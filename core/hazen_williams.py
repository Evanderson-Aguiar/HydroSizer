"""Single-segment Hazen–Williams candidate evaluation for Stage 8."""

import math
from typing import Any, Dict, Mapping, Optional, Sequence

from .basic_calculations import segment_cost, velocity_m_per_s
from .equations import (
    hazen_williams_total_headloss,
    hazen_williams_unit_headloss,
)
from .units import convert, to_si


def size_single_segment_hazen_williams(
    products: Sequence[Mapping[str, Any]],
    flow_value: float,
    flow_unit: str,
    length_value: float,
    length_unit: str,
    max_gradient_value: float,
    max_gradient_unit: str,
    max_gradient_enabled: bool = True,
) -> Dict[str, Any]:
    """Evaluate products and select the smallest admissible nominal diameter."""
    flow_original = _finite(flow_value, "flow")
    flow_m3_s = to_si(flow_original, "flow", flow_unit)
    length_m = to_si(length_value, "length", length_unit)
    max_gradient_m_m = (
        to_si(
            max_gradient_value,
            "headloss_gradient",
            max_gradient_unit,
        )
        if max_gradient_enabled
        else None
    )
    if length_m < 0:
        raise ValueError("length must not be negative")
    if max_gradient_m_m is not None and max_gradient_m_m <= 0:
        raise ValueError("maximum headloss gradient must be greater than zero")

    evaluated = [
        _evaluate_product(
            product,
            flow_m3_s,
            length_m,
            max_gradient_m_m,
        )
        for product in products
    ]
    admissible = [candidate for candidate in evaluated if candidate["admissible"]]
    admissible.sort(
        key=lambda candidate: (
            candidate["nominal_diameter_m"],
            candidate["internal_diameter_m"],
            candidate["catalog_id"],
        )
    )
    warnings = []
    if flow_original < 0:
        warnings.append(
            "Original flow is negative; its sign is preserved and calculations "
            "use the magnitude."
        )
    elif flow_original == 0:
        warnings.append(
            "Original flow is zero; a later stage must define the final sizing rule."
        )
    return {
        "flow_original": flow_original,
        "flow_unit": flow_unit,
        "flow_m3_s_signed": flow_m3_s,
        "flow_m3_s_magnitude": abs(flow_m3_s),
        "length_original": length_value,
        "length_unit": length_unit,
        "length_m": length_m,
        "max_gradient_original": max_gradient_value,
        "max_gradient_unit": max_gradient_unit,
        "max_gradient_m_m": max_gradient_m_m,
        "evaluated": evaluated,
        "selected": admissible[0] if admissible else None,
        "warnings": warnings,
    }


def format_hazen_williams_report(result: Mapping[str, Any]) -> str:
    """Create the Stage 8 single-segment calculation and justification report."""
    lines = [
        "HydroSizer Hazen–Williams Demonstration — Stage 8",
        "Scope: one manual segment; active catalog products; no layer access",
        "",
        "Equation",
        "  J = 10.67 × |Q|^1.852 / (C^1.852 × Di^4.8704)",
        "  hf = J × L",
        "  SI: Q [m³/s], Di [m], J [m/m], L [m], hf [m]",
        "",
        "Inputs",
        f"  Original flow: {_number(result['flow_original'])} {result['flow_unit']}",
        f"  Signed SI flow: {_number(result['flow_m3_s_signed'])} m³/s",
        f"  Flow magnitude: {_number(result['flow_m3_s_magnitude'])} m³/s",
        f"  Length: {_number(result['length_m'])} m",
        "  Maximum unit headloss: "
        f"{_number(result['max_gradient_original'])} "
        f"{result['max_gradient_unit']} "
        f"({_number(result['max_gradient_m_m'])} m/m)",
        "",
        "Selection strategy",
        "  1. Product must be active and hydraulically complete for H-W.",
        "  2. J must be less than or equal to the configured maximum.",
        "  3. Select smallest nominal diameter; then internal diameter; then ID.",
        "  Velocity and cost are informative, not admissibility criteria.",
        "",
        f"Candidates ({len(result['evaluated'])})",
    ]
    if not result["evaluated"]:
        lines.append("  <no active catalog products>")
    for candidate in result["evaluated"]:
        if candidate["status"] == "evaluated":
            label = "ADMISSIBLE" if candidate["admissible"] else "REJECTED"
            lines.extend(
                [
                    f"  [{label}] ID {candidate['catalog_id']} "
                    f"{candidate['material_code']}/{candidate['product_code']}",
                    "      DN: "
                    f"{_number(candidate['nominal_diameter'])} "
                    f"{candidate['nominal_diameter_unit']}; "
                    f"Di: {_number(candidate['internal_diameter'])} "
                    f"{candidate['internal_diameter_unit']}; "
                    f"C: {_number(candidate['hazen_williams_c'])}",
                    f"      Velocity: {_number(candidate['velocity_m_s'])} m/s; "
                    f"J: {_number(candidate['unit_headloss_m_m'])} m/m; "
                    f"J: {_number(candidate['unit_headloss_m_km'])} m/km; "
                    f"hf: {_number(candidate['total_headloss_m'])} m",
                    f"      Cost: {_optional_number(candidate['segment_cost'])}; "
                    f"reason: {candidate['reason']}",
                ]
            )
        else:
            lines.append(
                f"  [NOT EVALUATED] ID {candidate['catalog_id']} "
                f"{candidate['material_code']}/{candidate['product_code']}: "
                f"{candidate['reason']}"
            )

    lines.extend(["", "Selection"])
    selected = result["selected"]
    if selected is None:
        lines.append("  No admissible product was found in the active catalog.")
    else:
        lines.extend(
            [
                f"  Selected catalog ID: {selected['catalog_id']}",
                f"  Product: {selected['material_code']}/{selected['product_code']}",
                "  Justification: active and complete product; "
                f"J={_number(selected['unit_headloss_m_km'])} m/km is within "
                f"the limit and no admissible product has a smaller DN.",
            ]
        )
    if result["warnings"]:
        lines.extend(["", "Warnings"])
        lines.extend(f"  - {warning}" for warning in result["warnings"])
    lines.extend(
        [
            "",
            "Current limitations",
            "  No pressure check, combined criteria, network iteration, or layer update.",
        ]
    )
    return "\n".join(lines)


