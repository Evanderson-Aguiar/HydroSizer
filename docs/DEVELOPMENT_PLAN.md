# HydroSizer Technical Development Plan

## Current State and Goal

The repository began with only `AGENTS.md` and no valid Git metadata. Git was
initialized during Stage 0. Stages 1 through 15 were validated manually on
QGIS 3.44.12. Direct PDF export planned for Stage 16 was withdrawn by user
decision because browser printing of the approved HTML produced a better
result. Stage 17 translation was manually validated in QGIS. Stage 18
hardening and deterministic packaging are implemented and awaiting the manual
installation gate for the operational `1.0.0` release. Before that gate, a
pre-release UX revision replaced the
development-order interface with a five-step project workflow and separate
advanced tools. Development proceeds through explicit stage gates; a stage
starts only after the previous stage is manually validated and approved.

## Target Architecture

The repository will grow only when a stage requires it:

- `plugin.py`: QGIS lifecycle, actions, and controller wiring.
- `ui/`: Qt dialogs and widgets; no hydraulic calculations.
- `core/`: dependency-light units, equations, models, validation, and sizing.
- `integrations/`: read-only QGISRed detection plus QGIS layer adapters.
- `catalog/`: HydroSizer-owned SQLite catalog and CSV interchange.
- `audit/`: immutable run metadata and before/after change records.
- `reports/`: HTML and CSV calculation reports.
- `tests/unit/` and `tests/integration/`: pure Python and QGIS-runtime tests.

Internal calculations will use SI units. External values retain their original value, sign, field, and unit for reporting. Layer changes will be separated from preview generation and protected by confirmation, audit output, and rollback.

## Delivery Sequence and Gates

1. **Plugin shell (validated):** metadata, menu/toolbar action, non-modal dialog, version, basic diagnostic, lifecycle logging.
2. **QGIS environment diagnostic (validated):** inspect project, layers, providers, sanitized sources, and fields; export read-only JSON.
3. **QGISRed assisted detection (validated):** locate and inspect `*_Options.dbf` through an isolated read-only adapter with manual fallback.
4. **Layer/field mapping (validated):** user-reviewable pipe/result layer and field selection stored in memory.
5. **Input validation (validated):** IDs, joins, flow, length, missing/duplicate records; no edits.
6. **Units and basic calculations (validated):** central SI conversion, velocity, cost, reference tests.
7. **HydroSizer catalog (validated):** SQLite CRUD, validation, CSV import/export.
8. **Hazen–Williams (validated):** single-segment calculation and candidate test.
9. **Darcy–Weisbach (validated):** Reynolds, flow regimes, friction factor, losses.
10. **Combined criteria/selection (validated):** optional headloss, velocity,
    Bresse and diameter limits, project material filter, pressure, and
    deterministic tie-breaks without global catalog priority.
11. **End pressures (validated):** endpoint mapping, optional margins, and
    automatic per-pipe pressure-class checks during batch sizing.
12. **Batch sizing (validated):** all/selected features, progress, cancellation,
    memory-only results.
13. **Preview (validated):** filtering, map selection, inclusion controls, CSV export.
14. **Safe apply/audit (validated):** transactional edits, confirmation, rollback, CSV/JSON audit.
15. **HTML/CSV report (validated):** reproducible calculation memory and detailed data export.
16. **PDF (withdrawn):** use the browser print function on the approved HTML.
17. **pt_BR/English translation (validated):** automatic QGIS locale,
    translated UI/controller/calculation output, bilingual HTML memory.
18. **Hardening/package (final gate):** explicit distribution allowlist,
    deterministic ZIP, internal SHA-256 manifest, metadata/package validation,
    atomic replacement, guided five-step user workflow, separated advanced
    tools, and clean-profile installation test.

Each gate requires static checks, applicable automated tests, a QGIS manual test script, observed log messages, and user approval.

## Decisions

- Use `qgis.PyQt` exclusively and avoid compiled UI/resources until they add value.
- Use a non-modal dialog so Plugin Reloader can unload it safely.
- Use a file-based SVG icon to avoid generated resource code in Stage 1.
- Keep QGISRed DBFs read-only; HydroSizer data will live separately.
- Use only Python/QGIS/Qt standard capabilities unless a dependency is explicitly approved.
- Do not maintain a separate PDF renderer; print the approved HTML through the
  browser when PDF output is required.
- Keep English as the source-code and source-message language; add Qt translation in Stage 17.
- Use a plugin-owned `QTranslator` with a bundled pt_BR message catalog so the
  runtime does not depend on Qt Linguist build tools.
- Do not infer pipe/result relationships by row order; later joins use normalized explicit IDs.
- Treat the catalog as universal. Project material restrictions live only in
  the current in-memory criteria and never activate, deactivate, or reprioritize
  universal catalog records.

## Risks and Mitigations

- **QGIS/QGIS 4 API changes:** isolate compatibility code and test on QGIS 3.44 LTR before expanding support.
- **Unknown QGISRed DBF schema/encoding:** inspect real files read-only, expose raw diagnostics, and retain manual mapping.
- **Provider differences and non-file layers:** query provider capabilities; never assume Shapefile or a writable local path.
- **Unit ambiguity:** require reviewable units and central conversions with reference tests.
- **Partial or unintended edits:** maintain a strict preview/apply boundary, revalidate immediately before edits, and use transactions/rollback where available.
- **Plugin reload leaks:** own one dialog/action instance and explicitly close/delete them during unload.
