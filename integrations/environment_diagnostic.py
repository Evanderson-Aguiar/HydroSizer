"""Read-only collection and export of QGIS environment metadata."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Mapping, Optional


DiagnosticReport = Dict[str, Any]


def collect_environment_diagnostic() -> DiagnosticReport:
    """Collect project, layer, provider, source, and field metadata.

    The function does not iterate features, start edit sessions, or modify the
    project. QGIS imports remain local so formatting/export tests can run in a
    standard Python interpreter.
    """
    from qgis.core import Qgis, QgsProject, QgsRasterLayer, QgsVectorLayer

    project = QgsProject.instance()
    project_file = project.fileName() or ""
    project_title = project.title() or (
        Path(project_file).stem if project_file else "Untitled project"
    )
    warnings: List[str] = []
    layers: List[DiagnosticReport] = []

    sorted_layers = sorted(
        project.mapLayers().values(),
        key=lambda layer: (layer.name().casefold(), layer.id()),
    )
    for layer in sorted_layers:
        is_vector = isinstance(layer, QgsVectorLayer)
        is_raster = isinstance(layer, QgsRasterLayer)
        is_table = is_vector and not layer.isSpatial()
        if is_table:
            kind = "table"
        elif is_vector:
            kind = "vector"
        elif is_raster:
            kind = "raster"
        else:
            kind = "other"

        source = _sanitized_source(layer, warnings)
        fields: List[DiagnosticReport] = []
        if is_vector:
            for index, field in enumerate(layer.fields()):
                fields.append(
                    {
                        "name": field.name(),
                        "alias": layer.attributeDisplayName(index),
                        "type": field.typeName(),
                        "length": field.length(),
                        "precision": field.precision(),
                    }
                )

        layer_crs = layer.crs().authid() if layer.crs().isValid() else ""
        layers.append(
            {
                "id": layer.id(),
                "name": layer.name(),
                "kind": kind,
                "is_vector": is_vector,
                "is_table": is_table,
                "provider": layer.providerType(),
                "source": source,
                "source_sanitized": True,
                "valid": layer.isValid(),
                "crs": layer_crs,
                "fields": fields,
            }
        )

    counts = {
        "total": len(layers),
        "vector": sum(layer["kind"] == "vector" for layer in layers),
        "table": sum(layer["kind"] == "table" for layer in layers),
        "raster": sum(layer["kind"] == "raster" for layer in layers),
        "other": sum(layer["kind"] == "other" for layer in layers),
    }
    project_crs = project.crs().authid() if project.crs().isValid() else ""

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "hydrosizer_stage": 2,
        "qgis_version": getattr(Qgis, "QGIS_VERSION", "unknown"),
        "project": {
            "title": project_title,
            "file": project_file,
            "directory": project.absolutePath() or "",
            "crs": project_crs,
            "dirty": project.isDirty(),
        },
        "layer_counts": counts,
        "layers": layers,
        "warnings": warnings,
    }


def format_environment_diagnostic(report: Mapping[str, Any]) -> str:
    """Create a readable text representation of a diagnostic report."""
    project = report["project"]
    counts = report["layer_counts"]
    lines = [
        "HydroSizer — QGIS Environment Diagnostic",
        f"Generated (UTC): {report['generated_at_utc']}",
        f"QGIS: {report['qgis_version']}",
        "",
        "Project",
        f"  Title: {project['title']}",
        f"  File: {project['file'] or '<unsaved project>'}",
        f"  Directory: {project['directory'] or '<not available>'}",
        f"  CRS: {project['crs'] or '<not set>'}",
        f"  Modified: {'yes' if project['dirty'] else 'no'}",
        "",
        "Layer summary",
        f"  Total: {counts['total']}",
        f"  Spatial vector layers: {counts['vector']}",
        f"  Non-spatial tables: {counts['table']}",
        f"  Raster layers: {counts['raster']}",
        f"  Other layers: {counts['other']}",
        "",
        "Layers",
    ]

    layers = report["layers"]
    if not layers:
        lines.append("  <no layers loaded>")

    for number, layer in enumerate(layers, start=1):
        lines.extend(
            [
                f"  [{number}] {layer['name']}",
                f"      ID: {layer['id']}",
                f"      Type: {layer['kind']}",
                f"      Provider: {layer['provider'] or '<not available>'}",
                f"      Source: {layer['source'] or '<not available>'}",
                f"      CRS: {layer['crs'] or '<not set>'}",
                f"      Valid: {'yes' if layer['valid'] else 'no'}",
                f"      Fields ({len(layer['fields'])}):",
            ]
        )
        if not layer["fields"]:
            lines.append("        <none>")
        for field in layer["fields"]:
            alias = (
                f"; alias={field['alias']}"
                if field["alias"] and field["alias"] != field["name"]
                else ""
            )
            lines.append(
                "        - "
                f"{field['name']} ({field['type']}; "
                f"length={field['length']}; precision={field['precision']}"
                f"{alias})"
            )

    warnings = report.get("warnings", [])
    if warnings:
        lines.extend(["", "Warnings"])
        lines.extend(f"  - {warning}" for warning in warnings)

    return "\n".join(lines)


def write_diagnostic_json(
    report: Mapping[str, Any], target_path: Path
) -> Path:
    """Atomically write a UTF-8 diagnostic JSON file to an existing folder."""
    target = Path(target_path)
    if not target.parent.is_dir():
        raise FileNotFoundError(f"Destination folder does not exist: {target.parent}")
    if target.exists() and target.is_dir():
        raise IsADirectoryError(f"Destination is a directory: {target}")

    temporary_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(
                report,
                temporary_file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            temporary_file.write("\n")
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target)
    except Exception:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
        raise

    return target


def _sanitized_source(layer: Any, warnings: List[str]) -> str:
    """Return a public layer source while requesting password redaction."""
    public_source = getattr(layer, "publicSource", None)
    if callable(public_source):
        try:
            return public_source(True)
        except TypeError:
            try:
                return public_source()
            except Exception as error:
                warnings.append(
                    f"Could not read public source for layer {layer.name()}: {error}"
                )
                return ""
        except Exception as error:
            warnings.append(
                f"Could not read public source for layer {layer.name()}: {error}"
            )
            return ""

    warnings.append(f"Layer {layer.name()} does not expose a public source.")
    return ""
