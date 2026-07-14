# Layer and Field Mapping

## Stage 4 Scope

Stage 4 builds a temporary, user-reviewable mapping without reading features or changing project data. The mapping is held only in plugin memory and is cleared when HydroSizer is reloaded.

Required selections are:

- spatial line layer containing the pipes;
- unique pipe ID field;
- numeric pipe length attribute;
- vector layer or non-spatial table containing link results;
- corresponding result ID field;
- numeric flow field.

The selected length is an attribute. HydroSizer does not use geometry length, `$length`, CRS-based length, or 3D length.

## Compatibility Filters

Pipe candidates are spatial line layers. Result candidates are vector layers or tables with at least one numeric field. Length and flow controls list numeric fields only. ID controls list text and integer fields; the result ID list is restricted to the same category as the selected pipe ID.

These filters improve the mapping but do not validate record values, uniqueness, nulls, or joins. Those checks belong to Stage 5.

## Assisted Suggestions

Suggestions use deterministic scores based on layer metadata and the real QGISRed structure observed during Stage 2. For the controlled test project the expected mapping is:

| Role | Selection |
| --- | --- |
| Pipe layer | `Tubulações` (`Network_Pipes.shp`) |
| Pipe ID | `Id` |
| Length | `Length` |
| Result layer | `Link Vazão` (`Results/Network_Base_Link.shp`) |
| Result ID | `Id` |
| Flow | `Flow` |

Exact matches receive preference, but every suggested selection can be changed. Changing a layer immediately rebuilds its compatible field lists.

## Temporary Configuration

When **Store temporary mapping** is clicked, HydroSizer records the selected layer IDs, names, sanitized sources, field names, project file, flow-unit code, headloss code, and UTC timestamp in memory. It does not serialize the configuration, access features, or start an edit session.
