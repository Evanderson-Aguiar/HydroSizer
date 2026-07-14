# Units and Basic Calculations

## Internal Bases

HydroSizer converts inputs before calculation. The internal bases are:

| Quantity | Internal base |
| --- | --- |
| Flow | `m³/s` |
| Length | `m` |
| Diameter | `m` |
| Pressure | `Pa` |
| Headloss gradient | `m/m` |
| Kinematic viscosity | `m²/s` |
| Unit cost | currency per `m` |

Conversion logic belongs only to `core/units.py`. UI code and hydraulic equations must not contain independent conversion factors.

## Supported Units

- Flow: `LPS`/`L/s`, `CMS`/`m³/s`, `CMH`/`m³/h`, `GPM`, `CFS`.
- Length: `m`, `km`, `ft`.
- Diameter: `mm`, `m`, `in`.
- Pressure: `mca`, `kPa`, `bar`, `psi` (`Pa` is also accepted internally).
- Headloss gradient: `m/m`, `m/km`, `ft/100 ft`, `ft/1000 ft`.
- Kinematic viscosity: `m²/s`, `mm²/s`, or `cSt`.
- Unit cost: currency per metre or per foot.

Documented constants include `1 ft = 0.3048 m`, `1 in = 0.0254 m`, `1 US gal = 0.003785411784 m³`, `1 ft³ = 0.028316846592 m³`, `1 psi = 6894.757293168 Pa`, and the conventional water head `1 mca = 9806.65 Pa`.

## Velocity

Mean velocity uses the real internal diameter:

`V = 4 |Q| / (π Di²)`

Inputs are `Q` in `m³/s` and `Di` in `m`; the result is `m/s`. The original flow sign remains available for reporting, while velocity uses its magnitude. Diameter must be finite and greater than zero.

Reference case:

- `Q = 10 L/s = 0.01 m³/s`;
- `Di = 100 mm = 0.1 m`;
- `V = 1.2732395447351625 m/s`.

## Segment Cost

`segment cost = length in metres × cost per metre`

Reference case: `1000 m × 50 currency/m = 50000 currency units`. Cost is an estimate without currency conversion, excavation, accessories, energy, maintenance, or lifecycle components.

## Demonstration Boundary

The Stage 6 dialog accepts manual values only. It does not read the stored mapping, iterate features, size pipes, calculate headloss, or change project data.
