# -*- coding: utf-8 -*-
import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from .attribute_consistency_dialog import AttributeConsistencyDialog


class AttributeConsistencyChecker:
    def __init__(self, iface):
        self.iface = iface
        self.menu_action = None
        self.toolbar_action = None
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path)
        main_window = self.iface.mainWindow()

        # Keep the plugin name in the Plugins menu.
        self.menu_action = QAction(icon, "Attribute Consistency Checker", main_window)
        self.menu_action.setToolTip("Attribute Consistency Checker")
        self.menu_action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&Attribute Consistency Checker", self.menu_action)

        # Use a separate icon-only action in the toolbar so no plugin name is shown there.
        self.toolbar_action = QAction(icon, "", main_window)
        self.toolbar_action.setToolTip("Attribute Consistency Checker")
        self.toolbar_action.setStatusTip(
            "Check attribute consistency using keyword-based rules"
        )
        self.toolbar_action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.toolbar_action)

    def unload(self):
        if self.menu_action:
            self.iface.removePluginMenu(
                "&Attribute Consistency Checker", self.menu_action
            )
            self.menu_action = None
        if self.toolbar_action:
            self.iface.removeToolBarIcon(self.toolbar_action)
            self.toolbar_action = None

    def run(self):
        try:
            self.dialog = AttributeConsistencyDialog(self.iface)
            self.dialog.show()
            self.dialog.raise_()
            self.dialog.activateWindow()
        except Exception as exc:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Attribute Consistency Checker",
                "The plugin could not be opened:\\n{}".format(exc),
            )
