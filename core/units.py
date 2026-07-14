"""Central unit conversion registry for HydroSizer.

Internal bases are m³/s for flow, m for length and diameter, Pa for pressure,
m/m for headloss gradient, m²/s for kinematic viscosity, and currency units
per metre for unit cost.
"""

import math
from typing import Dict, Tuple


METRES_PER_FOOT = 0.3048
METRES_PER_INCH = 0.0254
CUBIC_METRES_PER_US_GALLON = 0.003785411784
CUBIC_METRES_PER_CUBIC_FOOT = 0.028316846592
PASCALS_PER_METRE_WATER = 9806.65
PASCALS_PER_PSI = 6894.757293168

FLOW_UNITS = ("LPS", "CMS", "CMH", "GPM", "CFS")
LENGTH_UNITS = ("m", "km", "ft")
DIAMETER_UNITS = ("mm", "m", "in")
PRESSURE_UNITS = ("mca", "kPa", "bar", "psi")
HEADLOSS_GRADIENT_UNITS = ("m/m", "m/km", "ft/100 ft", "ft/1000 ft")
COST_LENGTH_UNITS = ("per m", "per ft")
KINEMATIC_VISCOSITY_UNITS = ("m²/s", "mm²/s", "cSt")


_UNIT_FACTORS: Dict[str, Dict[str, float]] = {
    "flow": {
        "m3/s": 1.0,
        "cms": 1.0,
        "l/s": 0.001,
        "lps": 0.001,
        "m3/h": 1.0 / 3600.0,
        "cmh": 1.0 / 3600.0,
        "gpm": CUBIC_METRES_PER_US_GALLON / 60.0,
        "cfs": CUBIC_METRES_PER_CUBIC_FOOT,
    },
    "length": {
        "m": 1.0,
        "km": 1000.0,
        "ft": METRES_PER_FOOT,
    },
    "diameter": {
        "m": 1.0,
        "mm": 0.001,
        "in": METRES_PER_INCH,
    },
    "pressure": {
        "pa": 1.0,
        "kpa": 1000.0,
        "bar": 100000.0,
        "mca": PASCALS_PER_METRE_WATER,
        "psi": PASCALS_PER_PSI,
    },
    "headloss_gradient": {
        "m/m": 1.0,
        "m/km": 0.001,
        "ft/100ft": 0.01,
        "ft/1000ft": 0.001,
    },
    "cost_per_length": {
        "perm": 1.0,
        "cost/m": 1.0,
        "perft": 1.0 / METRES_PER_FOOT,
        "cost/ft": 1.0 / METRES_PER_FOOT,
    },
    "kinematic_viscosity": {
        "m2/s": 1.0,
        "mm2/s": 1.0e-6,
        "cst": 1.0e-6,
    },
}


def convert(value: float, quantity: str, from_unit: str, to_unit: str) -> float:
    """Convert a finite value between units of the same quantity."""
    number = _finite_value(value, "value")
    quantity_key = quantity.strip().casefold()
    definitions = _UNIT_FACTORS.get(quantity_key)
    if definitions is None:
        raise ValueError(f"Unsupported quantity: {quantity}")
    from_key = _normalized_unit(from_unit)
    to_key = _normalized_unit(to_unit)
    if from_key not in definitions:
        raise ValueError(f"Unsupported {quantity} unit: {from_unit}")
    if to_key not in definitions:
        raise ValueError(f"Unsupported {quantity} unit: {to_unit}")
    base_value = number * definitions[from_key]
    return base_value / definitions[to_key]


def to_si(value: float, quantity: str, from_unit: str) -> float:
    """Convert to the documented HydroSizer SI base for a quantity."""
    base_units = {
        "flow": "m³/s",
        "length": "m",
        "diameter": "m",
        "pressure": "Pa",
        "headloss_gradient": "m/m",
        "cost_per_length": "per m",
        "kinematic_viscosity": "m²/s",
    }
    quantity_key = quantity.strip().casefold()
    if quantity_key not in base_units:
        raise ValueError(f"Unsupported quantity: {quantity}")
    return convert(value, quantity_key, from_unit, base_units[quantity_key])


def supported_units(quantity: str) -> Tuple[str, ...]:
    """Return normalized accepted unit tokens for diagnostics and tests."""
    definitions = _UNIT_FACTORS.get(quantity.strip().casefold())
    if definitions is None:
        raise ValueError(f"Unsupported quantity: {quantity}")
    return tuple(definitions)


def _normalized_unit(unit: str) -> str:
    return (
        unit.strip()
        .casefold()
        .replace("³", "3")
        .replace("²", "2")
        .replace(" ", "")
        .replace("_", "")
    )


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
