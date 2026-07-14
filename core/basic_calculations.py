"""QGIS-independent velocity and segment cost calculations."""

import math
from typing import Any, Dict, Mapping

from .units import to_si


def velocity_m_per_s(flow_m3_s: float, internal_diameter_m: float) -> float:
    """Return mean velocity using `V = 4 |Q| / (π Di²)` in SI units."""
    flow = _finite_value(flow_m3_s, "flow")
    diameter = _finite_value(internal_diameter_m, "internal diameter")
    if diameter <= 0:
        raise ValueError("internal diameter must be greater than zero")
    return 4.0 * abs(flow) / (math.pi * diameter**2)


def segment_cost(length_m: float, cost_per_m: float) -> float:
    """Return `length × unit cost` using metres and currency per metre."""
    length = _finite_value(length_m, "length")
    unit_cost = _finite_value(cost_per_m, "unit cost")
    if length < 0:
        raise ValueError("length must not be negative")
    if unit_cost < 0:
        raise ValueError("unit cost must not be negative")
    return length * unit_cost


def calculate_basic_demo(
    flow_value: float,
    flow_unit: str,
    diameter_value: float,
    diameter_unit: str,
    length_value: float,
    length_unit: str,
    unit_cost_value: float,
    cost_length_unit: str,
) -> Dict[str, Any]:
    """Convert demo inputs to SI and calculate velocity and segment cost."""
    original_flow = _finite_value(flow_value, "flow")
    flow_m3_s = to_si(original_flow, "flow", flow_unit)
    diameter_m = to_si(diameter_value, "diameter", diameter_unit)
    length_m = to_si(length_value, "length", length_unit)
    cost_per_m = to_si(
        unit_cost_value,
        "cost_per_length",
        cost_length_unit,
    )
    if length_m < 0:
        raise ValueError("length must not be negative")
    if cost_per_m < 0:
        raise ValueError("unit cost must not be negative")
    velocity = velocity_m_per_s(flow_m3_s, diameter_m)
    total_cost = segment_cost(length_m, cost_per_m)
    return {
        "original_flow": original_flow,
        "original_flow_unit": flow_unit,
        "negative_flow": original_flow < 0,
        "zero_flow": original_flow == 0,
        "flow_m3_s_signed": flow_m3_s,
        "flow_m3_s_magnitude": abs(flow_m3_s),
        "diameter_m": diameter_m,
        "length_m": length_m,
        "cost_per_m": cost_per_m,
        "velocity_m_s": velocity,
        "segment_cost": total_cost,
    }


def format_basic_demo_report(
    inputs: Mapping[str, Any], result: Mapping[str, Any]
) -> str:
    """Format the isolated Stage 6 demonstration with conversion traceability."""
    lines = [
        "HydroSizer Basic Calculation — Stage 6",
        "Scope: manual demonstration only; no layer access",
        "",
        "Original inputs",
        f"  Flow: {_number(result['original_flow'])} {inputs['flow_unit']}",
        "  Internal diameter: "
        f"{_number(inputs['diameter_value'])} {inputs['diameter_unit']}",
        f"  Length: {_number(inputs['length_value'])} {inputs['length_unit']}",
        "  Unit cost: "
        f"{_number(inputs['unit_cost_value'])} {inputs['cost_length_unit']}",
        "",
        "SI conversions",
        f"  Signed flow: {_number(result['flow_m3_s_signed'])} m³/s",
        f"  Flow magnitude: {_number(result['flow_m3_s_magnitude'])} m³/s",
        f"  Internal diameter: {_number(result['diameter_m'])} m",
        f"  Length: {_number(result['length_m'])} m",
        f"  Unit cost: {_number(result['cost_per_m'])} currency/m",
        "",
        "Calculations",
        "  Velocity equation: V = 4 |Q| / (π Di²)",
        f"  Velocity: {_number(result['velocity_m_s'])} m/s",
        "  Segment cost equation: length × cost per metre",
        f"  Segment cost: {_number(result['segment_cost'])} currency units",
    ]
    if result["negative_flow"]:
        lines.extend(
            [
                "",
                "Warning: the original flow is negative. Its sign is preserved "
                "above; velocity uses the magnitude.",
            ]
        )
    elif result["zero_flow"]:
        lines.extend(["", "Warning: the original flow is zero."])
    return "\n".join(lines)


def _finite_value(value: float, name: str) -> float:
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
