# Attribute Consistency Checker

A QGIS plugin for checking attribute consistency with configurable keyword-based rules.

## Features

- Load vector data from supported vector file formats.
- Select a feature class from File Geodatabase and GeoPackage containers without adding it to the QGIS map.
- Choose source and target fields independently.
- Refresh distinct attribute values on demand, with progress feedback for large datasets.
- Configure coded-value domain handling for source and target fields.
- Build target-value choices from records matching the selected source values or keywords.
- View target-value frequencies and percentages to help identify dominant classifications.
- Allow multiple accepted target values in a single rule (OR logic).
- Save and load reusable rules in JSON format.
- Review inconsistent records and export the results.

## Installation

1. Download the latest plugin ZIP from the [GitHub repository](https://github.com/geoscicorner-project/AttributeConsistencyChecker).
2. In QGIS, open **Plugins → Manage and Install Plugins → Install from ZIP**.
3. Select the downloaded ZIP file and install the plugin.
4. Launch it from the **Plugins** menu or use its icon in the QGIS toolbar.

## Compatibility

- QGIS 3.28 or later.
- Coded-value domain decoding depends on the capabilities of the data provider and the installed GDAL/OGR version.

## Author

[GeosciCorner-Project](https://plugins.qgis.org/plugins/author/GeosciCorner-Project/)

## Source code and issue tracker

- [GitHub repository](https://github.com/geoscicorner-project/AttributeConsistencyChecker)
- [Report an issue](https://github.com/geoscicorner-project/AttributeConsistencyChecker/issues)

## License

GNU General Public License v2.0 or later. See [LICENSE](LICENSE).
