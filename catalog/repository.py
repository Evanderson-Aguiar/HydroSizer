"""SQLite persistence and CSV interchange for the HydroSizer catalog."""

import csv
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .schema import SCHEMA_SQL, SCHEMA_VERSION
from .validation import (
    CatalogValidationError,
    EDITABLE_FIELDS,
    prepare_product,
    validate_product,
)


# ``priority`` remains in schema version 1 only for backward compatibility.
# It is deliberately excluded from new CSV exports and from sizing decisions.
CSV_EXPORT_FIELDS = tuple(
    field for field in EDITABLE_FIELDS if field != "priority"
)

_LIST_PRODUCTS_SQL = """
    SELECT *
    FROM products
    WHERE (:active_only = 0 OR active = 1)
      AND (
          :search = ''
          OR material_code LIKE :term
          OR material_name_pt LIKE :term
          OR material_name_en LIKE :term
          OR product_code LIKE :term
          OR manufacturer LIKE :term
      )
    ORDER BY
        CASE WHEN :sort_by = 'catalog_id' THEN catalog_id END,
        CASE WHEN :sort_by = 'material_code' THEN material_code END
            COLLATE NOCASE,
        CASE WHEN :sort_by = 'material_name_pt' THEN material_name_pt END
            COLLATE NOCASE,
        CASE WHEN :sort_by = 'material_name_en' THEN material_name_en END
            COLLATE NOCASE,
        CASE WHEN :sort_by = 'product_code' THEN product_code END
            COLLATE NOCASE,
        CASE WHEN :sort_by = 'nominal_diameter' THEN nominal_diameter END,
        CASE WHEN :sort_by = 'internal_diameter' THEN internal_diameter END,
        CASE WHEN :sort_by = 'priority' THEN priority END,
        CASE WHEN :sort_by = 'active' THEN active END,
        catalog_id
"""

_INSERT_PRODUCT_SQL = """
    INSERT INTO products (
        material_code, material_name_pt, material_name_en, product_code,
        manufacturer, standard, series, nominal_diameter,
        nominal_diameter_unit, internal_diameter, internal_diameter_unit,
        pressure_class, max_allowable_pressure, pressure_unit,
        hazen_williams_c, absolute_roughness, roughness_unit,
        cost_per_length, cost_length_unit, currency, priority, active,
        qgisred_material_value, notes, created_at, updated_at
    ) VALUES (
        :material_code, :material_name_pt, :material_name_en, :product_code,
        :manufacturer, :standard, :series, :nominal_diameter,
        :nominal_diameter_unit, :internal_diameter, :internal_diameter_unit,
        :pressure_class, :max_allowable_pressure, :pressure_unit,
        :hazen_williams_c, :absolute_roughness, :roughness_unit,
        :cost_per_length, :cost_length_unit, :currency, :priority, :active,
        :qgisred_material_value, :notes, :created_at, :updated_at
    )
"""

_UPDATE_PRODUCT_SQL = """
    UPDATE products
    SET material_code = :material_code,
        material_name_pt = :material_name_pt,
        material_name_en = :material_name_en,
        product_code = :product_code,
        manufacturer = :manufacturer,
        standard = :standard,
        series = :series,
        nominal_diameter = :nominal_diameter,
        nominal_diameter_unit = :nominal_diameter_unit,
        internal_diameter = :internal_diameter,
        internal_diameter_unit = :internal_diameter_unit,
        pressure_class = :pressure_class,
        max_allowable_pressure = :max_allowable_pressure,
        pressure_unit = :pressure_unit,
        hazen_williams_c = :hazen_williams_c,
        absolute_roughness = :absolute_roughness,
        roughness_unit = :roughness_unit,
        cost_per_length = :cost_per_length,
        cost_length_unit = :cost_length_unit,
        currency = :currency,
        priority = :priority,
        active = :active,
        qgisred_material_value = :qgisred_material_value,
        notes = :notes,
        updated_at = :updated_at
    WHERE catalog_id = :catalog_id
"""


