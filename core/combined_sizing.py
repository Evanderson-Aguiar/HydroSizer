"""Combined single-segment criteria and deterministic selection for Stage 10."""

import math
from typing import Any, Dict, Mapping, Sequence

from .darcy_weisbach import size_single_segment_darcy_weisbach
from .equations import bresse_diameter_m
from .hazen_williams import size_single_segment_hazen_williams
from .units import to_si


MINIMUM_VELOCITY_MODES = ("disabled", "warning", "required")


def size_single_segment_combined(
    products: Sequence[Mapping[str, Any]],
    hydraulic_method: str,
    flow_value: float,
    flow_unit: str,
    length_value: float,
    length_unit: str,
    max_gradient_enabled: bool,
    max_gradient_value: float,
    max_gradient_unit: str,
    max_velocity_enabled: bool,
    max_velocity_m_s: float,
    min_velocity_mode: str,
    min_velocity_m_s: float,
    min_nominal_enabled: bool,
    min_nominal_value: float,
    min_nominal_unit: str,
    bresse_enabled: bool,
    bresse_coefficient: float,
    pressure_enabled: bool,
    verification_pressure_value: float,
    verification_pressure_unit: str,
    material_filter: str,
    kinematic_viscosity_value: float,
    kinematic_viscosity_unit: str,
) -> Dict[str, Any]:
    """Apply all enabled criteria and select one deterministic candidate."""
    method = _normalize_method(hydraulic_method)
    project_material = str(material_filter or "").strip()
    scoped_products = [
        product
        for product in products
        if not project_material
        or str(product.get("material_code") or "").strip().casefold()
        == project_material.casefold()
    ]
    minimum_mode = str(min_velocity_mode).strip().casefold()
    if minimum_mode not in MINIMUM_VELOCITY_MODES:
        raise ValueError(
            "minimum velocity mode must be disabled, warning, or required"
        )
    maximum_velocity = _finite(max_velocity_m_s, "maximum velocity")
    minimum_velocity = _finite(min_velocity_m_s, "minimum velocity")
    if max_velocity_enabled and maximum_velocity <= 0:
        raise ValueError("maximum velocity must be greater than zero")
    if minimum_mode != "disabled" and minimum_velocity <= 0:
        raise ValueError("minimum velocity must be greater than zero")

    minimum_nominal_m = None
    if min_nominal_enabled:
        minimum_nominal_m = to_si(
            min_nominal_value,
            "diameter",
            min_nominal_unit,
        )
        if minimum_nominal_m <= 0:
            raise ValueError("minimum nominal diameter must be greater than zero")

    pressure_pa = None
    if pressure_enabled:
        pressure_pa = to_si(
            verification_pressure_value,
            "pressure",
            verification_pressure_unit,
        )
        if pressure_pa < 0:
            raise ValueError("verification pressure must not be negative")

    if method == "H-W":
        base = size_single_segment_hazen_williams(
            scoped_products,
            flow_value,
            flow_unit,
            length_value,
            length_unit,
            max_gradient_value,
            max_gradient_unit,
            max_gradient_enabled=max_gradient_enabled,
        )
    else:
        base = size_single_segment_darcy_weisbach(
            scoped_products,
            flow_value,
            flow_unit,
            length_value,
            length_unit,
            max_gradient_value,
            max_gradient_unit,
            kinematic_viscosity_value,
            kinematic_viscosity_unit,
            max_gradient_enabled=max_gradient_enabled,
        )

    theoretical_diameter_m = None
    if bresse_enabled:
        theoretical_diameter_m = bresse_diameter_m(
            base["flow_m3_s_signed"],
            bresse_coefficient,
        )

    products_by_id = {
        int(product.get("catalog_id") or 0): product for product in products
    }
    evaluated = []
    for base_candidate in base["evaluated"]:
        product = products_by_id.get(base_candidate["catalog_id"], {})
        evaluated.append(
            _apply_criteria(
                base_candidate,
                product,
                base["max_gradient_m_m"],
                max_velocity_enabled,
                maximum_velocity,
                minimum_mode,
                minimum_velocity,
                minimum_nominal_m,
                theoretical_diameter_m,
                pressure_pa,
            )
        )

    admissible = [item for item in evaluated if item["admissible"]]
    admissible.sort(key=_selection_key)
    selected = admissible[0] if admissible else None
    result = dict(base)
    result.update(
        {
            "hydraulic_method": method,
            "material_filter": project_material,
            "max_gradient_enabled": bool(max_gradient_enabled),
            "max_velocity_enabled": bool(max_velocity_enabled),
            "max_velocity_m_s": maximum_velocity,
            "min_velocity_mode": minimum_mode,
            "min_velocity_m_s": minimum_velocity,
            "min_nominal_enabled": bool(min_nominal_enabled),
            "min_nominal_m": minimum_nominal_m,
            "bresse_enabled": bool(bresse_enabled),
            "bresse_coefficient": _finite(
                bresse_coefficient,
                "Bresse coefficient",
            ),
            "bresse_diameter_m": theoretical_diameter_m,
            "pressure_enabled": bool(pressure_enabled),
            "verification_pressure_pa": pressure_pa,
            "evaluated": evaluated,
            "selected": selected,
        }
    )
    return result


