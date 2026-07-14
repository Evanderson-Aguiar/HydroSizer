# QGISRed Integration Notes

## Safety Boundary

HydroSizer treats QGISRed files as external, user-owned inputs. Detection and inspection are read-only. The plugin does not add the options DBF to the project, start an edit session, change attributes, or write `*_Options.dbf` and `*_Materials.dbf`.

## Assisted Detection

Stage 3 inspects only these local directories:

1. the current QGIS project directory;
2. directories containing loaded local layer sources;
3. the parent network directory when a source is inside `Results/`.

Files matching `*_Options.dbf` are ranked. A candidate in the project directory receives preference, followed by candidates whose network base matches loaded files such as `Network_Pipes.shp` or `Results/Network_Base_Link.shp`. The user can always choose a DBF manually.

## Observed QGISRed 0.18 Structure

The controlled test network supplied on 2026-07-12 contains `Network_Options.dbf` with 58 records and three text fields:

| Field | Type | Width |
| --- | --- | ---: |
| `Group` | String | 32 |
| `Name` | String | 32 |
| `Value` | String | 128 |

Relevant observed rows are:

- `Hydraulics / UNITS / LPS`
- `Hydraulics / HEADLOSS / H-W`

HydroSizer validates field names case-insensitively before interpreting records. `UNITS` is mapped only when it belongs to the `Hydraulics` group. Recognized headloss codes are `H-W` (Hazen–Williams), `D-W` (Darcy–Weisbach), and `C-M` (Chezy–Manning, detected but outside the first-version sizing scope).

## Fallback and Encoding

Unknown schemas, missing settings, unsupported codes, and provider errors produce visible warnings. Flow unit and headloss controls remain manually reviewable. QGIS/OGR performs the DBF decoding; the detected provider encoding is displayed. A file-size and modification-time check detects concurrent changes during inspection.
