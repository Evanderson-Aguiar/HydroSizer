"""Assisted, read-only detection of QGISRed options files."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import unquote, urlparse


DetectionResult = Dict[str, Any]


def detect_qgisred_options_from_project() -> DetectionResult:
    """Collect local project/layer paths and search for QGISRed options DBFs."""
    from qgis.core import QgsProject

    project = QgsProject.instance()
    layer_sources = [layer.source() for layer in project.mapLayers().values()]
    return find_options_candidates(project.absolutePath() or "", layer_sources)


def find_options_candidates(
    project_directory: str, layer_sources: Sequence[str]
) -> DetectionResult:
    """Find and rank `*_Options.dbf` files in relevant local directories.

    Only the project directory, local layer directories, and the parent of a
    directory named `Results` are inspected. No recursive filesystem scan is
    performed.
    """
    warnings: List[str] = []
    project_path = _existing_directory(project_directory)
    source_paths = [
        path
        for source in layer_sources
        for path in [_local_source_path(source)]
        if path is not None and path.is_file()
    ]

    directories = set()
    if project_path is not None:
        directories.add(project_path)
    for source_path in source_paths:
        directories.add(source_path.parent)
        if source_path.parent.name.casefold() == "results":
            directories.add(source_path.parent.parent)

    option_files = set()
    for directory in sorted(directories, key=lambda path: str(path).casefold()):
        try:
            for child in directory.iterdir():
                if child.is_file() and child.name.casefold().endswith(
                    "_options.dbf"
                ):
                    option_files.add(child.resolve())
        except OSError as error:
            warnings.append(f"Could not inspect directory {directory}: {error}")

    candidates = []
    for option_file in option_files:
        network_base = option_file.name[: -len("_Options.dbf")]
        score = 0
        reasons = []
        if project_path is not None and option_file.parent == project_path:
            score += 100
            reasons.append("options file is in the project directory")

        matching_sources = 0
        prefix = f"{network_base}_".casefold()
        for source_path in source_paths:
            same_network_directory = source_path.parent == option_file.parent
            result_subdirectory = (
                source_path.parent.name.casefold() == "results"
                and source_path.parent.parent == option_file.parent
            )
            if (same_network_directory or result_subdirectory) and (
                source_path.stem.casefold().startswith(prefix)
            ):
                matching_sources += 1
        if matching_sources:
            score += matching_sources * 10
            reasons.append(f"matches {matching_sources} loaded layer source(s)")

        candidates.append(
            {
                "path": str(option_file),
                "network_base": network_base,
                "score": score,
                "reasons": reasons,
            }
        )

    candidates.sort(
        key=lambda candidate: (
            -candidate["score"],
            candidate["path"].casefold(),
        )
    )
    recommended = candidates[0] if candidates else None
    return {
        "project_directory": str(project_path) if project_path else "",
        "inspected_directories": [
            str(path)
            for path in sorted(directories, key=lambda value: str(value).casefold())
        ],
        "candidates": candidates,
        "recommended": recommended,
        "warnings": warnings,
    }


def format_detection_result(result: DetectionResult) -> str:
    """Create a concise explanation of the assisted detection result."""
    lines = [
        f"Project directory: {result['project_directory'] or '<not available>'}",
        "Inspected directories:",
    ]
    if result["inspected_directories"]:
        lines.extend(
            f"  - {directory}" for directory in result["inspected_directories"]
        )
    else:
        lines.append("  <none>")

    lines.append(f"Options candidates: {len(result['candidates'])}")
    for candidate in result["candidates"]:
        reason = "; ".join(candidate["reasons"]) or "filename match"
        lines.append(
            f"  - {candidate['path']} [base={candidate['network_base']}; "
            f"score={candidate['score']}; {reason}]"
        )
    for warning in result["warnings"]:
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


def _existing_directory(value: str) -> Optional[Path]:
    if not value:
        return None
    path = Path(value)
    return path.resolve() if path.is_dir() else None


def _local_source_path(source: str) -> Optional[Path]:
    """Extract an existing local file from a QGIS provider source string."""
    if not source:
        return None
    raw_path = source.split("|", 1)[0]
    if raw_path.casefold().startswith("file:"):
        parsed = urlparse(raw_path)
        raw_path = unquote(parsed.path)
        if parsed.netloc:
            raw_path = f"//{parsed.netloc}{raw_path}"
        elif len(raw_path) > 2 and raw_path[0] == "/" and raw_path[2] == ":":
            raw_path = raw_path[1:]
    path = Path(raw_path)
    try:
        return path.resolve() if path.is_file() else None
    except OSError:
        return None