def format_combined_sizing_report(result: Mapping[str, Any]) -> str:
    """Format enabled criteria, candidate decisions, and final selection."""
    lines = [
        "HydroSizer Combined Criteria Demonstration — Stage 10",
        "Scope: one manual segment; active catalog products; no layer access",
        "",
        "Configuration",
        f"  Hydraulic method: {result['hydraulic_method']}",
        "  Project material filter: "
        + (result["material_filter"] or "all active materials"),
        "  Maximum unit headloss: "
        + (
            f"{_number(result['max_gradient_m_m'])} m/m (required)"
            if result["max_gradient_enabled"]
            else "disabled"
        ),
        "  Maximum velocity: "
        + (
            f"{_number(result['max_velocity_m_s'])} m/s (required)"
            if result["max_velocity_enabled"]
            else "disabled"
        ),
        "  Minimum velocity: "
        f"{result['min_velocity_mode']}"
        + (
            f" at {_number(result['min_velocity_m_s'])} m/s"
            if result["min_velocity_mode"] != "disabled"
            else ""
        ),
        "  Minimum nominal diameter: "
        + (
            f"{_number(result['min_nominal_m'])} m (required)"
            if result["min_nominal_enabled"]
            else "disabled"
        ),
        "  Bresse estimate: "
        + (
            f"D={_number(result['bresse_diameter_m'])} m, "
            f"K={_number(result['bresse_coefficient'])} (initial estimate)"
            if result["bresse_enabled"]
            else "disabled"
        ),
        "  Pressure verification: "
        + (
            f"{_number(result['verification_pressure_pa'])} Pa (required)"
            if result["pressure_enabled"]
            else "disabled"
        ),
        "",
        "Selection order",
        "  All enabled required criteria; smallest DN; lowest segment cost;",
        "  highest allowable pressure; lowest stable catalog ID.",
        "",
        f"Candidates ({len(result['evaluated'])})",
    ]
    if not result["evaluated"]:
        lines.append("  <no active catalog products>")
    for item in result["evaluated"]:
        if item["status"] == "insufficient_data":
            lines.append(
                f"  [INSUFFICIENT DATA] ID {item['catalog_id']} "
                f"{item['material_code']}/{item['product_code']}: "
                f"{item['reason']}"
            )
            continue
        label = "ADMISSIBLE" if item["admissible"] else "REJECTED"
        lines.extend(
            [
                f"  [{label}] ID {item['catalog_id']} "
                f"{item['material_code']}/{item['product_code']}",
                f"      DN={_number(item['nominal_diameter_m'])} m; "
                f"V={_number(item['velocity_m_s'])} m/s; "
                f"J={_number(item['unit_headloss_m_km'])} m/km",
                f"      Cost={_optional(item['segment_cost'])}; "
                f"allowable pressure={_optional(item['allowable_pressure_pa'])} Pa",
                f"      Status={item['status']}; "
                f"controlling criterion={item['controlling_criterion']}",
            ]
        )
        if item["failures"]:
            lines.append("      Failures: " + "; ".join(item["failures"]))
        if item["warnings"]:
            lines.append("      Warnings: " + "; ".join(item["warnings"]))

    lines.extend(["", "Selection"])
    selected = result["selected"]
    if selected is None:
        lines.append("  No product satisfies all enabled required criteria.")
    else:
        lines.extend(
            [
                f"  Selected catalog ID: {selected['catalog_id']}",
                f"  Product: {selected['material_code']}/{selected['product_code']}",
                f"  Status: {selected['status']}",
                f"  Controlling criterion: {selected['controlling_criterion']}",
                "  Justification: satisfies every required criterion and ranks "
                "first under the configured deterministic selection order.",
            ]
        )
    if result["warnings"]:
        lines.extend(["", "Hydraulic warnings"])
        lines.extend(f"  - {warning}" for warning in result["warnings"])
    lines.extend(
        [
            "",
            "Current limitations",
            "  Batch pressure is resolved automatically from mapped pipe endpoints.",
            "  Bresse is only an initial diameter estimate, not full validation.",
        ]
    )
    return "\n".join(lines)


