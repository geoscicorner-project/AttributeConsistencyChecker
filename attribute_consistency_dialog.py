# -*- coding: utf-8 -*-
import json
import os

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QLabel, QComboBox,
    QListWidget, QListWidgetItem, QLineEdit, QPushButton, QMessageBox,
    QGroupBox, QAbstractItemView, QFileDialog, QInputDialog, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressDialog, QApplication
)
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsField, QgsWkbTypes,
    QgsVectorFileWriter, QgsProviderRegistry, QgsFeatureRequest
)


class AttributeConsistencyDialog(QDialog):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.rules = []
        self.result_layer = None
        self.result_rows = []
        self.input_layer = None
        self._loading_values = False
        self._source_domain_map = {}
        self._target_domain_map = {}
        self._domain_diagnostics = {}
        self.setWindowTitle("Attribute Consistency Checker — v0.2.5")
        self.resize(1050, 820)
        self._build_ui()
        self._load_layers()

    def _build_ui(self):
        root = QVBoxLayout(self)
        intro = QLabel(
            "<b>Attribute Consistency Checker</b><br>"
            "Rules search for keywords in the source field. Only features matching a keyword "
            "but having an unexpected target-field value are shown."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        data_group = QGroupBox("1. Input data")
        data_layout = QVBoxLayout(data_group)
        layer_row = QHBoxLayout()
        self.layer_combo = QComboBox()
        self.layer_combo.setMinimumWidth(300)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_changed)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._load_layers)
        self.browse_btn = QPushButton("Load vector file...")
        self.browse_btn.clicked.connect(self._browse_layer)
        self.browse_gdb_btn = QPushButton("Load GDB folder...")
        self.browse_gdb_btn.clicked.connect(self._browse_gdb)
        layer_row.addWidget(QLabel("Layer:"))
        layer_row.addWidget(self.layer_combo, 1)
        layer_row.addWidget(self.refresh_btn)
        layer_row.addWidget(self.browse_btn)
        layer_row.addWidget(self.browse_gdb_btn)
        data_layout.addLayout(layer_row)

        # Field selectors and their domain options share the same two rows.
        # This keeps domain controls adjacent to the corresponding field.
        fields_grid = QGridLayout()
        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        self.source_combo.currentIndexChanged.connect(self._on_field_selection_changed)
        self.target_combo.currentIndexChanged.connect(self._on_field_selection_changed)
        self.source_domain_mode = QComboBox()
        self.target_domain_mode = QComboBox()
        domain_options = [
            ("Auto-detect", "auto"),
            ("Yes — use coded value domain", "yes"),
            ("No — use stored values", "no")
        ]
        for combo in (self.source_domain_mode, self.target_domain_mode):
            for label, value in domain_options:
                combo.addItem(label, value)

        fields_grid.addWidget(QLabel("Source field:"), 0, 0)
        fields_grid.addWidget(self.source_combo, 0, 1)
        fields_grid.addWidget(QLabel("Source domain:"), 0, 2)
        fields_grid.addWidget(self.source_domain_mode, 0, 3)
        fields_grid.addWidget(QLabel("Target field:"), 1, 0)
        fields_grid.addWidget(self.target_combo, 1, 1)
        fields_grid.addWidget(QLabel("Target domain:"), 1, 2)
        fields_grid.addWidget(self.target_domain_mode, 1, 3)
        fields_grid.setColumnStretch(1, 3)
        fields_grid.setColumnStretch(3, 2)
        data_layout.addLayout(fields_grid)

        refresh_values_row = QHBoxLayout()
        self.refresh_values_btn = QPushButton("Refresh Attribute Values")
        self.refresh_values_btn.clicked.connect(self._load_unique_values)
        self.values_status = QLabel("Select fields, then click Refresh Attribute Values.")
        self.values_status.setWordWrap(True)
        refresh_values_row.addWidget(self.refresh_values_btn)
        refresh_values_row.addWidget(self.values_status, 1)
        data_layout.addLayout(refresh_values_row)
        self.source_domain_mode.currentIndexChanged.connect(self._on_domain_mode_changed)
        self.target_domain_mode.currentIndexChanged.connect(self._on_domain_mode_changed)
        root.addWidget(data_group)

        splitter = QSplitter(Qt.Horizontal)

        source_group = QGroupBox("2. Source field values")
        source_layout = QVBoxLayout(source_group)
        source_layout.addWidget(QLabel("Select existing values or enter keywords separated by semicolons (;):"))
        self.source_search = QLineEdit()
        self.source_search.setPlaceholderText("Search existing values (type to filter)...")
        self.source_search.textChanged.connect(
            lambda text: self._filter_values(self.source_values, text)
        )
        source_layout.addWidget(self.source_search)
        self.source_values = QListWidget()
        self.source_values.setSelectionMode(QAbstractItemView.ExtendedSelection)
        source_layout.addWidget(self.source_values)
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("Example: Mosque;Prayer Room")
        source_layout.addWidget(self.keyword_edit)
        splitter.addWidget(source_group)

        action_group = QWidget()
        action_layout = QVBoxLayout(action_group)
        action_layout.setContentsMargins(5, 0, 5, 0)
        action_layout.addStretch()
        self.build_target_values_btn = QPushButton("➜")
        self.build_target_values_btn.setToolTip(
            "Build target-value choices from records matching the source keywords."
        )
        self.build_target_values_btn.setMinimumSize(66, 58)
        self.build_target_values_btn.setStyleSheet(
            "QPushButton { font-size: 25px; font-weight: bold; padding: 8px; }"
        )
        self.build_target_values_btn.clicked.connect(self._build_target_value_list)
        action_layout.addWidget(self.build_target_values_btn, 0, Qt.AlignCenter)
        action_label = QLabel("Build target\nvalue list")
        action_label.setAlignment(Qt.AlignCenter)
        action_label.setWordWrap(True)
        action_layout.addWidget(action_label)
        action_layout.addStretch()
        splitter.addWidget(action_group)

        target_group = QGroupBox("3. Expected target values")
        target_layout = QVBoxLayout(target_group)
        target_layout.addWidget(QLabel("Select one or more target values that are considered valid:"))
        self.target_search = QLineEdit()
        self.target_search.setPlaceholderText("Search existing classes (type to filter)...")
        self.target_search.textChanged.connect(
            lambda text: self._filter_values(self.target_values, text)
        )
        target_layout.addWidget(self.target_search)
        self.target_values = QListWidget()
        self.target_values.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.target_values.setToolTip(
            "Select multiple values using Ctrl+click or Shift+click. "
            "All selected values are accepted by a single rule."
        )
        self.target_values.itemSelectionChanged.connect(self._update_target_selection_status)
        target_layout.addWidget(self.target_values)
        self.target_selection_status = QLabel(
            "Select one or more values (Ctrl/Shift+click)."
        )
        self.target_selection_status.setStyleSheet("color: #555;")
        target_layout.addWidget(self.target_selection_status)
        self.expected_edit = QLineEdit()
        self.expected_edit.setPlaceholderText("Or enter a target value manually")
        target_layout.addWidget(self.expected_edit)
        splitter.addWidget(target_group)
        splitter.setSizes([440, 90, 440])
        root.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        for label, slot in [
            ("Add rule from selection", self._add_rule),
            ("Remove selected rule", self._remove_rule),
            ("Save rules to JSON", self._save_rules),
            ("Load rules from JSON", self._load_rules)
        ]:
            button = QPushButton(label)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        root.addLayout(buttons)

        rules_group = QGroupBox("4. Rule list")
        rules_layout = QVBoxLayout(rules_group)
        self.rules_list = QListWidget()
        rules_layout.addWidget(self.rules_list)
        root.addWidget(rules_group, 1)

        results_group = QGroupBox("5. Check results — inconsistent records only")
        results_layout = QVBoxLayout(results_group)
        self.result_summary = QLabel("No check has been run yet.")
        results_layout.addWidget(self.result_summary)
        self.results_table = QTableWidget(0, 6)
        self.results_table.setHorizontalHeaderLabels([
            "Feature ID", "Source value", "Actual target value",
            "Expected target value", "Rule", "Status"
        ])
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        results_layout.addWidget(self.results_table)
        root.addWidget(results_group, 2)

        bottom = QHBoxLayout()
        self.run_btn = QPushButton("Check Consistency")
        self.run_btn.clicked.connect(self._run_check)
        self.export_btn = QPushButton("Export results...")
        self.export_btn.clicked.connect(self._export_result)
        self.export_btn.setEnabled(False)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        bottom.addWidget(self.run_btn)
        bottom.addWidget(self.export_btn)
        bottom.addStretch()
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

    def _load_layers(self, preferred_id=None):
        current_id = preferred_id or self.layer_combo.currentData()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        layers = [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer) and lyr.isValid()
        ]
        active = self.iface.activeLayer()
        if isinstance(active, QgsVectorLayer) and active.isValid():
            if all(lyr.id() != active.id() for lyr in layers):
                layers.insert(0, active)
        for layer in layers:
            self.layer_combo.addItem(layer.name(), layer.id())
        selected = self.layer_combo.findData(current_id) if current_id else -1
        if selected < 0 and isinstance(active, QgsVectorLayer):
            selected = self.layer_combo.findData(active.id())
        if selected >= 0:
            self.layer_combo.setCurrentIndex(selected)
        self.layer_combo.blockSignals(False)
        self._on_layer_changed()

    def _add_vector_source(self, path, display_name=None):
        """Load a vector source; require sublayer selection for GDB/GPKG containers."""
        if not path:
            return False

        normalized_path = path.rstrip("/\\ ")
        extension = os.path.splitext(normalized_path)[1].lower()
        is_container = extension in (".gpkg", ".gdb", ".sqlite", ".db")
        default_name = display_name or os.path.splitext(
            os.path.basename(normalized_path)
        )[0]

        # GPKG and GDB can contain many feature classes. Always enumerate their
        # OGR sublayers first so the user explicitly chooses the feature class.
        if is_container:
            try:
                details = QgsProviderRegistry.instance().querySublayers(path)
            except Exception as exc:
                QMessageBox.critical(
                    self, "Failed to read database contents",
                    "QGIS could not read the layer list from this source.\n\n{}".format(exc)
                )
                return False

            valid_details = []
            for detail in details:
                # QgsProviderSublayerDetails objects returned by QGIS expose
                # providerKey(), uri(), and name(). Invalid layers are skipped
                # through isValid() rather than a broad exception handler.
                if detail.providerKey() not in ("ogr", ""):
                    continue
                uri = detail.uri()
                sub_name = detail.name()
                candidate = QgsVectorLayer(uri, sub_name, "ogr")
                if candidate.isValid():
                    valid_details.append((sub_name, uri))

            if not valid_details:
                QMessageBox.critical(
                    self, "No feature classes found",
                    "No readable feature classes/vector layers were found.\n\n"
                    "Pastikan database berisi data vektor dan didukung oleh QGIS/OGR."
                )
                return False

            labels = [item[0] for item in valid_details]
            selected_name, ok = QInputDialog.getItem(
                self,
                "Select feature class / layer",
                "The database contains the following layers. Select one to check:",
                labels, 0, False
            )
            if not ok:
                return False

            # Use the selected row rather than matching by name, since a data
            # source may contain repeated display names in different groups.
            selected_index = labels.index(selected_name)
            selected_uri = valid_details[selected_index][1]
            layer = QgsVectorLayer(selected_uri, selected_name, "ogr")
        else:
            # Ordinary single-layer vector files can be opened directly.
            layer = QgsVectorLayer(path, default_name, "ogr")

            # Some OGR formats expose sublayers instead of a directly openable
            # layer. In that case, enumerate and let the user choose one.
            if not layer.isValid():
                try:
                    details = QgsProviderRegistry.instance().querySublayers(path)
                except Exception:
                    details = []

                valid_details = []
                for detail in details:
                    # Filter unsupported providers and invalid sublayers
                    # without swallowing unexpected programming errors.
                    if detail.providerKey() not in ("ogr", ""):
                        continue
                    uri = detail.uri()
                    sub_name = detail.name()
                    candidate = QgsVectorLayer(uri, sub_name, "ogr")
                    if candidate.isValid():
                        valid_details.append((sub_name, uri))

                if len(valid_details) == 1:
                    selected_name, selected_uri = valid_details[0]
                elif len(valid_details) > 1:
                    labels = [item[0] for item in valid_details]
                    selected_name, ok = QInputDialog.getItem(
                        self, "Select layer", "Select the layer to check:",
                        labels, 0, False
                    )
                    if not ok:
                        return False
                    selected_uri = valid_details[labels.index(selected_name)][1]
                else:
                    QMessageBox.critical(
                        self, "Data tidak dapat dibuka",
                        "QGIS could not open this source as a vector layer.\n\n"
                        "Pastikan format didukung oleh QGIS/OGR."
                    )
                    return False
                layer = QgsVectorLayer(selected_uri, selected_name, "ogr")

        if not layer.isValid():
            QMessageBox.critical(
                self, "Failed to load layer",
                "Layer '{}' was found but could not be opened.".format(layer.name())
            )
            return False

        # Keep the selected source as an internal layer object. Do not add it to
        # the QGIS project/map layer tree.
        self.input_layer = layer
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        self.layer_combo.addItem("{} [external input]".format(layer.name()), "__external_input__")
        self.layer_combo.blockSignals(False)
        self._on_layer_changed()
        return True

    def _browse_layer(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select vector data", "",
            "Data vektor (*.shp *.gpkg *.geojson *.json *.kml *.gml *.tab "
            "*.mif *.dxf *.csv *.gpx *.sqlite *.db *.vrt);;"
            "All files (*.*)"
        )
        if path:
            self._add_vector_source(path)

    def _browse_gdb(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select File Geodatabase folder (.gdb)", ""
        )
        if path:
            self._add_vector_source(path)

    def _current_layer(self):
        layer_id = self.layer_combo.currentData()
        if layer_id == "__external_input__":
            layer = self.input_layer
        else:
            layer = QgsProject.instance().mapLayer(layer_id) if layer_id else None
        return layer if isinstance(layer, QgsVectorLayer) and layer.isValid() else None

    def _on_layer_changed(self):
        layer = self._current_layer()
        self.source_combo.blockSignals(True)
        self.target_combo.blockSignals(True)
        self.source_combo.clear()
        self.target_combo.clear()
        if layer:
            for field in layer.fields():
                self.source_combo.addItem(field.name())
                self.target_combo.addItem(field.name())
            if self.target_combo.count() > 1:
                self.target_combo.setCurrentIndex(1)
        self.source_combo.blockSignals(False)
        self.target_combo.blockSignals(False)
        self._clear_attribute_values("Select fields, then click Refresh Attribute Values.")

    def _on_field_selection_changed(self, *_args):
        self._clear_attribute_values("Fields changed. Click Refresh Attribute Values to reload.")

    def _on_domain_mode_changed(self, *_args):
        self._clear_attribute_values("Domain settings changed. Click Refresh Attribute Values to apply them.")

    def _clear_attribute_values(self, message):
        self.source_values.clear()
        self.target_values.clear()
        self.source_search.clear()
        self.target_search.clear()
        self._source_domain_map = {}
        self._target_domain_map = {}
        self.values_status.setText(message)

    def _field_domain_map(self, layer, field_index):
        """Read coded-value domains using QGIS provider metadata and GDAL/OGR.

        OGR lookup is based on the actual datasource URI and field name. This
        avoids relying on display names or QGIS field indexes, which may differ
        from the underlying OGR definition.
        """
        mapping = {}
        field_name = layer.fields().at(field_index).name()
        diagnostics = {
            "field": field_name,
            "provider": layer.providerType(),
            "source": layer.source(),
            "domain_name": "",
            "driver": "",
            "feature_class": "",
            "method": "",
            "error": ""
        }

        # First try the QGIS provider connection API.
        try:
            field = layer.fields().at(field_index)
            domain_name = field.domainName() if hasattr(field, "domainName") else ""
            if domain_name:
                diagnostics["domain_name"] = str(domain_name)
                metadata = QgsProviderRegistry.instance().providerMetadata(layer.providerType())
                if metadata and hasattr(metadata, "createConnection"):
                    connection = metadata.createConnection(layer.source(), {})
                    domain = connection.fieldDomain(domain_name) if connection else None
                    if domain and hasattr(domain, "values"):
                        for coded_value in domain.values():
                            mapping[str(coded_value.code())] = str(coded_value.value())
                        if mapping:
                            diagnostics["method"] = "QGIS provider metadata"
        except Exception as exc:
            diagnostics["qgis_error"] = str(exc)

        # GDAL/OGR fallback. Resolve the OGR layer and field by name, not by
        # display label or by the QGIS field index.
        if not mapping:
            ds = None
            try:
                from osgeo import ogr

                source_uri = layer.source()
                parts = source_uri.split("|")
                datasource = parts[0]
                uri_options = {}
                for part in parts[1:]:
                    if "=" in part:
                        key, value = part.split("=", 1)
                        uri_options[key.lower()] = value

                open_ex = getattr(ogr, "OpenEx", None)
                if open_ex:
                    flags = getattr(ogr, "OF_VECTOR", 4) | getattr(ogr, "OF_READONLY", 0)
                    ds = open_ex(datasource, flags)
                else:
                    ds = ogr.Open(datasource, 0)

                if ds is None:
                    raise RuntimeError("GDAL/OGR tidak dapat membuka datasource: {}".format(datasource))

                expected_names = []
                for key in ("layername", "layer", "layername"):
                    if uri_options.get(key):
                        expected_names.append(uri_options[key])
                expected_names.append(layer.name())

                ogr_layer = None
                layer_count = ds.GetLayerCount()
                candidates = []
                for idx in range(layer_count):
                    candidate = ds.GetLayer(idx)
                    if candidate is None:
                        continue
                    candidate_name = candidate.GetName()
                    candidates.append(candidate)
                    normalized_candidate = candidate_name.replace("\\\\", "/").split("/")[-1].casefold()
                    if any(
                        candidate_name.casefold() == name.casefold()
                        or normalized_candidate == name.replace("\\\\", "/").split("/")[-1].casefold()
                        for name in expected_names if name
                    ):
                        ogr_layer = candidate
                        break

                # If layer naming differs, select the layer that actually has
                # the requested field.
                if ogr_layer is None:
                    for candidate in candidates:
                        definition = candidate.GetLayerDefn()
                        if definition.GetFieldIndex(field_name) >= 0:
                            ogr_layer = candidate
                            break

                if ogr_layer is None:
                    raise RuntimeError(
                        "Feature class not found. Searched name: {}".format(
                            ", ".join(expected_names)
                        )
                    )

                diagnostics["feature_class"] = ogr_layer.GetName()
                driver = ds.GetDriver()
                diagnostics["driver"] = driver.GetName() if driver else ""

                definition = ogr_layer.GetLayerDefn()
                ogr_field_index = definition.GetFieldIndex(field_name)
                if ogr_field_index < 0:
                    raise RuntimeError(
                        "Field '{}' was not found in the OGR feature class definition '{}'.".format(
                            field_name, ogr_layer.GetName()
                        )
                    )

                ogr_field = definition.GetFieldDefn(ogr_field_index)
                domain_name = None
                if hasattr(ogr_field, "GetDomainName"):
                    domain_name = ogr_field.GetDomainName()
                if domain_name:
                    diagnostics["domain_name"] = str(domain_name)

                # Some FileGDB datasets expose the domain catalogue even when
                # the field-to-domain association is not surfaced by the
                # provider. In that case, try the conventional field/domain
                # name match, but only if that domain exists.
                if not domain_name and hasattr(ds, "GetFieldDomain") and hasattr(ds, "GetFieldDomainNames"):
                    available_domains = list(ds.GetFieldDomainNames() or [])
                    matching = [name for name in available_domains
                                if str(name).casefold() == field_name.casefold()]
                    if matching:
                        domain_name = matching[0]
                        diagnostics["domain_name"] = str(domain_name)

                if not domain_name:
                    raise RuntimeError(
                        "Field '{}' tidak memiliki nama domain yang diekspos oleh driver {}.".format(
                            field_name, diagnostics["driver"] or "OGR"
                        )
                    )

                if not hasattr(ds, "GetFieldDomain"):
                    raise RuntimeError(
                        "GDAL/OGR does not provide GetFieldDomain. Check the GDAL version and driver."
                    )

                domain = ds.GetFieldDomain(domain_name)
                if domain is None:
                    raise RuntimeError(
                        "Domain '{}' is registered but its definition could not be read.".format(domain_name)
                    )

                if hasattr(domain, "GetDomainType"):
                    diagnostics["domain_type"] = str(domain.GetDomainType())

                if hasattr(domain, "GetEnumeration"):
                    coded_values = domain.GetEnumeration()
                    if hasattr(coded_values, "items"):
                        mapping = {str(k): str(v) for k, v in coded_values.items()}
                    elif coded_values:
                        mapping = {str(item[0]): str(item[1]) for item in coded_values}

                if mapping:
                    diagnostics["method"] = "GDAL/OGR ({})".format(diagnostics["driver"] or "driver tidak diketahui")
                else:
                    raise RuntimeError(
                        "Domain '{}' was found, but its coded-value list is empty or unsupported.".format(
                            domain_name
                        )
                    )
            except Exception as exc:
                diagnostics["ogr_error"] = str(exc)
            finally:
                ds = None

        self._domain_diagnostics[field_name] = diagnostics
        return mapping

    def _effective_domain_map(self, layer, field_index, mode_combo, field_label):
        mode = mode_combo.currentData()
        if mode == "no":
            return {}
        mapping = self._field_domain_map(layer, field_index)
        if mode == "yes" and not mapping:
            field_name = layer.fields().at(field_index).name()
            details = self._domain_diagnostics.get(field_name, {})
            diagnostic_lines = [
                "Field: {}".format(field_name),
                "Provider: {}".format(details.get("provider", "-")),
                "Driver OGR: {}".format(details.get("driver", "-")),
                "Feature Class: {}".format(details.get("feature_class", "-")),
                "Domain: {}".format(details.get("domain_name", "-")),
                "Kesalahan QGIS: {}".format(details.get("qgis_error", "-")),
                "Kesalahan OGR: {}".format(details.get("ogr_error", "-"))
            ]
            QMessageBox.warning(
                self, "Unable to read domain",
                "The plugin could not read the coded value domain for {}. "
                "Stored attribute values will be used as a fallback.\n\n{}".format(
                    field_label, "\\n".join(diagnostic_lines)
                )
            )
        return mapping

    def _append_value_item(self, widget, code, domain_map):
        code_text = str(code)
        label = domain_map.get(code_text)
        display = "{} — {}".format(code_text, label) if label else code_text
        item = QListWidgetItem(display)
        item.setData(Qt.UserRole, code_text)
        widget.addItem(item)

    def _load_unique_values(self):
        """Load distinct source values only; target values are built on demand."""
        if self._loading_values:
            return
        layer = self._current_layer()
        self.source_values.clear()
        self.target_values.clear()
        self.source_search.clear()
        self.target_search.clear()
        self._source_domain_map = {}
        self._target_domain_map = {}
        if not layer or not self.source_combo.currentText() or not self.target_combo.currentText():
            self.values_status.setText("Select a layer, source field, and target field first.")
            return

        source_name = self.source_combo.currentText()
        si = layer.fields().indexFromName(source_name)
        if si < 0:
            self.values_status.setText("Invalid source field.")
            return

        self._loading_values = True
        self.refresh_values_btn.setEnabled(False)
        self.build_target_values_btn.setEnabled(False)
        self.values_status.setText("Reading unique source-field values...")
        total = max(0, layer.featureCount())
        progress = QProgressDialog(
            "Reading unique source-field values. Large datasets may take some time.",
            "Cancel", 0, total if total > 0 else 0, self
        )
        progress.setWindowTitle("Loading source values")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()
        QApplication.processEvents()

        source_set = set()
        try:
            self._source_domain_map = self._effective_domain_map(
                layer, si, self.source_domain_mode, "source field"
            )
            request = QgsFeatureRequest().setSubsetOfAttributes([source_name], layer.fields())
            processed = 0
            canceled = False
            for feature in layer.getFeatures(request):
                value = feature.attribute(si)
                if value is not None and str(value).strip():
                    source_set.add(str(value).strip())
                processed += 1
                if processed % 250 == 0:
                    if total > 0:
                        progress.setValue(min(processed, total))
                    else:
                        progress.setLabelText(
                            "Reading source values... {} features processed".format(processed)
                        )
                    QApplication.processEvents()
                    if progress.wasCanceled():
                        canceled = True
                        break

            if canceled:
                self._clear_attribute_values(
                    "Reading was cancelled. Click Refresh Attribute Values to try again."
                )
                return

            for value in sorted(source_set, key=str.casefold):
                self._append_value_item(self.source_values, value, self._source_domain_map)

            self.values_status.setText(
                "Done: {:,} unique source values. Select source values or enter keywords, "
                "then click 'Build Target Value List'.".format(len(source_set))
            )
        except Exception as exc:
            self.values_status.setText("Failed to read source attribute values.")
            QMessageBox.warning(self, "Failed to read attributes", str(exc))
        finally:
            progress.close()
            self._loading_values = False
            self.refresh_values_btn.setEnabled(True)
            self.build_target_values_btn.setEnabled(True)

    def _build_target_value_list(self):
        """Build target choices from actual target values in source-matching records."""
        if self._loading_values:
            return
        layer = self._current_layer()
        if not layer:
            QMessageBox.warning(self, "Invalid input", "Select a vector layer first.")
            return

        source_name = self.source_combo.currentText()
        target_name = self.target_combo.currentText()
        si = layer.fields().indexFromName(source_name)
        ti = layer.fields().indexFromName(target_name)
        if si < 0 or ti < 0:
            QMessageBox.warning(self, "Invalid fields", "Select valid source and target fields.")
            return

        # Use selected existing source values and/or manually entered keywords.
        keywords = list(dict.fromkeys(
            self._selected_values(self.source_values) + self._split_manual(self.keyword_edit.text())
        ))
        if not keywords:
            QMessageBox.information(
                self, "Source value belum ditentukan",
                "Select one or more values from the source-field list, or enter keywords "
                "in the text box below the list."
            )
            return

        self.target_values.clear()
        self.target_search.clear()
        self._update_target_selection_status()
        self._target_domain_map = {}
        self._loading_values = True
        self.refresh_values_btn.setEnabled(False)
        self.build_target_values_btn.setEnabled(False)
        self.values_status.setText("Finding target values in matching records...")

        total = max(0, layer.featureCount())
        progress = QProgressDialog(
            "Finding records based on source values and collecting actual target values...",
            "Cancel", 0, total if total > 0 else 0, self
        )
        progress.setWindowTitle("Building target value list")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()
        QApplication.processEvents()

        target_counts = {}
        matched_count = 0
        try:
            self._target_domain_map = self._effective_domain_map(
                layer, ti, self.target_domain_mode, "target field"
            )
            normalized_keywords = [key.casefold() for key in keywords if key]
            request = QgsFeatureRequest().setSubsetOfAttributes(
                [source_name, target_name], layer.fields()
            )
            processed = 0
            canceled = False
            for feature in layer.getFeatures(request):
                source_value = feature.attribute(si)
                if source_value is None:
                    processed += 1
                    continue
                source_text = str(source_value).strip().casefold()
                if source_text and any(key in source_text for key in normalized_keywords):
                    matched_count += 1
                    target_value = feature.attribute(ti)
                    if target_value is not None and str(target_value).strip():
                        target_text = str(target_value).strip()
                        target_counts[target_text] = target_counts.get(target_text, 0) + 1
                processed += 1
                if processed % 250 == 0:
                    if total > 0:
                        progress.setValue(min(processed, total))
                    else:
                        progress.setLabelText(
                            "Processing... {} features checked".format(processed)
                        )
                    QApplication.processEvents()
                    if progress.wasCanceled():
                        canceled = True
                        break

            if canceled:
                self.target_values.clear()
                self.values_status.setText(
                    "Target list generation was cancelled. Click the button to try again."
                )
                return

            for value, count in sorted(
                target_counts.items(), key=lambda pair: (-pair[1], pair[0].casefold())
            ):
                label = self._target_domain_map.get(value)
                display_value = "{} — {}".format(value, label) if label else value
                percentage = (count / float(matched_count) * 100.0) if matched_count else 0.0
                display = "{}  |  {:,} record  |  {:.2f}%".format(
                    display_value, count, percentage
                )
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, value)
                item.setData(Qt.UserRole + 1, count)
                self.target_values.addItem(item)

            if target_counts:
                self.values_status.setText(
                    "Target list complete: {:,} matching records, {:,} unique target values. "
                    "Sorted by frequency (highest first); percentages are calculated from all matching records."
                    .format(matched_count, len(target_counts))
                )
            else:
                self.values_status.setText(
                    "No target values were found in {:,} records matching the source keywords.".format(
                        matched_count
                    )
                )
        except Exception as exc:
            self.values_status.setText("Failed to build target value list.")
            QMessageBox.warning(self, "Failed to build target list", str(exc))
        finally:
            progress.close()
            self._loading_values = False
            self.refresh_values_btn.setEnabled(True)
            self.build_target_values_btn.setEnabled(True)

    def _filter_values(self, widget, text):
        """Filter displayed attribute values without changing stored codes."""
        query = (text or "").strip().casefold()
        for index in range(widget.count()):
            item = widget.item(index)
            item.setHidden(bool(query) and query not in item.text().casefold())

    @staticmethod
    def _split_manual(text):
        # Titik koma adalah pemisah utama sesuai format yang diminta user.
        return [part.strip() for part in (text or "").split(";") if part.strip()]

    def _add_rule(self):
        keywords = list(dict.fromkeys(
            self._selected_values(self.source_values) + self._split_manual(self.keyword_edit.text())
        ))
        expected = list(dict.fromkeys(
            self._selected_values(self.target_values) + self._split_manual(self.expected_edit.text())
        ))
        if not keywords:
            QMessageBox.warning(self, "Incomplete rule",
                                "Select source values or enter keywords, e.g. Mosque;Prayer Room.")
            return
        if not expected:
            QMessageBox.warning(self, "Incomplete rule",
                                "Select or enter at least one expected target value.")
            return
        name, ok = QInputDialog.getText(
            self, "Rule name", "Rule name:", text="Rule {}".format(len(self.rules) + 1)
        )
        if not ok:
            return
        self.rules.append({
            "rule_name": name.strip() or "Rule {}".format(len(self.rules) + 1),
            "source_field": self.source_combo.currentText(),
            "target_field": self.target_combo.currentText(),
            "matching_method": "contains",
            "case_sensitive": False,
            "source_values": keywords,
            "expected_values": expected,
            "enabled": True
        })
        self._refresh_rules()
        self.keyword_edit.clear()
        self.expected_edit.clear()
        self._update_target_selection_status()

    def _selected_values(self, widget):
        values = []
        for item in widget.selectedItems():
            value = item.data(Qt.UserRole)
            if value is None:
                value = item.text().split(" — ", 1)[0].strip()
            if str(value).strip():
                values.append(str(value).strip())
        return values

    def _update_target_selection_status(self):
        count = len(self.target_values.selectedItems())
        if count:
            self.target_selection_status.setText(
                "{} target values selected — any one is accepted (OR).".format(count)
            )
        else:
            self.target_selection_status.setText(
                "Select one or more values (Ctrl/Shift+click)."
            )

    @staticmethod
    def _expected_values(rule):
        """Return allowed target values as a list; supports legacy JSON strings."""
        values = rule.get("expected_values", [])
        if isinstance(values, str):
            values = [v.strip() for v in values.split(";") if v.strip()]
        return [str(v).strip() for v in values if str(v).strip()]

    def _refresh_rules(self):
        self.rules_list.clear()
        for i, rule in enumerate(self.rules):
            keywords = ";".join(rule.get("source_values", []))
            expected = " / ".join(self._expected_values(rule))
            state = "Aktif" if rule.get("enabled", True) else "Nonaktif"
            self.rules_list.addItem(
                "{} | {} → {} [{}]".format(i + 1, keywords, expected, state)
            )

    def _remove_rule(self):
        index = self.rules_list.currentRow()
        if index >= 0:
            self.rules.pop(index)
            self._refresh_rules()

    def _save_rules(self):
        if not self.rules:
            QMessageBox.information(self, "No rules", "There are no rules to save.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save rules", "", "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({
                    "source_field": self.source_combo.currentText(),
                    "target_field": self.target_combo.currentText(),
                    "rules": self.rules
                }, stream, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Success", "Rules saved to:\\n{}".format(path))
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def _load_rules(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load rules", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as stream:
                payload = json.load(stream)
            self.rules = payload.get("rules", [])
            if self.source_combo.findText(payload.get("source_field", "")) >= 0:
                self.source_combo.setCurrentText(payload["source_field"])
            if self.target_combo.findText(payload.get("target_field", "")) >= 0:
                self.target_combo.setCurrentText(payload["target_field"])
            self._refresh_rules()
            QMessageBox.information(self, "Success", "Successfully loaded {} rules.".format(len(self.rules)))
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))

    def _run_check(self):
        layer = self._current_layer()
        if not layer:
            QMessageBox.warning(self, "Invalid input", "Select a vector layer first.")
            return
        if not self.rules:
            QMessageBox.warning(self, "No rules", "Add at least one rule.")
            return

        source_field = self.source_combo.currentText()
        target_field = self.target_combo.currentText()
        si = layer.fields().indexFromName(source_field)
        ti = layer.fields().indexFromName(target_field)
        active_rules = [
            r for r in self.rules
            if r.get("enabled", True)
            and r.get("source_field") == source_field
            and r.get("target_field") == target_field
        ]
        if not active_rules:
            QMessageBox.warning(self, "No matching rules",
                                "There are no active rules for the selected field pair.")
            return

        geom_name = QgsWkbTypes.displayString(layer.wkbType())
        output = QgsVectorLayer(
            "{}?crs={}".format(geom_name, layer.crs().authid()),
            "{}_inconsistent".format(layer.name()), "memory"
        )
        provider = output.dataProvider()
        provider.addAttributes(list(layer.fields()) + [
            QgsField("QC_STATUS", QVariant.String, len=24),
            QgsField("QC_RULE", QVariant.String, len=254),
            QgsField("QC_EXPECT", QVariant.String, len=254),
            QgsField("QC_ACTUAL", QVariant.String, len=254)
        ])
        output.updateFields()

        self.results_table.setRowCount(0)
        self.result_rows = []
        output_features = []
        checked_count = 0
        ignored_count = 0

        for feature in layer.getFeatures():
            source_value = feature.attribute(si)
            target_value = feature.attribute(ti)
            source_text = "" if source_value is None else str(source_value).strip()
            target_text = "" if target_value is None else str(target_value).strip()

            if not source_text:
                ignored_count += 1
                continue

            matched_rules = []
            for rule in active_rules:
                text = source_text if rule.get("case_sensitive", False) else source_text.casefold()
                keys = [
                    k if rule.get("case_sensitive", False) else k.casefold()
                    for k in rule.get("source_values", [])
                ]
                method = rule.get("matching_method", "contains")
                if any(
                    (text == key if method == "exact" else
                     text.startswith(key) if method == "starts_with" else
                     text.endswith(key) if method == "ends_with" else
                     key in text)
                    for key in keys
                ):
                    matched_rules.append(rule)

            # Tidak ada kata pemicu yang cocok: record diabaikan sepenuhnya.
            if not matched_rules:
                ignored_count += 1
                continue

            checked_count += 1
            expected_sets = [
                set(v.casefold() for v in self._expected_values(rule))
                for rule in matched_rules
            ]
            conflict = len(set(tuple(sorted(values)) for values in expected_sets)) > 1

            if conflict:
                status = "RULE_CONFLICT"
                expected_display = " | ".join(sorted(set(
                    v for rule in matched_rules for v in self._expected_values(rule)
                )))
            else:
                allowed = expected_sets[0] if expected_sets else set()
                status = "INCONSISTENT" if target_text.casefold() not in allowed else None
                expected_display = " | ".join(self._expected_values(matched_rules[0]))

            # Hanya record yang salah atau konflik dimasukkan ke tabel dan output.
            if status is None:
                continue

            rule_display = ";".join(r["rule_name"] for r in matched_rules)
            row_values = [
                str(feature.id()), source_text, target_text,
                expected_display, rule_display, status
            ]
            self.result_rows.append((feature.id(), row_values))
            row = self.results_table.rowCount()
            self.results_table.insertRow(row)
            for col, value in enumerate(row_values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.results_table.setItem(row, col, item)

            out_feature = QgsFeature(output.fields())
            out_feature.setGeometry(feature.geometry())
            attrs = feature.attributes()
            attrs.extend([status, rule_display, expected_display, target_text])
            out_feature.setAttributes(attrs)
            output_features.append(out_feature)

        if output_features:
            provider.addFeatures(output_features)
        output.updateExtents()
        self.result_layer = output
        self.export_btn.setEnabled(bool(output_features))

        if output_features:
            QgsProject.instance().addMapLayer(output)
        self.result_summary.setText(
            "Features matching keywords: {} | Mismatches/conflicts: {} | "
            "Ignored (no keyword match): {}".format(
                checked_count, len(output_features), ignored_count
            )
        )

        QMessageBox.information(
            self, "Check complete",
            "Check complete.\\n\\n"
            "Features matching keywords: {}\\n"
            "Mismatches/conflicts: {}\\n"
            "Ignored: {}\\n\\n"
            "The table shows only mismatched or conflicting records.".format(
                checked_count, len(output_features), ignored_count
            )
        )

    def _export_result(self):
        if not self.result_layer or not self.result_layer.isValid() or self.result_layer.featureCount() == 0:
            QMessageBox.information(self, "No results", "There are no problematic records to export.")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export inconsistent records", "",
            "GeoPackage (*.gpkg);;ESRI Shapefile (*.shp)"
        )
        if not path:
            return
        driver = "GPKG" if "GeoPackage" in selected_filter else "ESRI Shapefile"
        extension = ".gpkg" if driver == "GPKG" else ".shp"
        if not path.lower().endswith(extension):
            path += extension
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = driver
        options.fileEncoding = "UTF-8"
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as exc:
                QMessageBox.critical(self, "Failed to overwrite file", str(exc))
                return
        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            self.result_layer, path, QgsProject.instance().transformContext(), options
        )
        if result[0] == QgsVectorFileWriter.NoError:
            QMessageBox.information(self, "Export successful", "Inconsistent records saved to:\\n{}".format(path))
        else:
            QMessageBox.critical(self, "Export failed", str(result))