def _evaluate_product(
    product: Mapping[str, Any],
    flow_m3_s: float,
    length_m: float,
    max_gradient_m_m: Optional[float],
) -> Dict[str, Any]:
    candidate = {
        "catalog_id": int(product.get("catalog_id") or 0),
        "material_code": product.get("material_code") or "",
        "product_code": product.get("product_code") or "",
        "active": bool(product.get("active", True)),
        "admissible": False,
        "status": "not_evaluated",
        "reason": "",
    }
    if not candidate["active"]:
        candidate["reason"] = "product is inactive"
        return candidate

    required = (
        "nominal_diameter",
        "nominal_diameter_unit",
        "internal_diameter",
        "internal_diameter_unit",
        "hazen_williams_c",
    )
    missing = [field for field in required if product.get(field) in {None, ""}]
    if missing:
        candidate["reason"] = "missing " + ", ".join(missing)
        return candidate
    try:
        nominal_m = to_si(
            product["nominal_diameter"],
            "diameter",
            product["nominal_diameter_unit"],
        )
        internal_m = to_si(
            product["internal_diameter"],
            "diameter",
            product["internal_diameter_unit"],
        )
        coefficient = _finite(product["hazen_williams_c"], "Hazen–Williams C")
        gradient = hazen_williams_unit_headloss(
            flow_m3_s,
            internal_m,
            coefficient,
        )
        total_loss = hazen_williams_total_headloss(
            flow_m3_s,
            internal_m,
            coefficient,
            length_m,
        )
        velocity = velocity_m_per_s(flow_m3_s, internal_m)
    except ValueError as error:
        candidate["reason"] = str(error)
        return candidate

    cost_total: Optional[float] = None
    if product.get("cost_per_length") is not None and product.get(
        "cost_length_unit"
    ):
        try:
            cost_per_m = to_si(
                product["cost_per_length"],
                "cost_per_length",
                product["cost_length_unit"],
            )
            cost_total = segment_cost(length_m, cost_per_m)
        except ValueError:
            cost_total = None

    tolerance = (
        1.0e-12 * max(1.0, max_gradient_m_m)
        if max_gradient_m_m is not None
        else 0.0
    )
    admissible = (
        max_gradient_m_m is None
        or gradient <= max_gradient_m_m + tolerance
    )
    candidate.update(
        {
            "status": "evaluated",
            "admissible": admissible,
            "reason": (
                "unit headloss calculated; maximum limit is disabled"
                if max_gradient_m_m is None
                else "unit headloss is within the configured limit"
                if admissible
                else "unit headloss exceeds the configured limit"
            ),
            "nominal_diameter": float(product["nominal_diameter"]),
            "nominal_diameter_unit": product["nominal_diameter_unit"],
            "nominal_diameter_m": nominal_m,
            "internal_diameter": float(product["internal_diameter"]),
            "internal_diameter_unit": product["internal_diameter_unit"],
            "internal_diameter_m": internal_m,
            "hazen_williams_c": coefficient,
            "velocity_m_s": velocity,
            "unit_headloss_m_m": gradient,
            "unit_headloss_m_km": convert(
                gradient,
                "headloss_gradient",
                "m/m",
                "m/km",
            ),
            "total_headloss_m": total_loss,
            "segment_cost": cost_total,
        }
    )
    return candidate


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


def _optional_number(value: Optional[float]) -> str:
    return "<not available>" if value is None else _number(value)