def _apply_criteria(
    base: Mapping[str, Any],
    product: Mapping[str, Any],
    max_gradient_m_m: Any,
    max_velocity_enabled: bool,
    max_velocity_m_s: float,
    min_velocity_mode: str,
    min_velocity_m_s: float,
    min_nominal_m: Any,
    bresse_diameter_m_value: Any,
    verification_pressure_pa: Any,
) -> Dict[str, Any]:
    item = dict(base)
    item["allowable_pressure_pa"] = _allowable_pressure_pa(product)
    item["failures"] = []
    item["warnings"] = []
    item["criterion_ratios"] = {}
    if base["status"] != "evaluated":
        item["status"] = "insufficient_data"
        item["controlling_criterion"] = "hydraulic data"
        return item

    if max_gradient_m_m is not None:
        _maximum_criterion(
            item,
            "unit headloss",
            base["unit_headloss_m_m"],
            max_gradient_m_m,
        )
    if max_velocity_enabled:
        _maximum_criterion(
            item,
            "maximum velocity",
            base["velocity_m_s"],
            max_velocity_m_s,
        )
    if min_velocity_mode != "disabled":
        ratio = (
            math.inf
            if base["velocity_m_s"] == 0
            else min_velocity_m_s / base["velocity_m_s"]
        )
        if min_velocity_mode == "required":
            item["criterion_ratios"]["minimum velocity"] = ratio
        if base["velocity_m_s"] < min_velocity_m_s:
            message = (
                f"velocity {base['velocity_m_s']:.12g} m/s is below "
                f"{min_velocity_m_s:.12g} m/s"
            )
            if min_velocity_mode == "required":
                item["failures"].append(message)
            else:
                item["warnings"].append(message)
    if min_nominal_m is not None:
        _minimum_criterion(
            item,
            "minimum nominal diameter",
            base["nominal_diameter_m"],
            min_nominal_m,
        )
    if bresse_diameter_m_value is not None:
        _minimum_criterion(
            item,
            "Bresse initial diameter",
            base["nominal_diameter_m"],
            bresse_diameter_m_value,
        )
    if verification_pressure_pa is not None:
        allowable = item["allowable_pressure_pa"]
        if allowable is None:
            item["failures"].append("allowable product pressure is missing")
            item["criterion_ratios"]["pressure"] = math.inf
        else:
            _maximum_criterion(
                item,
                "pressure",
                verification_pressure_pa,
                allowable,
            )

    item["admissible"] = not item["failures"]
    item["status"] = (
        "sized with warning"
        if item["admissible"] and item["warnings"]
        else "sized"
        if item["admissible"]
        else "not admissible"
    )
    item["controlling_criterion"] = (
        max(
            item["criterion_ratios"],
            key=item["criterion_ratios"].get,
        )
        if item["criterion_ratios"]
        else "selection order"
    )
    return item


def _maximum_criterion(
    item: Dict[str, Any],
    name: str,
    actual: float,
    limit: float,
) -> None:
    ratio = actual / limit
    item["criterion_ratios"][name] = ratio
    tolerance = 1.0e-12 * max(1.0, limit)
    if actual > limit + tolerance:
        item["failures"].append(
            f"{name} {actual:.12g} exceeds {limit:.12g}"
        )


def _minimum_criterion(
    item: Dict[str, Any],
    name: str,
    actual: float,
    limit: float,
) -> None:
    ratio = math.inf if actual == 0 else limit / actual
    item["criterion_ratios"][name] = ratio
    tolerance = 1.0e-12 * max(1.0, limit)
    if actual + tolerance < limit:
        item["failures"].append(
            f"{name} {actual:.12g} is below {limit:.12g}"
        )


def _selection_key(item: Mapping[str, Any]):
    cost = item["segment_cost"]
    pressure = item["allowable_pressure_pa"]
    return (
        item["nominal_diameter_m"],
        cost is None,
        cost if cost is not None else math.inf,
        pressure is None,
        -pressure if pressure is not None else math.inf,
        item["catalog_id"],
    )


def _allowable_pressure_pa(product: Mapping[str, Any]):
    value = product.get("max_allowable_pressure")
    unit = product.get("pressure_unit")
    if value in {None, ""} or not unit:
        return None
    try:
        pressure = to_si(value, "pressure", unit)
    except ValueError:
        return None
    return pressure if pressure > 0 else None


def _normalize_method(value: str) -> str:
    normalized = str(value).strip().upper().replace("–", "-")
    aliases = {
        "H-W": "H-W",
        "HAZEN-WILLIAMS": "H-W",
        "D-W": "D-W",
        "DARCY-WEISBACH": "D-W",
    }
    if normalized not in aliases:
        raise ValueError("hydraulic method must be H-W or D-W")
    return aliases[normalized]


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _number(value: float) -> str:
    return f"{value:.12g}"


def _optional(value: Any) -> str:
    return "<not available>" if value is None else _number(value)
