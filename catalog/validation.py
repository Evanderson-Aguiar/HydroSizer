"""Normalization and validation rules for catalog products."""

from typing import Any, Dict, List, Mapping, Tuple

try:
    from ..core.units import to_si
except ImportError:  # Standalone test discovery from the plugin directory.
    from core.units import to_si


EDITABLE_FIELDS = (
    "material_code",
    "material_name_pt",
    "material_name_en",
    "product_code",
    "manufacturer",
    "standard",
    "series",
    "nominal_diameter",
    "nominal_diameter_unit",
    "internal_diameter",
    "internal_diameter_unit",
    "pressure_class",
    "max_allowable_pressure",
    "pressure_unit",
    "hazen_williams_c",
    "absolute_roughness",
    "roughness_unit",
    "cost_per_length",
    "cost_length_unit",
    "currency",
    "priority",
    "active",
    "qgisred_material_value",
    "notes",
)

REQUIRED_TEXT_FIELDS = (
    "material_code",
    "material_name_pt",
    "material_name_en",
    "product_code",
)

TEXT_FIELDS = (
    "material_code",
    "material_name_pt",
    "material_name_en",
    "product_code",
    "manufacturer",
    "standard",
    "series",
    "nominal_diameter_unit",
    "internal_diameter_unit",
    "pressure_class",
    "pressure_unit",
    "roughness_unit",
    "cost_length_unit",
    "currency",
    "qgisred_material_value",
    "notes",
)

FLOAT_FIELDS = (
    "nominal_diameter",
    "internal_diameter",
    "max_allowable_pressure",
    "hazen_williams_c",
    "absolute_roughness",
    "cost_per_length",
)

ALLOWED_UNITS = {
    "nominal_diameter_unit": {"mm", "m", "in"},
    "internal_diameter_unit": {"mm", "m", "in"},
    "pressure_unit": {"mca", "kPa", "bar", "psi"},
    "roughness_unit": {"mm", "m", "in"},
    "cost_length_unit": {"per m", "per ft"},
}


class CatalogValidationError(ValueError):
    """Raised when a product has structural validation errors."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_product(raw_product: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize one product and return errors plus advisory warnings."""
    errors: List[str] = []
    warnings: List[str] = []
    normalized: Dict[str, Any] = {}

    for field in TEXT_FIELDS:
        normalized[field] = _text(raw_product.get(field))
    for field in FLOAT_FIELDS:
        normalized[field] = _optional_float(
            raw_product.get(field), field, errors
        )
    normalized["priority"] = _optional_integer(
        raw_product.get("priority"), "priority", errors
    )
    normalized["active"] = _boolean(raw_product.get("active", True), errors)

    for field in REQUIRED_TEXT_FIELDS:
        if not normalized[field]:
            errors.append(f"{field} is required")

    for field in ("nominal_diameter", "internal_diameter"):
        value = normalized[field]
        if value is None:
            errors.append(f"{field} is required")
        elif value <= 0:
            errors.append(f"{field} must be greater than zero")

    for field, allowed in ALLOWED_UNITS.items():
        value = normalized[field]
        if value:
            canonical = {
                option.casefold(): option for option in allowed
            }.get(value.casefold())
            if canonical is None:
                errors.append(
                    f"{field} must be one of: {', '.join(sorted(allowed))}"
                )
            else:
                normalized[field] = canonical

    for field in ("nominal_diameter_unit", "internal_diameter_unit"):
        if not normalized[field]:
            errors.append(f"{field} is required")

    pressure = normalized["max_allowable_pressure"]
    if pressure is None:
        warnings.append("maximum allowable pressure is not defined")
    elif pressure <= 0:
        errors.append("max_allowable_pressure must be greater than zero")
    if pressure is not None and not normalized["pressure_unit"]:
        errors.append("pressure_unit is required when pressure is provided")

    coefficient = normalized["hazen_williams_c"]
    if coefficient is not None and coefficient <= 0:
        errors.append("hazen_williams_c must be greater than zero")
    roughness = normalized["absolute_roughness"]
    if roughness is not None and roughness < 0:
        errors.append("absolute_roughness must not be negative")
    if roughness is not None and not normalized["roughness_unit"]:
        errors.append("roughness_unit is required when roughness is provided")
    if coefficient is None and roughness is None:
        warnings.append(
            "product is hydraulically incomplete: provide C or absolute roughness"
        )

    cost = normalized["cost_per_length"]
    if cost is None:
        warnings.append("unit cost is not defined")
    elif cost < 0:
        errors.append("cost_per_length must not be negative")
    if cost is not None and not normalized["cost_length_unit"]:
        errors.append("cost_length_unit is required when cost is provided")
    if cost is not None and not normalized["currency"]:
        warnings.append("currency is not defined for the unit cost")

    _warn_if_internal_exceeds_nominal(normalized, warnings)
    return {
        "normalized": normalized,
        "errors": errors,
        "warnings": warnings,
        "valid": not errors,
    }


def prepare_product(raw_product: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Return normalized values or raise a structured validation error."""
    validation = validate_product(raw_product)
    if validation["errors"]:
        raise CatalogValidationError(validation["errors"])
    return validation["normalized"], validation["warnings"]


def _warn_if_internal_exceeds_nominal(
    product: Mapping[str, Any], warnings: List[str]
) -> None:
    nominal = product["nominal_diameter"]
    internal = product["internal_diameter"]
    nominal_unit = product["nominal_diameter_unit"]
    internal_unit = product["internal_diameter_unit"]
    if None in {nominal, internal} or not nominal_unit or not internal_unit:
        return
    try:
        nominal_m = to_si(nominal, "diameter", nominal_unit)
        internal_m = to_si(internal, "diameter", internal_unit)
    except ValueError:
        return
    if internal_m > nominal_m:
        warnings.append("internal diameter is greater than nominal diameter")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _optional_float(value: Any, field: str, errors: List[str]):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be numeric")
        return None
    text = str(value).strip()
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        number = float(text)
    except (TypeError, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        errors.append(f"{field} must be finite")
        return None
    return number


def _optional_integer(value: Any, field: str, errors: List[str]):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be an integer")
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        errors.append(f"{field} must be an integer")
        return None
    return number


def _boolean(value: Any, errors: List[str]) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "sim", "active"}:
        return True
    if normalized in {"0", "false", "no", "não", "nao", "inactive"}:
        return False
    errors.append("active must be a boolean")
    return True
