# HydroSizer Product Catalog

## Ownership and Location

The catalog belongs exclusively to HydroSizer. It does not read, edit, replace, or synchronize QGISRed `*_Materials.dbf` files. The mutable SQLite database is created under the active QGIS profile in `HydroSizer/catalog.sqlite`; no machine-specific absolute path is stored in source code.

When the database in the active profile has no products, HydroSizer imports the bundled 77-product initial catalog in one transaction. Existing catalogs are never overwritten, merged, or otherwise changed by this initialization. The bundled values come from the reviewed project list and retain notes where manufacturer, cost, or other commercial information remains pending; users remain responsible for verifying applicability before design use.

## Schema

SQLite schema version 1 stores an autoincrementing `catalog_id`, stable material and product codes, Portuguese and English names, manufacturer, standard, series, nominal and real internal diameters with units, pressure data, Hazen–Williams C, absolute roughness with units, unit cost, currency, availability, optional `qgisred_material_value`, notes, and UTC creation/update timestamps. A legacy `priority` column remains in existing databases for schema compatibility, but the interface, new CSV exports, and sizing logic ignore it.

`catalog_id` is an internal primary key. `(material_code, product_code)` is unique without case sensitivity. Duplicating a record generates `-COPY`, `-COPY-2`, and subsequent deterministic product-code suffixes.

## Validation

Structural errors prevent saving or importing:

- missing codes, bilingual names, diameters, or diameter units;
- nonnumeric, nonfinite, zero, or negative required diameters;
- invalid units;
- nonpositive allowable pressure or Hazen–Williams C;
- negative roughness or cost;
- dependent unit fields missing;
- duplicate material/product codes.

Hydraulic incompleteness is advisory so partial catalogs can be prepared incrementally. Warnings identify missing pressure, missing both C and absolute roughness, missing cost, missing currency, or internal diameter greater than nominal diameter.

## CSV Interchange

CSV export uses UTF-8 with BOM and writes the current editable fields, excluding internal IDs, timestamps, and legacy priority. Import requires the core identity and diameter columns, accepts optional and older columns, validates every row first, detects duplicates within the file, and inserts all rows in one SQLite transaction. Any invalid row or database conflict rolls back the entire import.

Exports are written to a temporary file in the destination directory and atomically replaced on success.

## Interface Operations

The catalog table supports filtering, header sorting, adding, editing, deterministic duplication, activating/deactivating, deletion with confirmation, validation, and CSV import/export. The active-only filter affects only the view. Deactivation means the product is generally unavailable and should not be used for a project-specific preference.

In **Criteria > Products Allowed in This Project**, choose **All active materials** or one material code. This temporary project filter does not update the catalog. For example, choosing `PE100-SDR11` makes the current sizing run consider only active products with that material code.
