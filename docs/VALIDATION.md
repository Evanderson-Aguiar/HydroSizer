# Data Validation

## Read-Only Contract

Stage 5 resolves the stored layer IDs again, confirms that sanitized sources and mapped fields still match, and requests only four attributes: pipe ID, pipe length, result ID, and flow. `QgsFeatureRequest.NoGeometry` is used. No edit session is started and no attribute is changed.

Problem highlighting is optional and user-triggered. It changes only the current QGIS feature selection and zooms spatial layers; it does not save edits.

## ID Rules

Text IDs are trimmed but remain case-sensitive. Integer IDs are converted to a canonical decimal string. Null, empty, boolean, non-integral, and incompatible ID values are errors. Pipe IDs must be unique.

Result duplicates are classified as:

- **error** when the same normalized ID has different valid flow values;
- **warning** when repeated records have an equivalent flow value.

A pipe without a result is an error because it cannot be processed. A result without a pipe is a warning because it does not prevent mapped pipes from being evaluated.

## Numeric Rules

Length must be numeric, finite, and greater than zero. It is read exclusively from the selected attribute.

Flow must be numeric and finite. Negative values are warnings: their original sign is retained, while later sizing will use the magnitude. Zero flow is a warning until its sizing behavior is explicitly implemented. Null, nonnumeric, NaN, and infinite values are errors.

## Observed Test Project

The controlled QGISRed result layer contains eight matched IDs. Its `Flow` field is null for all eight rows and must fail validation. `Flow_Sig` contains signed results and should pass with two warnings:

- ID `3`: `-1.6648 L/s`;
- ID `P1`: `-19.3102 L/s`.

HydroSizer does not switch fields automatically. The user must review the scenario and select `Flow_Sig` or another intended field, then store the mapping again.

## Report Status

- **PASS**: no errors or warnings;
- **PASS WITH WARNINGS**: no blocking errors;
- **FAIL**: at least one error.

The report retains issue code, severity, layer role, feature ID, original ID, selected field, original value, and an actionable message. Display is limited to 500 issues while counts and highlight FIDs cover the complete validation result.
