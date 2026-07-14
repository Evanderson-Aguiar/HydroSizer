"""Single-segment Darcy–Weisbach candidate evaluation for Stage 9."""

import math
from typing import Any, Dict, Mapping, Optional, Sequence

from .basic_calculations import segment_cost, velocity_m_per_s
from .equations import (
    darcy_friction_factor,
    darcy_weisbach_total_headloss,
    darcy_weisbach_unit_headloss,
    relative_roughness,
    reynolds_number,
)
from .units import convert, to_si


DEFAULT_WATER_KINEMATIC_VISCOSITY_M2_S = 1.004e-6


def size_single_segment_darcy_weisbach(
    products: Sequence[Mapping[str, Any]],
    flow_value: float,
    flow_unit: str,
    length_value: float,
    length_unit: str,
    max_gradient_value: float,
    max_gradient_unit: str,
    kinematic_viscosity_value: float,
    kinematic_viscosity_unit: str,
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
    viscosity_m2_s = to_si(
        kinematic_viscosity_value,
        "kinematic_viscosity",
        kinematic_viscosity_unit,
    )
    if length_m < 0:
        raise ValueError("length must not be negative")
    if max_gradient_m_m is not None and max_gradient_m_m <= 0:
        raise ValueError("maximum headloss gradient must be greater than zero")
    if viscosity_m2_s <= 0:
        raise ValueError("kinematic viscosity must be greater than zero")

    evaluated = [
        _evaluate_product(
            product,
            flow_m3_s,
            length_m,
            max_gradient_m_m,
            viscosity_m2_s,
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
            "Original flow is zero; friction factor is undefined and losses "
            "are reported as zero. A later stage must define the sizing rule."
        )
    if any(item.get("regime") == "transitional" for item in evaluated):
        warnings.append(
            "At least one candidate is in the transition zone; its friction "
            "factor uses the documented interpolation and requires review."
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
        "kinematic_viscosity_original": kinematic_viscosity_value,
        "kinematic_viscosity_unit": kinematic_viscosity_unit,
        "kinematic_viscosity_m2_s": viscosity_m2_s,
        "evaluated": evaluated,
        "selected": admissible[0] if admissible else None,
        "warnings": warnings,
    }


def format_darcy_weisbach_report(result: Mapping[str, Any]) -> str:
    """Create the Stage 9 calculation and candidate justification report."""
    lines = [
        "HydroSizer Darcy–Weisbach Demonstration — Stage 9",
        "Scope: one manual segment; active catalog products; no layer access",
        "",
        "Equations",
        "  V = 4 |Q| / (π Di²); Re = V Di / ν; relative roughness = ε / Di",
        "  Laminar Re < 2300: f = 64 / Re",
        "  Turbulent Re >= 4000: Swamee–Jain explicit approximation",
        "  Transition 2300 <= Re < 4000: linear boundary interpolation",
        "  J = f V² / (2 g Di); hf = J L; g = 9.80665 m/s²",
        "",
        "Inputs",
        f"  Original flow: {_number(result['flow_original'])} {result['flow_unit']}",
        f"  Signed SI flow: {_number(result['flow_m3_s_signed'])} m³/s",
        f"  Flow magnitude: {_number(result['flow_m3_s_magnitude'])} m³/s",
        f"  Length: {_number(result['length_m'])} m",
        "  Kinematic viscosity: "
        f"{_number(result['kinematic_viscosity_original'])} "
        f"{result['kinematic_viscosity_unit']} "
        f"({_number(result['kinematic_viscosity_m2_s'])} m²/s)",
        "  Maximum unit headloss: "
        f"{_number(result['max_gradient_original'])} "
        f"{result['max_gradient_unit']} "
        f"({_number(result['max_gradient_m_m'])} m/m)",
        "",
        "Selection strategy",
        "  Product must be active and include valid Di and absolute roughness.",
        "  J must be less than or equal to the configured maximum.",
        "  Select smallest nominal diameter; then internal diameter; then ID.",
        "  Velocity and cost are informative, not admissibility criteria.",
        "",
        f"Candidates ({len(result['evaluated'])})",
    ]
    if not result["evaluated"]:
        lines.append("  <no active catalog products>")
    for candidate in result["evaluated"]:
        if candidate["status"] != "evaluated":
            lines.append(
                f"  [NOT EVALUATED] ID {candidate['catalog_id']} "
                f"{candidate['material_code']}/{candidate['product_code']}: "
                f"{candidate['reason']}"
            )
            continue
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
                f"ε: {_number(candidate['absolute_roughness'])} "
                f"{candidate['roughness_unit']}",
                f"      V: {_number(candidate['velocity_m_s'])} m/s; "
                f"Re: {_number(candidate['reynolds'])}; "
                f"regime: {candidate['regime']}",
                "      Relative roughness: "
                f"{_number(candidate['relative_roughness'])}; "
                f"f: {_optional_number(candidate['friction_factor'])}",
                f"      J: {_number(candidate['unit_headloss_m_m'])} m/m; "
                f"J: {_number(candidate['unit_headloss_m_km'])} m/km; "
                f"hf: {_number(candidate['total_headloss_m'])} m",
                f"      Cost: {_optional_number(candidate['segment_cost'])}; "
                f"reason: {candidate['reason']}",
            ]
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
                "the limit and no admissible product has a smaller DN.",
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
    viscosity_m2_s: float,
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
        "absolute_roughness",
        "roughness_unit",
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
        roughness_m = to_si(
            product["absolute_roughness"],
            "diameter",
            product["roughness_unit"],
        )
        velocity = velocity_m_per_s(flow_m3_s, internal_m)
        reynolds = reynolds_number(velocity, internal_m, viscosity_m2_s)
        roughness_relative = relative_roughness(roughness_m, internal_m)
        factor, regime = darcy_friction_factor(reynolds, roughness_relative)
        gradient = (
            0.0
            if factor is None
            else darcy_weisbach_unit_headloss(velocity, internal_m, factor)
        )
        total_loss = darcy_weisbach_total_headloss(gradient, length_m)
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
            "absolute_roughness": float(product["absolute_roughness"]),
            "roughness_unit": product["roughness_unit"],
            "absolute_roughness_m": roughness_m,
            "relative_roughness": roughness_relative,
            "velocity_m_s": velocity,
            "reynolds": reynolds,
            "regime": regime,
            "friction_factor": factor,
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
