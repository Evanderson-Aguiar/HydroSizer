# Hydraulic Methods

## Stage 8: Hazen–Williams

HydroSizer evaluates one manually defined pipe segment with:

`J = 10.67 × |Q|^1.852 / (C^1.852 × Di^4.8704)`

`hf = J × L`

All calculations use SI internally: flow `Q` in m³/s, real internal diameter
`Di` in m, unit headloss `J` in m/m, length `L` in m, and total headloss
`hf` in m. `C` is the dimensionless catalog Hazen–Williams coefficient. The
flow sign is retained for reporting, while hydraulic loss uses its magnitude.

A numerical reference is `Q = 0.01 m³/s`, `C = 140`, and `Di = 0.10 m`,
which gives `J = 0.01659339675 m/m` and, for `L = 1000 m`,
`hf = 16.59339675 m`.

## Candidate Selection

The demonstration reads active products from the HydroSizer-owned SQLite
catalog. A product is evaluated only when nominal diameter, internal diameter,
their units, and `C` are present and valid. It is admissible when
`J <= Jmax`, including a small floating-point comparison tolerance.

The selected product is deterministic: smallest nominal diameter, then
smallest internal diameter, then lowest catalog ID. Velocity and segment cost
are reported for review but are not Stage 8 acceptance criteria.

## Stage 9: Darcy–Weisbach

HydroSizer calculates mean velocity, Reynolds number, relative roughness,
Darcy friction factor, unit headloss, and total headloss:

`Re = V Di / ν`

`εr = ε / Di`

`J = f V² / (2 g Di)` and `hf = J L`

Inputs use SI internally: `V` in m/s, `Di` and absolute roughness `ε` in m,
kinematic viscosity `ν` in m²/s, and `g = 9.80665 m/s²`. The default
water viscosity is `1.004×10⁻⁶ m²/s` (`1.004 mm²/s` or `cSt`),
representative of water near 20 °C, and is configurable in the interface.

Flow regimes and friction treatment are explicit:

- `Re = 0`: stagnant; friction factor undefined and losses zero.
- `0 < Re < 2300`: laminar, `f = 64/Re`.
- `2300 <= Re < 4000`: transition-zone warning and linear interpolation
  between the friction factors at the two regime boundaries.
- `Re >= 4000`: turbulent Swamee–Jain approximation,
  `f = 0.25/[log10(εr/3.7 + 5.74/Re⁰·⁹)]²`.

A turbulent reference with `Q = 0.01 m³/s`, `Di = 0.1 m`,
`ε = 0.0001 m`, and `ν = 1.004×10⁻⁶ m²/s` gives
`Re = 126816.6877`, `f = 0.02188263115`, `J = 0.01808710693 m/m`,
and `hf = 18.08710693 m` over 1000 m.

Darcy–Weisbach candidate selection uses the same Stage 8 deterministic order,
but requires valid catalog absolute roughness instead of Hazen–Williams `C`.

## Stage 10: Combined Criteria and Bresse Estimate

The project criteria can apply Hazen–Williams or Darcy–Weisbach and enable or
disable maximum unit headloss, maximum velocity, minimum nominal diameter,
minimum velocity, Bresse estimate, and product pressure-class verification.
Flow and length are not project criteria: batch sizing reads them for each pipe
from the validated QGISRed mapping.

The Bresse estimate is `D = K sqrt(|Q|)`, with `Q` in m³/s and `D` in m. Its
default coefficient is `K = 1.2`. When enabled, products below the theoretical
diameter are skipped, but every remaining product must still pass all enabled
hydraulic criteria. Bresse is an initial estimate, not full validation.

After eliminating inadmissible products, the deterministic default order is:

1. smallest nominal diameter;
2. lowest estimated segment cost when available;
3. highest allowable product pressure;
4. lowest stable catalog ID.

Each candidate reports failures, warnings, status, and a controlling criterion.
The controlling criterion is the required check with the highest limit-use
ratio. When pressure verification is enabled, batch sizing obtains the start
and end node pressures automatically, applies the configured margin to the
larger value, and rejects candidates with insufficient allowable pressure.

The project may temporarily restrict candidates to one material code. This
filter is held in plugin memory and does not alter the universal catalog.
Catalog schema version 1 still contains a legacy `priority` field for backward
compatibility, but current sizing ignores it.

## Current Limits

The single-pipe checks in Advanced Tools do not read the complete network or
change attributes. The normal project workflow uses validated batch inputs,
automatic endpoint mapping, preview, and a separately confirmed safe apply.
