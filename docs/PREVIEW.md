# Memory-only Sizing Preview

## Snapshot and Eligibility

Stage 13 creates a snapshot automatically after each Batch sizing run. It does
not rerun hydraulic calculations or reread project features. Rows with status
`sized` or `sized with warning` and a selected catalog product start as
included. `no solution` and `insufficient data` rows remain visible but are
ineligible for inclusion.

Starting another batch, changing the stored mapping, rerunning Data validation,
or reloading the plugin clears the snapshot. This prevents a later stage from
using results tied to obsolete mapped data.

## Filters and Inclusion

The review activity under **Sizing** combines free-text search with status and
inclusion filters.
Search covers pipe ID/FID, status, catalog ID, material/product codes, and
messages. **Include selected rows** and **Exclude selected rows** affect only
eligible rows highlighted in the table. These choices live only in plugin
memory.

## Map Selection

**Select selected rows on map** replaces the current selection on the mapped
pipe layer with the highlighted preview FIDs and zooms to them. It does not
open an edit session or change attributes or geometries.

## CSV Export and Safety Boundary

**Export displayed CSV** writes exactly the rows matching the current filters,
including eligibility/inclusion flags, identifiers, selected product, hydraulic
values, pressure, cost, controlling criterion, and messages. The file is UTF-8
with BOM and is atomically replaced through a temporary file in the destination
folder.

The review activity has no apply action. Layer edits, confirmation, rollback,
and audit records belong exclusively to the **Apply** step.
