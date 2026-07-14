# HydroSizer User Workflow

## Interface rationale

The main dialog follows the engineering task instead of the implementation
history. Fourteen equal-level technical tabs were replaced by five ordered
project steps. Diagnostic and single-pipe calculators remain available in a
separate **Advanced Tools** dialog, so they do not compete with required work.

The design follows the QGIS Human Interface Guidelines: related controls are
grouped, advanced options are separated, main tabs are not nested, long content
is vertically scrollable, operating-system dialog buttons use
`QDialogButtonBox`, and the initial window is limited to 960 x 580 pixels.
Wide result tables retain their own horizontal scrolling instead of widening
the complete workflow. See the official [QGIS Human Interface
Guidelines](https://docs.qgis.org/latest/en/docs/developers_guide/hig.html).

Navigation is intentionally not locked. A user may inspect later settings at
any time, while calculation actions continue to enforce their real data
prerequisites. This avoids a misleading wizard that appears to guarantee
readiness only because a page was visited.

## Normal project sequence

1. **Project**
   - Detect the QGISRed hydraulic scenario and review units and headloss method.
   - Map pipe and result layers plus ID, flow, and length fields.
   - Run read-only data validation and resolve every blocking error.
2. **Criteria**
   - Import or maintain the HydroSizer product catalog.
   - Keep all active materials or temporarily restrict this project to one
     material code; the universal catalog is not changed.
   - Define the hydraulic method and enable only the admissibility limits that
     apply to the project. Flow and length come from each mapped pipe.
   - Keep automatic product pressure verification enabled when pressure-class
     compliance is required. Review endpoint mapping and any optional margin.
3. **Sizing**
   - Process all mapped pipes or the selected pipe features in memory.
   - Filter the preview, inspect warnings or missing solutions, and include only
     the rows that belong to the proposed design.
   - Review the controlling criterion, warnings, and verification pressure in
     the pressure unit captured from the project endpoint mapping.
4. **Apply** — optional
   - Map existing destination fields and choose the audit directory.
   - Prepare the before/after plan, confirm it, and inspect pending QGIS edits.
   - Save layer edits only after review, then rerun the hydraulic simulation.
5. **Documents**
   - Complete project and document identification.
   - Export the final HTML calculation memory and detailed CSV after the reviewed
     hydraulic scenario is stable.

After applying new diameters, return to **Project**, load the updated QGISRed
results, validate again, and repeat the sizing cycle until the design converges.
Use **Previous** and **Next** only for navigation; they do not calculate, save,
or modify project data.

## Advanced tools

**Advanced Tools…** contains environment diagnostics, the unit calculator,
single-pipe Hazen–Williams and Darcy–Weisbach checks, and an optional pressure
diagnostic for one pipe/product pair. The normal batch automatically checks the
larger endpoint pressure for every pipe, so an individual check is not a
required dimensioning step.
