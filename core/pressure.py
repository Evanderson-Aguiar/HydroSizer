"""Pure endpoint-pressure verification for Stage 11."""

from collections import defaultdict
import math
from typing import Any, Dict, Mapping, Optional, Tuple

from .units import to_si


MARGIN_MODES = ("none", "factor", "additive")


def evaluate_endpoint_pressure(
    dataset: Mapping[str, Any],
    requested_pipe_id: Any,
    pressure_unit: str,
    margin_mode: str,
    safety_factor: float,
    additive_margin_value: float,
    additive_margin_unit: str,
    product: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Resolve endpoint pressures and optionally check one product rating."""
    mode = str(margin_mode).strip().casefold()
    if mode not in MARGIN_MODES:
        raise ValueError("margin mode must be none, factor, or additive")
    requested_id, error = _normalize_id(
        requested_pipe_id,
        dataset["pipe_id_category"],
    )
    if error:
        raise ValueError("pipe ID to evaluate is null, empty, or invalid")
    matching_pipes = []
    for record in dataset["pipe_records"]:
        normalized, record_error = _normalize_id(
            record["pipe_id"],
            dataset["pipe_id_category"],
        )
        if not record_error and normalized == requested_id:
            matching_pipes.append(record)
    if not matching_pipes:
        raise ValueError(f"pipe ID {requested_id!r} was not found")
    if len(matching_pipes) > 1:
        raise ValueError(f"pipe ID {requested_id!r} is duplicated")
    pipe = matching_pipes[0]

    node_index = defaultdict(list)
    for record in dataset["node_records"]:
        normalized, node_error = _normalize_id(
            record["node_id"],
            dataset["node_id_category"],
        )
        if not node_error:
            node_index[normalized].append(record)

    initial_id = _node_id_at_coordinate(
        pipe.get("initial_coordinate"),
        dataset["node_records"],
        dataset["node_id_category"],
        dataset["endpoint_tolerance"],
        "initial",
    )
    final_id = _node_id_at_coordinate(
        pipe.get("final_coordinate"),
        dataset["node_records"],
        dataset["node_id_category"],
        dataset["endpoint_tolerance"],
        "final",
    )

    warnings = []
    initial_original, initial_pressure, initial_fids = _resolve_node_pressure(
        initial_id,
        node_index,
        pressure_unit,
        "initial",
        warnings,
    )
    final_original, final_pressure, final_fids = _resolve_node_pressure(
        final_id,
        node_index,
        pressure_unit,
        "final",
        warnings,
    )
    base_pressure = max(initial_pressure, final_pressure)
    if initial_pressure < 0 or final_pressure < 0:
        warnings.append(
            "At least one endpoint pressure is negative; review the hydraulic "
            "simulation before sizing."
        )

    factor = _finite(safety_factor, "safety factor")
    applied_factor = 1.0
    additive_margin_pa = 0.0
    additive_margin_original = 0.0
    if mode == "factor":
        if factor < 1:
            raise ValueError("safety factor must be greater than or equal to 1")
        applied_factor = factor
        verification_pressure = base_pressure * factor
    elif mode == "additive":
        additive_margin_original = additive_margin_value
        additive_margin_pa = to_si(
            additive_margin_value,
            "pressure",
            additive_margin_unit,
        )
        if additive_margin_pa < 0:
            raise ValueError("additive pressure margin must not be negative")
        verification_pressure = base_pressure + additive_margin_pa
    else:
        verification_pressure = base_pressure

    result = {
        "pipe_fid": pipe["fid"],
        "pipe_id": requested_id,
        "initial_node_id": initial_id,
        "final_node_id": final_id,
        "initial_node_fids": initial_fids,
        "final_node_fids": final_fids,
        "pressure_unit": pressure_unit,
        "initial_pressure_original": initial_original,
        "final_pressure_original": final_original,
        "initial_pressure_pa": initial_pressure,
        "final_pressure_pa": final_pressure,
        "base_verification_pressure_pa": base_pressure,
        "margin_mode": mode,
        "safety_factor": applied_factor,
        "additive_margin_pa": additive_margin_pa,
        "additive_margin_original": additive_margin_original,
        "additive_margin_unit": additive_margin_unit,
        "verification_pressure_pa": verification_pressure,
        "warnings": warnings,
    }
    if product is None:
        return result
    allowable_pressure = _product_allowable_pressure(product)
    tolerance = 1.0e-9 * max(1.0, allowable_pressure)
    admissible = verification_pressure <= allowable_pressure + tolerance
    result.update(
        {
            "catalog_id": int(product.get("catalog_id") or 0),
            "material_code": product.get("material_code") or "",
            "product_code": product.get("product_code") or "",
            "pressure_class": product.get("pressure_class") or "",
            "allowable_pressure_original": product.get(
                "max_allowable_pressure"
            ),
            "allowable_pressure_unit": product.get("pressure_unit") or "",
            "allowable_pressure_pa": allowable_pressure,
            "admissible": admissible,
            "status": "PASS" if admissible else "FAIL",
        }
    )
    return result


def resolve_endpoint_pressure(
    dataset: Mapping[str, Any],
    requested_pipe_id: Any,
    pressure_unit: str,
    margin_mode: str,
    safety_factor: float,
    additive_margin_value: float,
    additive_margin_unit: str,
) -> Dict[str, Any]:
    """Resolve endpoint pressures without selecting or checking a product."""
    return evaluate_endpoint_pressure(
        dataset,
        requested_pipe_id,
        pressure_unit,
        margin_mode,
        safety_factor,
        additive_margin_value,
        additive_margin_unit,
        product=None,
    )


def format_endpoint_pressure_report(
    dataset: Mapping[str, Any],
    result: Mapping[str, Any],
) -> str:
    """Format mappings, endpoint values, margin, and pressure-class decision."""
    lines = [
        "HydroSizer Endpoint Pressure Verification — Stage 11",
        "Mode: read-only; no attributes or geometries were changed",
        "",
        "Mapping",
        "  Relationship: pipe start/end geometry to node-result points",
        f"  Pipe layer: {dataset['pipe_layer_name']}",
        f"  Pipe ID: {dataset['pipe_id_field']}",
        f"  Initial endpoint: {dataset['initial_node_id_field']}",
        f"  Final endpoint: {dataset['final_node_id_field']}",
        f"  Node result layer/table: {dataset['node_layer_name']}",
        f"  Node result ID: {dataset['node_id_field']}",
        f"  Pressure: {dataset['pressure_field']} [{dataset['pressure_unit']}]",
        f"  Pipe CRS: {dataset.get('pipe_crs', '<not reported>')}",
        "  Endpoint tolerance: "
        f"{_number(dataset.get('endpoint_tolerance', 0.0))} map unit(s)",
        "",
        "Resolved endpoints",
        f"  Pipe ID: {result['pipe_id']}",
        f"  Initial node: {result['initial_node_id']}",
        "  Initial pressure: "
        f"{_number(result['initial_pressure_original'])} "
        f"{result['pressure_unit']} "
        f"({_number(result['initial_pressure_pa'])} Pa)",
        f"  Final node: {result['final_node_id']}",
        "  Final pressure: "
        f"{_number(result['final_pressure_original'])} "
        f"{result['pressure_unit']} "
        f"({_number(result['final_pressure_pa'])} Pa)",
        "  Base verification pressure = max(initial, final): "
        f"{_number(result['base_verification_pressure_pa'])} Pa",
        "",
        "Margin",
        f"  Mode: {result['margin_mode']}",
        f"  Safety factor: {_number(result['safety_factor'])}",
        "  Additive margin input: "
        f"{_number(result['additive_margin_original'])} "
        f"{result['additive_margin_unit']}",
        f"  Additive margin SI: {_number(result['additive_margin_pa'])} Pa",
        f"  Final verification pressure: "
        f"{_number(result['verification_pressure_pa'])} Pa",
        "",
        "Product check",
        f"  Catalog ID: {result['catalog_id']}",
        f"  Product: {result['material_code']}/{result['product_code']}",
        f"  Pressure class: {result['pressure_class'] or '<not provided>'}",
        "  Allowable pressure: "
        f"{_number(result['allowable_pressure_original'])} "
        f"{result['allowable_pressure_unit']} "
        f"({_number(result['allowable_pressure_pa'])} Pa)",
        f"  Status: {result['status']}",
        "  Decision: verification pressure is "
        + ("within" if result["admissible"] else "above")
        + " the product rating.",
    ]
    if result["warnings"]:
        lines.extend(["", "Warnings"])
        lines.extend(f"  - {warning}" for warning in result["warnings"])
    lines.extend(
        [
            "",
            "Method limitations",
            "  Verification uses pressures at the two pipe endpoints.",
            "  Critical high/low profile points must be represented by nodes.",
            "  This is not a transient or water-hammer analysis.",
            "  The displayed node-result state must represent the intended scenario.",
        ]
    )
    return "\n".join(lines)


def _resolve_node_pressure(
    node_id: str,
    node_index: Mapping[str, Any],
    pressure_unit: str,
    endpoint_name: str,
    warnings: list,
) -> Tuple[float, float, list]:
    records = node_index.get(node_id, [])
    if not records:
        raise ValueError(
            f"{endpoint_name} endpoint node {node_id!r} has no pressure result"
        )
    original_values = []
    values = []
    for record in records:
        pressure = _finite(record["pressure"], f"pressure for node {node_id}")
        original_values.append(pressure)
        values.append(to_si(pressure, "pressure", pressure_unit))
    first = values[0]
    tolerance = 1.0e-9 * max(1.0, abs(first))
    if any(abs(value - first) > tolerance for value in values[1:]):
        raise ValueError(f"node {node_id!r} has conflicting pressure results")
    if len(records) > 1:
        warnings.append(
            f"Node {node_id!r} has {len(records)} equivalent pressure records."
        )
    return original_values[0], first, [record["fid"] for record in records]


def _node_id_at_coordinate(
    coordinate: Any,
    node_records: list,
    node_id_category: str,
    tolerance_value: Any,
    endpoint_name: str,
) -> str:
    if not coordinate or len(coordinate) != 2:
        raise ValueError(f"{endpoint_name} pipe endpoint geometry is missing")
    x = _finite(coordinate[0], f"{endpoint_name} endpoint x")
    y = _finite(coordinate[1], f"{endpoint_name} endpoint y")
    tolerance = _finite(tolerance_value, "endpoint matching tolerance")
    if tolerance < 0:
        raise ValueError("endpoint matching tolerance must not be negative")
    matches = {}
    for record in node_records:
        node_coordinate = record.get("coordinate")
        if not node_coordinate or len(node_coordinate) != 2:
            continue
        node_x = _finite(node_coordinate[0], "node x")
        node_y = _finite(node_coordinate[1], "node y")
        if math.hypot(node_x - x, node_y - y) > tolerance:
            continue
        node_id, error = _normalize_id(record["node_id"], node_id_category)
        if not error:
            matches[node_id] = True
    if not matches:
        raise ValueError(
            f"{endpoint_name} pipe endpoint has no node within tolerance "
            f"{tolerance:.12g}"
        )
    if len(matches) > 1:
        identifiers = ", ".join(sorted(matches))
        raise ValueError(
            f"{endpoint_name} pipe endpoint is ambiguous; matching nodes: "
            f"{identifiers}"
        )
    return next(iter(matches))


def _product_allowable_pressure(product: Mapping[str, Any]) -> float:
    value = product.get("max_allowable_pressure")
    unit = product.get("pressure_unit")
    if value in {None, ""} or not unit:
        raise ValueError("selected product has no allowable pressure")
    pressure = to_si(value, "pressure", unit)
    if pressure <= 0:
        raise ValueError("selected product allowable pressure must be positive")
    return pressure


def _normalize_id(value: Any, category: str) -> Tuple[Optional[str], str]:
    if value is None or isinstance(value, bool):
        return None, "invalid"
    if category == "integer":
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None, "invalid"
        if not math.isfinite(number) or not number.is_integer():
            return None, "invalid"
        return str(int(number)), ""
    text = str(value).strip()
    return (text, "") if text else (None, "invalid")


def _finite(value: Any, name: str) -> float:
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