class CatalogConflictError(ValueError):
    """Raised when a material/product code pair already exists."""


class CatalogImportError(ValueError):
    """Raised when an atomic CSV import cannot be completed."""


class CatalogRepository:
    """Persist HydroSizer-owned products without external dependencies."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        """Create an empty versioned catalog or verify its schema version."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                connection.executescript(SCHEMA_SQL)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version != SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported catalog schema version {version}; "
                    f"expected {SCHEMA_VERSION}."
                )

    def seed_from_csv_if_empty(
        self, source_path: Path
    ) -> Tuple[int, List[str]]:
        """Import bundled products once, without changing a populated catalog."""
        with self._connect() as connection:
            product_count = connection.execute(
                "SELECT COUNT(*) FROM products"
            ).fetchone()[0]
        if product_count:
            return 0, []

        try:
            return self.import_csv(source_path)
        except CatalogConflictError:
            # A second QGIS process may have populated the shared profile after
            # the empty check. In that case, preserve its catalog unchanged.
            with self._connect() as connection:
                product_count = connection.execute(
                    "SELECT COUNT(*) FROM products"
                ).fetchone()[0]
            if product_count:
                return 0, []
            raise

    def list_products(
        self,
        search: str = "",
        active_only: bool = False,
        sort_by: str = "material_code",
    ) -> List[Dict[str, Any]]:
        """List products using an allowlisted deterministic sort column."""
        allowed_sort = {
            "catalog_id",
            "material_code",
            "material_name_pt",
            "material_name_en",
            "product_code",
            "nominal_diameter",
            "internal_diameter",
            "priority",
            "active",
        }
        if sort_by not in allowed_sort:
            raise ValueError(f"Unsupported catalog sort column: {sort_by}")
        normalized_search = search.strip()
        parameters = {
            "active_only": 1 if active_only else 0,
            "search": normalized_search,
            "term": f"%{normalized_search}%",
            "sort_by": sort_by,
        }
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(_LIST_PRODUCTS_SQL, parameters)
            ]

    def get_product(self, catalog_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM products WHERE catalog_id = ?", (catalog_id,)
            ).fetchone()
        return dict(row) if row else None

    def add_product(
        self, product: Mapping[str, Any]
    ) -> Tuple[int, List[str]]:
        normalized, warnings = prepare_product(product)
        now = _utc_now()
        parameters = dict(normalized)
        parameters.update(created_at=now, updated_at=now)
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    _INSERT_PRODUCT_SQL,
                    parameters,
                )
                catalog_id = cursor.lastrowid
        except sqlite3.IntegrityError as error:
            raise CatalogConflictError(
                "material_code and product_code must be unique together"
            ) from error
        return int(catalog_id), warnings

    def update_product(
        self, catalog_id: int, product: Mapping[str, Any]
    ) -> List[str]:
        normalized, warnings = prepare_product(product)
        parameters = dict(normalized)
        parameters.update(
            updated_at=_utc_now(),
            catalog_id=catalog_id,
        )
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    _UPDATE_PRODUCT_SQL,
                    parameters,
                )
                if cursor.rowcount != 1:
                    raise KeyError(f"Catalog product {catalog_id} does not exist")
        except sqlite3.IntegrityError as error:
            raise CatalogConflictError(
                "material_code and product_code must be unique together"
            ) from error
        return warnings

    def duplicate_product(self, catalog_id: int) -> Tuple[int, List[str]]:
        product = self.get_product(catalog_id)
        if product is None:
            raise KeyError(f"Catalog product {catalog_id} does not exist")
        base_code = product["product_code"]
        suffix = 1
        while True:
            candidate = f"{base_code}-COPY" if suffix == 1 else f"{base_code}-COPY-{suffix}"
            if not self._product_code_exists(product["material_code"], candidate):
                break
            suffix += 1
        duplicate = {field: product[field] for field in EDITABLE_FIELDS}
        duplicate["product_code"] = candidate
        return self.add_product(duplicate)

    def set_active(self, catalog_id: int, active: bool) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE products SET active = ?, updated_at = ? "
                "WHERE catalog_id = ?",
                (1 if active else 0, _utc_now(), catalog_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Catalog product {catalog_id} does not exist")

    def delete_product(self, catalog_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM products WHERE catalog_id = ?", (catalog_id,)
            )
            return cursor.rowcount == 1

    def validate_catalog(self) -> Dict[str, Any]:
        items = []
        for product in self.list_products(sort_by="catalog_id"):
            validation = validate_product(product)
            items.append(
                {
                    "catalog_id": product["catalog_id"],
                    "material_code": product["material_code"],
                    "product_code": product["product_code"],
                    "errors": validation["errors"],
                    "warnings": validation["warnings"],
                }
            )
        return {
            "product_count": len(items),
            "invalid_count": sum(bool(item["errors"]) for item in items),
            "warning_count": sum(len(item["warnings"]) for item in items),
            "items": items,
        }

    def export_csv(self, target_path: Path) -> int:
        """Atomically export editable product fields as UTF-8 CSV."""
        target = Path(target_path)
        if not target.parent.is_dir():
            raise FileNotFoundError(f"Destination folder does not exist: {target.parent}")
        products = self.list_products(sort_by="catalog_id")
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8-sig",
                newline="",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                writer = csv.DictWriter(
                    temporary_file,
                    fieldnames=CSV_EXPORT_FIELDS,
                )
                writer.writeheader()
                for product in products:
                    writer.writerow(
                        {
                            field: _csv_value(product[field])
                            for field in CSV_EXPORT_FIELDS
                        }
                    )
                temporary_path = Path(temporary_file.name)
            os.replace(temporary_path, target)
        except Exception:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
            raise
        return len(products)

    def import_csv(self, source_path: Path) -> Tuple[int, List[str]]:
        """Validate every row, then import all rows in one transaction."""
        source = Path(source_path).resolve(strict=True)
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise CatalogImportError("CSV has no header")
            missing = [
                field
                for field in (
                    "material_code",
                    "material_name_pt",
                    "material_name_en",
                    "product_code",
                    "nominal_diameter",
                    "nominal_diameter_unit",
                    "internal_diameter",
                    "internal_diameter_unit",
                )
                if field not in reader.fieldnames
            ]
            if missing:
                raise CatalogImportError(
                    "CSV is missing required columns: " + ", ".join(missing)
                )
            prepared = []
            warnings = []
            seen = set()
            for row_number, row in enumerate(reader, start=2):
                try:
                    normalized, row_warnings = prepare_product(row)
                except CatalogValidationError as error:
                    raise CatalogImportError(
                        f"CSV row {row_number}: {'; '.join(error.errors)}"
                    ) from error
                key = (
                    normalized["material_code"],
                    normalized["product_code"],
                )
                if key in seen:
                    raise CatalogImportError(
                        f"CSV row {row_number}: duplicate material/product code"
                    )
                seen.add(key)
                prepared.append(normalized)
                warnings.extend(
                    f"row {row_number}: {warning}" for warning in row_warnings
                )

        now = _utc_now()
        try:
            with self._connect() as connection:
                for product in prepared:
                    parameters = dict(product)
                    parameters.update(created_at=now, updated_at=now)
                    connection.execute(
                        _INSERT_PRODUCT_SQL,
                        parameters,
                    )
        except sqlite3.IntegrityError as error:
            raise CatalogConflictError(
                "CSV conflicts with an existing material/product code"
            ) from error
        return len(prepared), warnings

    def _product_code_exists(self, material_code: str, product_code: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM products WHERE material_code = ? "
                "AND product_code = ?",
                (material_code, product_code),
            ).fetchone()
        return row is not None

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return value
