"""SQLite schema for the HydroSizer-owned catalog."""

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS products (
    catalog_id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_code TEXT NOT NULL COLLATE NOCASE,
    material_name_pt TEXT NOT NULL,
    material_name_en TEXT NOT NULL,
    product_code TEXT NOT NULL COLLATE NOCASE,
    manufacturer TEXT,
    standard TEXT,
    series TEXT,
    nominal_diameter REAL NOT NULL,
    nominal_diameter_unit TEXT NOT NULL,
    internal_diameter REAL NOT NULL,
    internal_diameter_unit TEXT NOT NULL,
    pressure_class TEXT,
    max_allowable_pressure REAL,
    pressure_unit TEXT,
    hazen_williams_c REAL,
    absolute_roughness REAL,
    roughness_unit TEXT,
    cost_per_length REAL,
    cost_length_unit TEXT,
    currency TEXT,
    priority INTEGER,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    qgisred_material_value TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (material_code, product_code)
);

CREATE INDEX IF NOT EXISTS idx_products_active
ON products (active);

CREATE INDEX IF NOT EXISTS idx_products_search
ON products (material_code, product_code, material_name_pt, material_name_en);
"""
