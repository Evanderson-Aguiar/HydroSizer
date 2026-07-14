# Safe Layer Apply and Audit

## Explicit Destination Mapping

The **Apply** step writes only existing attributes on the mapped pipe layer. It never
creates fields and never edits QGISRed `*_Materials.dbf` or `*_Options.dbf`.
The user may map nominal diameter, internal diameter, hydraulic C/roughness,
pressure class, and material. At least one destination is required and the same
field cannot serve two outputs.
Mapped pipe ID and length fields are protected and cannot be selected as
destinations.

For the observed QGISRed schema, HydroSizer suggests `DN` for catalog nominal
diameter, `Diameter` for real internal diameter, and `RoughCoeff` for the
Hazen–Williams coefficient. Material is intentionally not selected by default:
it can be mapped only when every included product has an explicit
`qgisred_material_value`.

## Review and Last-moment Revalidation

**Prepare before/after apply plan** reads current IDs and mapped target values
without editing. It lists every old and proposed value and separates changes
from maintained rows. Changing preview inclusion or output mapping invalidates
the plan.

After the confirmation dialog, HydroSizer rereads pipe/result IDs, lengths,
flows, feature sets, layer source, target fields, and old target values. Any
difference from the batch snapshot blocks apply and requires a new validation
and sizing run.

## Edit Command and Rollback

All changed attributes are placed in one named QGIS edit command. If validation,
value conversion, an attribute update, or audit writing fails, the command is
destroyed. When HydroSizer started the edit session, that session is also rolled
back. Existing unrelated edit-buffer changes are not committed or rolled back.

On success, edits remain pending in the QGIS edit buffer. The user can inspect
and **Undo** them, or use **Save Layer Edits** to persist them. The network must
then be simulated manually again in QGISRed.

## Audit Bundle

Apply requires an audit directory. The suggested location is
`HydroSizer_Audit` beside a local pipe source, with project-directory fallback.
After explicit confirmation, the directory may be created. Each run writes a
unique UTF-8 CSV of old/new values and a JSON metadata file containing versions,
project/layer sources, mappings, units, criteria, counts, selection strategy,
and a SHA-256 hash of the selected catalog-product snapshot.
