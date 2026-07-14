# Endpoint Pressure Verification

## Topology Relationship

The current QGISRed project stores no endpoint IDs in `Tubulações`; its pipe
schema ends at fields such as `Tag` and `Descrip`. Therefore, Stage 11 defaults
to a geometric relationship: the first and last vertices of each pipe are
matched to point geometries in the node-result layer within a configurable
tolerance.

The observed mapping is `Tubulações.Id` to `Node Pressão.Id` and `Pressure`,
using line endpoints and node-result point locations.

## Read-only Geometry Matching

Geometry mode requests pipe ID, node ID, pressure, pipe geometries, and node
geometries. Node coordinates are transformed to the pipe CRS when necessary.
The default tolerance is `0.01` pipe-CRS units; in the observed EPSG:31985
project this means `0.01 m`. No edit session is started.

The verifier rejects missing geometries, endpoints with no node inside the
tolerance, and endpoints matching more than one distinct node ID.

## Verification Rule

Pressures are converted to pascals and the base value is:

`Pverification_base = max(Pinitial, Pfinal)`

One optional margin can then be applied:

- multiplicative: `Pverification = Pbase × factor`, with `factor >= 1`; or
- additive: `Pverification = Pbase + margin`.

Both margins are disabled by default and cannot be combined. A selected active
catalog product passes when its allowable pressure is greater than or equal to
the final verification pressure, within numerical tolerance.

## Validation and Assumptions

The verifier also rejects duplicate pipe IDs, missing node results, conflicting
duplicate pressures, nonnumeric pressures, and products without a valid
pressure rating. Equivalent duplicate node results produce a warning.

The check assumes nodes exist at high, low, and other critical profile points.
It uses the displayed result state and is not a transient or water-hammer
analysis. Stage 11 evaluates one pipe; batch processing belongs to Stage 12.
