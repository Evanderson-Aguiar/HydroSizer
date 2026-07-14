# Memory-only Batch Sizing

## Prerequisites

Sizing requires stored layer/field mapping and successful input validation
from the **Project** step in the current plugin session. The stored QGISRed
flow unit is used for every mapped result. Because the pipe-length attribute
does not carry unit metadata, its unit must be selected explicitly on the
**Sizing** step.

The run uses the current hydraulic and selection controls under **Criteria**.
Manual check values are replaced pipe by pipe. When pressure is enabled, the
current geometric endpoint-pressure mapping and margin supply each pipe's
verification pressure.

## Processing Modes

- **All mapped pipes:** processes every validated pipe record.
- **Selected pipe features only:** processes only QGIS-selected features from
  the mapped pipe layer and refuses an empty selection.

Pipes are processed in stable feature-ID order. Flow/result joins continue to
use normalized explicit IDs, never row order. Endpoint topology uses the
geometry relationship validated in Stage 11.

## Progress and Cancellation

A QGIS progress dialog reports the current pipe and includes **Cancel**.
Cancellation is cooperative between pipes. Already calculated rows remain in
plugin memory for inspection, but no partial layer update can exist because no
edit session or attribute write is started.

## Results and Limits

Each in-memory row retains pipe ID/FID, original signed flow, length, selected
catalog product, velocity, unit/total headloss, endpoint verification pressure,
cost, status, controlling criterion, and messages. Statuses are `sized`,
`sized with warning`, `no solution`, and `insufficient data`.

The text report displays at most 500 rows to keep the UI responsive; all
processed rows remain in memory. Results are cleared on plugin reload.
Filtering and inclusion are available in the second **Sizing** activity. Layer
changes remain isolated under **Apply**.
