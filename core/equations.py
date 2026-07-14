"""Hydraulic equations using documented SI inputs and outputs."""

import math
from typing import Optional, Tuple


HAZEN_WILLIAMS_SI_COEFFICIENT = 10.67
HAZEN_WILLIAMS_FLOW_EXPONENT = 1.852
HAZEN_WILLIAMS_DIAMETER_EXPONENT = 4.8704
STANDARD_GRAVITY_M_S2 = 9.80665
LAMINAR_REYNOLDS_LIMIT = 2300.0
TURBULENT_REYNOLDS_LIMIT = 4000.0


def hazen_williams_unit_headloss(
    flow_m3_s: float,
    internal_diameter_m: float,
    coefficient_c: float,
) -> float:
    """Return Hazen–Williams headloss gradient in m/m.

    Uses `J = 10.67 |Q|^1.852 / (C^1.852 Di^4.8704)` with flow in
    m³/s and real internal diameter in metres.
    """
    flow = _finite(flow_m3_s, "flow")
    diameter = _finite(internal_diameter_m, "internal diameter")
    coefficient = _finite(coefficient_c, "Hazen–Williams C")
    if diameter <= 0:
        raise ValueError("internal diameter must be greater than zero")
    if coefficient <= 0:
        raise ValueError("Hazen–Williams C must be greater than zero")
    if flow == 0:
        return 0.0
    return (
        HAZEN_WILLIAMS_SI_COEFFICIENT
        * abs(flow) ** HAZEN_WILLIAMS_FLOW_EXPONENT
        / (
            coefficient**HAZEN_WILLIAMS_FLOW_EXPONENT
            * diameter**HAZEN_WILLIAMS_DIAMETER_EXPONENT
        )
    )


def hazen_williams_total_headloss(
    flow_m3_s: float,
    internal_diameter_m: float,
    coefficient_c: float,
    length_m: float,
) -> float:
    """Return total Hazen–Williams headloss in metres."""
    length = _finite(length_m, "length")
    if length < 0:
        raise ValueError("length must not be negative")
    return hazen_williams_unit_headloss(
        flow_m3_s,
        internal_diameter_m,
        coefficient_c,
    ) * length


def reynolds_number(
    velocity_m_s: float,
    internal_diameter_m: float,
    kinematic_viscosity_m2_s: float,
) -> float:
    """Return `Re = |V| Di / nu` using SI inputs."""
    velocity = _finite(velocity_m_s, "velocity")
    diameter = _finite(internal_diameter_m, "internal diameter")
    viscosity = _finite(
        kinematic_viscosity_m2_s,
        "kinematic viscosity",
    )
    if diameter <= 0:
        raise ValueError("internal diameter must be greater than zero")
    if viscosity <= 0:
        raise ValueError("kinematic viscosity must be greater than zero")
    return abs(velocity) * diameter / viscosity


def relative_roughness(
    absolute_roughness_m: float,
    internal_diameter_m: float,
) -> float:
    """Return dimensionless relative roughness `epsilon / Di`."""
    roughness = _finite(absolute_roughness_m, "absolute roughness")
    diameter = _finite(internal_diameter_m, "internal diameter")
    if roughness < 0:
        raise ValueError("absolute roughness must not be negative")
    if diameter <= 0:
        raise ValueError("internal diameter must be greater than zero")
    return roughness / diameter


def swamee_jain_friction_factor(
    reynolds: float,
    relative_roughness_value: float,
) -> float:
    """Return the Darcy friction factor using turbulent Swamee–Jain."""
    reynolds_value = _finite(reynolds, "Reynolds number")
    roughness = _finite(relative_roughness_value, "relative roughness")
    if reynolds_value < TURBULENT_REYNOLDS_LIMIT:
        raise ValueError("Swamee–Jain requires Reynolds number >= 4000")
    if roughness < 0:
        raise ValueError("relative roughness must not be negative")
    logarithm = math.log10(
        roughness / 3.7 + 5.74 / reynolds_value**0.9
    )
    return 0.25 / logarithm**2


def darcy_friction_factor(
    reynolds: float,
    relative_roughness_value: float,
) -> Tuple[Optional[float], str]:
    """Return `(factor, regime)` with an explicit transition treatment.

    Below Re 2300, `f = 64/Re`. At and above Re 4000, Swamee–Jain is used.
    Between the limits, the two boundary factors are linearly interpolated.
    Zero flow has no meaningful factor and returns `(None, "stagnant")`.
    """
    reynolds_value = _finite(reynolds, "Reynolds number")
    roughness = _finite(relative_roughness_value, "relative roughness")
    if reynolds_value < 0:
        raise ValueError("Reynolds number must not be negative")
    if roughness < 0:
        raise ValueError("relative roughness must not be negative")
    if reynolds_value == 0:
        return None, "stagnant"
    if reynolds_value < LAMINAR_REYNOLDS_LIMIT:
        return 64.0 / reynolds_value, "laminar"
    if reynolds_value >= TURBULENT_REYNOLDS_LIMIT:
        return (
            swamee_jain_friction_factor(reynolds_value, roughness),
            "turbulent",
        )

    laminar_boundary = 64.0 / LAMINAR_REYNOLDS_LIMIT
    turbulent_boundary = swamee_jain_friction_factor(
        TURBULENT_REYNOLDS_LIMIT,
        roughness,
    )
    weight = (reynolds_value - LAMINAR_REYNOLDS_LIMIT) / (
        TURBULENT_REYNOLDS_LIMIT - LAMINAR_REYNOLDS_LIMIT
    )
    factor = laminar_boundary + weight * (
        turbulent_boundary - laminar_boundary
    )
    return factor, "transitional"


def darcy_weisbach_unit_headloss(
    velocity_m_s: float,
    internal_diameter_m: float,
    friction_factor: float,
) -> float:
    """Return `J = f V² / (2 g Di)` in m/m."""
    velocity = _finite(velocity_m_s, "velocity")
    diameter = _finite(internal_diameter_m, "internal diameter")
    factor = _finite(friction_factor, "friction factor")
    if diameter <= 0:
        raise ValueError("internal diameter must be greater than zero")
    if factor < 0:
        raise ValueError("friction factor must not be negative")
    return factor * velocity**2 / (2.0 * STANDARD_GRAVITY_M_S2 * diameter)


def darcy_weisbach_total_headloss(
    unit_headloss_m_m: float,
    length_m: float,
) -> float:
    """Return `hf = J L` in metres."""
    gradient = _finite(unit_headloss_m_m, "unit headloss")
    length = _finite(length_m, "length")
    if gradient < 0:
        raise ValueError("unit headloss must not be negative")
    if length < 0:
        raise ValueError("length must not be negative")
    return gradient * length


def bresse_diameter_m(flow_m3_s: float, coefficient: float) -> float:
    """Return the Bresse estimate `D = K sqrt(|Q|)` in metres.

    Flow is in m³/s. The configurable coefficient has the corresponding
    implicit SI dimensions and the estimate is not a hydraulic validation.
    """
    flow = _finite(flow_m3_s, "flow")
    factor = _finite(coefficient, "Bresse coefficient")
    if factor <= 0:
        raise ValueError("Bresse coefficient must be greater than zero")
    return factor * math.sqrt(abs(flow))


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
