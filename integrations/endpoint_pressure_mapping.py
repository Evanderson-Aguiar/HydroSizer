"""Reviewable layer/field suggestions for Stage 11 endpoint pressures."""

import re
from typing import Any, Dict, Mapping, Optional, Sequence
import unicodedata


def suggest_endpoint_pressure_mapping(
    inventory: Sequence[Mapping[str, Any]],
) -> Dict[str, str]:
    """Suggest observed QGISRed pipe endpoints and node pressure results."""
    pipe_layers = [layer for layer in inventory if layer["is_line"]]
    pipe = _best(pipe_layers, _pipe_score)
    node_layers = [
        layer
        for layer in inventory
        if layer["id"] != (pipe["id"] if pipe else "")
        and any(field["numeric"] for field in layer["fields"])
    ]
    nodes = _best(node_layers, _node_result_score)
    pipe_id = _suggest_field(pipe, ("id", "pipe_id", "dc_id"), {"text", "integer"})
    node_id = _suggest_field(nodes, ("id", "node_id", "dc_id"), {"text", "integer"})
    pressure = _suggest_field(
        nodes,
        ("pressure", "pressao", "press", "pressure_m"),
        {"numeric", "integer"},
    )
    return {
        "pipe_layer_id": pipe["id"] if pipe else "",
        "pipe_id_field": pipe_id,
        "node_layer_id": nodes["id"] if nodes else "",
        "node_id_field": node_id,
        "pressure_field": pressure,
    }


def endpoint_fields(
    layer: Optional[Mapping[str, Any]],
    numeric: bool,
) -> list:
    if layer is None:
        return []
    categories = {"numeric", "integer"} if numeric else {"text", "integer"}
    return [
        field for field in layer["fields"] if field["category"] in categories
    ]


def _pipe_score(layer: Mapping[str, Any]) -> int:
    layer_name = _normalized(layer["name"])
    source = layer["source"].replace("\\", "/").casefold()
    score = 10
    if layer_name in {"pipes", "pipe", "tubulacoes", "tubulacao"}:
        score += 100
    if source.endswith("_pipes.shp"):
        score += 80
    return score


def _node_result_score(layer: Mapping[str, Any]) -> int:
    names = {_normalized(field["name"]) for field in layer["fields"]}
    name = _normalized(layer["name"])
    source = layer["source"].replace("\\", "/").casefold()
    score = 0
    if "pressure" in names or "pressao" in names:
        score += 180
    if "node" in name or "pressao" in name or "pressure" in name:
        score += 80
    if "/results/" in source:
        score += 60
    return score


def _suggest_field(layer, preferences, categories) -> str:
    if layer is None:
        return ""
    available = {
        _normalized(field["name"]): field["name"]
        for field in layer["fields"]
        if field["category"] in categories
    }
    for preferred in preferences:
        if preferred in available:
            return available[preferred]
    return ""


def _best(layers, score):
    if not layers:
        return None
    return sorted(
        layers,
        key=lambda layer: (-score(layer), layer["name"].casefold(), layer["id"]),
    )[0]


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9_]+", "", plain.casefold())
