"""Stage 17 bilingual hydraulic calculation memory and detailed worksheet."""

import csv
from datetime import datetime
from html import escape
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Optional

try:
    from ..core.units import convert, to_si
except ImportError:  # Descoberta isolada dos testes a partir da raiz.
    from core.units import convert, to_si


CSV_FIELDS = (
    "incluido",
    "elegivel",
    "id_trecho",
    "fid_trecho",
    "situacao_dimensionamento",
    "situacao_aplicacao",
    "comprimento_original",
    "unidade_comprimento",
    "comprimento_m",
    "vazao_original",
    "unidade_vazao",
    "vazao_utilizada_m3_s",
    "material",
    "produto",
    "id_catalogo",
    "diametro_nominal",
    "unidade_diametro_nominal",
    "diametro_interno",
    "unidade_diametro_interno",
    "velocidade_m_s",
    "metodo_hidraulico",
    "coeficiente_hazen_williams",
    "rugosidade_absoluta",
    "unidade_rugosidade",
    "numero_reynolds",
    "regime_escoamento",
    "fator_atrito",
    "perda_carga_unitaria_m_km",
    "perda_carga_trecho_m",
    "no_inicial",
    "no_final",
    "pressao_inicial_original",
    "pressao_final_original",
    "unidade_pressao_nodal",
    "pressao_inicial_pa",
    "pressao_final_pa",
    "pressao_base_verificacao_pa",
    "tipo_margem",
    "fator_seguranca",
    "margem_aditiva_original",
    "unidade_margem_aditiva",
    "margem_aditiva_pa",
    "pressao_verificacao_pa",
    "classe_pressao",
    "pressao_admissivel_original",
    "unidade_pressao_produto",
    "pressao_admissivel_pa",
    "custo_unitario_comprimento",
    "unidade_custo_comprimento",
    "custo_trecho",
    "criterio_controlador",
    "observacoes",
)


def build_calculation_memory(
    batch_result: Mapping[str, Any],
    preview: Mapping[str, Any],
    metadata: Mapping[str, Any],
    applied_plan: Optional[Mapping[str, Any]] = None,
) -> dict:
    """Consolidar um retrato reproduzível do dimensionamento do projeto."""
    if not batch_result.get("memory_only") or not preview.get("memory_only"):
        raise ValueError(
            "a memória de cálculo exige resultados de lote e prévia em memória"
        )
    batch_rows = {int(row["pipe_fid"]): row for row in batch_result["rows"]}
    if len(batch_rows) != len(batch_result["rows"]):
        raise ValueError("o lote contém FIDs de tubulação duplicados")
    apply_by_fid = {}
    if applied_plan:
        apply_by_fid = {
            int(row["pipe_fid"]): row["status"] for row in applied_plan["rows"]
        }

    rows = []
    for preview_row in preview["rows"]:
        fid = int(preview_row["pipe_fid"])
        if fid not in batch_rows:
            raise ValueError(f"o FID {fid} da prévia não pertence ao lote")
        row = dict(batch_rows[fid])
        row["included"] = bool(preview_row["included"])
        row["eligible"] = bool(preview_row["eligible"])
        row["flow_used_m3_s"] = _converted_magnitude(
            row.get("flow_original"), "flow", row.get("flow_unit")
        )
        row["length_m"] = _converted(
            row.get("length_original"), "length", row.get("length_unit")
        )
        row["allowable_pressure_pa"] = _converted(
            row.get("max_allowable_pressure"),
            "pressure",
            row.get("pressure_unit"),
        )
        if fid in apply_by_fid:
            row["apply_status"] = (
                "applied" if apply_by_fid[fid] == "change" else "maintained"
            )
        elif row["included"]:
            row["apply_status"] = "proposed"
        else:
            row["apply_status"] = "excluded"
        rows.append(row)

    generated = metadata.get("generated_at") or datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    model = {
        "metadata": dict(metadata),
        "generated_at": generated,
        "criteria": dict(batch_result.get("criteria", {})),
        "selection_mode": batch_result.get("selection_mode", ""),
        "cancelled": bool(batch_result.get("cancelled")),
        "rows": rows,
    }
    model["summary"] = _summary(rows, applied_plan)
    model["quantities"] = _quantities(rows)
    model["critical_results"] = _critical_results(rows, model["metadata"])
    return model


def export_calculation_memory(html_path: Path, model: Mapping[str, Any]) -> dict:
    """Substituir com segurança o par HTML/CSV de mesmo nome-base."""
    target_html = Path(html_path)
    if target_html.suffix.casefold() != ".html":
        target_html = target_html.with_suffix(".html")
    target_csv = target_html.with_suffix(".csv")
    if not target_html.parent.is_dir():
        raise FileNotFoundError(
            f"a pasta de destino não existe: {target_html.parent}"
        )
    html_temp = _temporary_path(target_html.parent, target_html.name)
    csv_temp = _temporary_path(target_html.parent, target_csv.name)
    backups = {}
    try:
        html_temp.write_text(render_calculation_html(model), encoding="utf-8")
        _write_csv(csv_temp, model)
        for target in (target_html, target_csv):
            if target.exists():
                backup = _temporary_path(target.parent, target.name)
                backup.unlink()
                os.replace(target, backup)
                backups[target] = backup
        os.replace(html_temp, target_html)
        os.replace(csv_temp, target_csv)
        for backup in backups.values():
            backup.unlink()
    except Exception:
        for path in (html_temp, csv_temp):
            if path.exists():
                path.unlink()
        for target in (target_html, target_csv):
            if target.exists():
                target.unlink()
            backup = backups.get(target)
            if backup is not None and backup.exists():
                os.replace(backup, target)
        raise
    return {
        "html_path": target_html,
        "csv_path": target_csv,
        "rows": len(model["rows"]),
    }


def render_calculation_html(model: Mapping[str, Any]) -> str:
    """Render the engineering calculation memory in the selected UI language."""
    metadata = model["metadata"]
    summary = model["summary"]
    project_title = metadata.get("project_title") or metadata.get("project_name")
    project_title = project_title or "Empreendimento não identificado"
    html = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Memória de cálculo hidráulico — {escape(str(project_title))}</title>
<style>
@page{{size:A4;margin:18mm 15mm 17mm}}
*{{box-sizing:border-box}} body{{font-family:Arial,Helvetica,sans-serif;color:#202124;
font-size:10.5pt;line-height:1.45;margin:0;background:#eceff1}}
.documento{{max-width:210mm;margin:12px auto;background:#fff;padding:18mm 15mm;
box-shadow:0 1px 8px #999}} .capa{{min-height:230mm;display:flex;flex-direction:column;
justify-content:space-between;border-top:8px solid #165b3a;padding-top:12mm}}
.capa h1{{font-size:25pt;text-transform:uppercase;letter-spacing:.5px;margin:25mm 0 4mm}}
.capa h2{{font-size:15pt;color:#165b3a;margin:0;border:0;counter-increment:none}}
.capa h2::before,.anexo h2::before{{content:none}} .anexo h2{{counter-increment:none}}
.subtitulo{{font-size:12pt}}
.controle{{border:1px solid #333;padding:8mm;margin-top:20mm}}
h2{{font-size:15pt;color:#165b3a;border-bottom:2px solid #165b3a;padding-bottom:2mm;
margin-top:12mm}} h2::before{{content:none}}
h3{{font-size:11.5pt;color:#333;margin-top:7mm}}
table{{border-collapse:collapse;width:100%;margin:3mm 0 6mm;font-size:9pt}}
th,td{{border:1px solid #8a8a8a;padding:2mm;text-align:left;vertical-align:top}}
th{{background:#e5eee9;color:#173c2b}} .numero{{text-align:right;white-space:nowrap}}
.nota{{border-left:4px solid #b36b00;background:#fff5df;padding:4mm;margin:4mm 0}}
.formula{{font-family:"Courier New",monospace;background:#f4f4f4;padding:3mm;
margin:2mm 0}} .rodape{{color:#555;font-size:8.5pt}}
.quebra{{break-before:page;page-break-before:always}} .sem-quebra{{break-inside:avoid}}
@media print{{body{{background:#fff}}.documento{{box-shadow:none;margin:0;max-width:none;padding:0}}
.capa{{min-height:255mm}} tr{{break-inside:avoid}}}}
</style></head><body><main class="documento">
<section class="capa">
<div><div class="subtitulo">{escape(str(metadata.get('client') or 'Contratante não informado'))}</div>
<h1>Memória de cálculo hidráulico</h1>
<h2>Rede de distribuição de água</h2>
<p class="subtitulo">{escape(str(project_title))}</p></div>
<div class="controle">{_definition_table((
    ('Localidade', metadata.get('location') or 'Não informada'),
    ('Fase do projeto', metadata.get('project_stage') or 'Não informada'),
    ('Código do documento', metadata.get('document_code') or 'Não informado'),
    ('Revisão', metadata.get('revision') or '00'),
    ('Responsável técnico', metadata.get('responsible') or 'Não informado'),
    ('Registro profissional', metadata.get('professional_registration') or 'Não informado'),
    ('Data de emissão', _display_datetime(model['generated_at'])),
))}</div>
<p class="rodape">Documento gerado para revisão, complementação e assinatura do responsável técnico.</p>
</section>

<section class="quebra"><h2>1 Objeto e escopo</h2>
<p>Esta memória apresenta os critérios, as premissas, o procedimento de cálculo e os
resultados do dimensionamento hidráulico das tubulações da rede de distribuição de água do
empreendimento <strong>{escape(str(project_title))}</strong>.</p>
<p>{escape(str(metadata.get('project_description') or
    'A concepção geral do empreendimento não foi informada no formulário de emissão.'))}</p>
<p>O escopo automatizado abrange a verificação trecho a trecho, com vazões provenientes do
modelo hidráulico identificado nesta memória, seleção de produtos do catálogo e verificação da
pressão de serviço do produto. A análise não determina demandas, não redistribui vazões e
não substitui a simulação hidráulica global da rede.</p></section>

<section><h2>3 Dados de entrada e premissas</h2>
<h3>3.1 Identificação do cenário hidráulico</h3>
{_definition_table((
    ('Cenário analisado', metadata.get('hydraulic_scenario') or 'Não informado'),
    ('Método de perda de carga', _method_name(metadata.get('hydraulic_method'))),
    ('Unidade da vazão de origem', metadata.get('flow_unit')),
    ('Unidade do comprimento de origem', metadata.get('length_unit')),
    ('Unidade da pressão nodal', _project_pressure_unit(model)),
    ('Sistema de referência do projeto', metadata.get('project_crs')),
))}</section>

<section><h2>4 Critérios de dimensionamento</h2>{_criteria_table(model['criteria'], metadata)}
<p>A escolha exige atendimento simultâneo a todos os critérios obrigatórios habilitados.
Entre os produtos admissíveis, a ordenação considera menor DN, menor custo disponível,
maior pressão admissível e, por fim, o identificador estável do catálogo.</p></section>

<section><h2>5 Formulação hidráulica</h2>{_methodology(metadata, model['criteria'])}</section>

<section><h2>6 Síntese do dimensionamento</h2>{_summary_table(summary)}
{_critical_table(model['critical_results'])}
<h3>6.2 Quantitativos de tubulações dimensionadas</h3>{_quantities_table(model['quantities'])}
<p class="rodape">Os quantitativos consideram apenas os trechos incluídos na prévia. Custos
 são estimativos e permanecem sem unidade monetária quando ela não foi definida no catálogo.</p></section>

<section class="quebra anexo"><h2>Anexo A — Planilha de dimensionamento por trecho</h2>
{_sizing_tables(model)}</section>

<section class="quebra anexo"><h2>Anexo B — Rastreabilidade computacional</h2>
{_definition_table((
    ('Ferramenta de cálculo', 'HydroSizer'),
    ('Versão do HydroSizer', metadata.get('hydrosizer_version')),
    ('Versão do QGIS', metadata.get('qgis_version')),
    ('Versão do QGISRed', _qgisred_version(metadata.get('qgisred_version'))),
))}
</section>
</main></body></html>"""
    return _localized_report_html(html, metadata)


def _criteria_table(criteria, metadata):
    min_mode = {
        "disabled": "Não aplicado",
        "warning": "Alerta, sem rejeição",
        "required": "Obrigatório",
    }.get(criteria.get("min_velocity_mode"), "Não informado")
    minimum_velocity = (
        "Não aplicado"
        if criteria.get("min_velocity_mode") == "disabled"
        else f"{min_mode}; {_value_unit(criteria.get('min_velocity_m_s'), 'm/s')}"
    )
    rows = (
        ("Materiais admitidos no projeto", (
            criteria.get("material_filter") or "Todos os materiais ativos")),
        ("Perda de carga unitária máxima", _enabled_value(
            criteria.get("max_gradient_enabled", True),
            criteria.get("max_gradient_value"), criteria.get("max_gradient_unit"))),
        ("Velocidade máxima", _enabled_value(
            criteria.get("max_velocity_enabled"), criteria.get("max_velocity_m_s"), "m/s")),
        ("Velocidade mínima", minimum_velocity),
        ("Diâmetro nominal mínimo", _enabled_value(
            criteria.get("min_nominal_enabled"), criteria.get("min_nominal_value"),
            criteria.get("min_nominal_unit"))),
        ("Estimativa inicial de Bresse", _enabled_value(
            criteria.get("bresse_enabled"), criteria.get("bresse_coefficient"), "coeficiente K")),
        ("Verificação da classe de pressão", _yes_no(criteria.get("pressure_enabled"))),
        ("Margem de verificação da pressão", _pressure_margin(metadata)),
        ("Viscosidade cinemática", _value_unit(
            criteria.get("kinematic_viscosity_value"), criteria.get("kinematic_viscosity_unit"))),
    )
    return _definition_table(rows)


def _methodology(metadata, criteria):
    common = """<h3>5.1 Continuidade das unidades e velocidade</h3>
<div class="formula">Q [m³/s]; D<sub>i</sub> [m]; L [m]; g = 9,80665 m/s²<br>
v = 4 |Q| / (π D<sub>i</sub>²)</div>"""
    if metadata.get("hydraulic_method") == "H-W":
        method = """<h3>5.2 Equação de Hazen–Williams</h3>
<div class="formula">J = 10,67 |Q|<sup>1,852</sup> /
(C<sup>1,852</sup> D<sub>i</sub><sup>4,8704</sup>)<br>
h<sub>f</sub> = J L</div>
<p>O coeficiente C e o diâmetro interno real são obtidos do produto do catálogo.
Para apresentação, J é convertido de m/m para m/km.</p>"""
    else:
        method = """<h3>5.2 Equação de Darcy–Weisbach</h3>
<div class="formula">Re = v D<sub>i</sub> / ν &nbsp;&nbsp; ε<sub>r</sub> = ε/D<sub>i</sub><br>
J = f v² / (2 g D<sub>i</sub>) &nbsp;&nbsp; h<sub>f</sub> = J L</div>
<p>Para regime laminar, f = 64/Re. Para regime turbulento é utilizada a aproximação
explícita de Swamee–Jain. Na faixa de transição é aplicada interpolação entre os limites,
com indicação para revisão técnica.</p>"""
    pressure = """<h3>5.3 Verificação de pressão do produto</h3>
<div class="formula">P<sub>base</sub> = máx(P<sub>nó inicial</sub>, P<sub>nó final</sub>)<br>
P<sub>verificação</sub> = P<sub>base</sub> × FS &nbsp; ou &nbsp;
P<sub>base</sub> + margem aditiva</div>
<p>O produto é admissível quando a pressão de verificação não supera sua pressão máxima
admissível. Esta checagem é de resistência do produto e não substitui a verificação das
pressões mínimas e máximas de serviço em todos os nós e cenários da rede.</p>""" if criteria.get("pressure_enabled") else ""
    cost = """<h3>5.4 Custo indicativo</h3>
<div class="formula">Custo do trecho = comprimento convertido para metro × custo por metro</div>
<p>O custo participa do desempate somente quando disponível e não constitui orçamento da obra.</p>"""
    return common + method + pressure + cost


def _summary_table(summary):
    return _definition_table((
        ("Total de trechos", summary["included_count"]),
        ("Extensão total", _value_unit(summary["included_length_m"], "m")),
        ("Custo total estimado", _optional_pt(summary["total_cost"])),
    ))


def _critical_table(critical):
    if not critical:
        return "<h3>6.1 Valores críticos</h3><p>Não há resultados hidráulicos válidos.</p>"
    body = "".join(
        f"<tr><td>{escape(item['label'])}</td><td>{escape(str(item['pipe_id']))}</td>"
        f"<td class=\"numero\">{escape(item['display'])}</td></tr>"
        for item in critical
    )
    return ("<h3>6.1 Valores críticos entre os trechos incluídos</h3>"
            "<table><thead><tr><th>Grandeza</th><th>Trecho crítico</th><th>Valor</th>"
            f"</tr></thead><tbody>{body}</tbody></table>")


def _quantities_table(quantities):
    if not quantities:
        return "<p>Não há trechos dimensionados incluídos.</p>"
    body = "".join(
        "<tr>"
        f"<td>{escape(item['material'])}</td><td>{escape(item['product'])}</td>"
        f"<td class=\"numero\">{escape(item['diameter'])}</td>"
        f"<td class=\"numero\">{item['count']}</td>"
        f"<td class=\"numero\">{_pt_number(item['length_m'])}</td>"
        f"<td class=\"numero\">{_optional_pt(item['cost'])}</td></tr>"
        for item in quantities
    )
    return ("<table><thead><tr><th>Material</th><th>Produto</th><th>DN</th>"
            "<th>Trechos</th><th>Extensão (m)</th><th>Custo indicativo</th></tr>"
            f"</thead><tbody>{body}</tbody></table>")


def _sizing_tables(model):
    rows = model["rows"]
    if not rows:
        return "<p>Nenhum trecho processado.</p>"
    hydraulic = []
    pressure = []
    pressure_unit = _project_pressure_unit(model)
    for row in rows:
        hydraulic.append(
            "<tr>"
            f"<td>{escape(str(row['pipe_id']))}</td>"
            f"<td class=\"numero\">{_optional_pt(row.get('length_m'))}</td>"
            f"<td class=\"numero\">{_optional_pt(row.get('flow_original'))}</td>"
            f"<td>{escape(str(row.get('flow_unit') or ''))}</td>"
            f"<td>{escape(str(row.get('material_code') or '—'))}</td>"
            f"<td class=\"numero\">{_optional_pt(row.get('nominal_diameter'))}</td>"
            f"<td class=\"numero\">{_optional_pt(row.get('internal_diameter'))}</td>"
            f"<td class=\"numero\">{_optional_pt(row.get('velocity_m_s'))}</td>"
            f"<td class=\"numero\">{_optional_pt(row.get('unit_headloss_m_km'))}</td>"
            f"<td class=\"numero\">{_optional_pt(row.get('total_headloss_m'))}</td>"
            f"<td>{escape(_status_name(row.get('status')))}</td></tr>"
        )
        pressure.append(
            "<tr>"
            f"<td>{escape(str(row['pipe_id']))}</td>"
            f"<td>{escape(str(row.get('initial_node_id') or 'Não disponível'))}</td>"
            f"<td class=\"numero\">{_pressure_pt(row, 'initial_pressure_pa', 'initial_pressure_original', pressure_unit)}</td>"
            f"<td>{escape(str(row.get('final_node_id') or 'Não disponível'))}</td>"
            f"<td class=\"numero\">{_pressure_pt(row, 'final_pressure_pa', 'final_pressure_original', pressure_unit)}</td>"
            f"<td class=\"numero\">{_pressure_pt(row, 'verification_pressure_pa', None, pressure_unit)}</td>"
            f"<td>{escape(str(row.get('pressure_class') or '—'))}</td>"
            f"<td class=\"numero\">{_pressure_pt(row, 'allowable_pressure_pa', None, pressure_unit)}</td>"
            f"<td class=\"numero\">{_optional_pt(row.get('segment_cost'))}</td>"
            f"<td>{escape(_criterion_name(row.get('controlling_criterion')))}</td>"
            f"<td>{escape(_application_name(row.get('apply_status')))}</td>"
            f"<td>{escape(_messages_pt(row.get('messages')))}</td></tr>"
        )
    return f"""<h3>A.1 Grandezas hidráulicas e material selecionado</h3>
<table><thead><tr><th>Trecho</th><th>L (m)</th><th>Q original</th><th>Un.</th>
<th>Material</th><th>DN</th><th>Di</th><th>v (m/s)</th>
<th>J (m/km)</th><th>hf (m)</th><th>Situação</th></tr></thead>
<tbody>{''.join(hydraulic)}</tbody></table>
<h3>A.2 Pressões, custos e decisão</h3>
<table><thead><tr><th>Trecho</th><th>Nó inicial</th><th>P inicial ({escape(pressure_unit)})</th>
<th>Nó final</th><th>P final ({escape(pressure_unit)})</th>
<th>P verif. ({escape(pressure_unit)})</th><th>Classe</th>
<th>P adm. ({escape(pressure_unit)})</th><th>Custo</th>
<th>Critério controlador</th><th>Aplicação</th><th>Observações</th></tr></thead>
<tbody>{''.join(pressure)}</tbody></table>"""


def _write_csv(path, model):
    method = _method_name(model["metadata"].get("hydraulic_method"))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in model["rows"]:
            values = {
                "incluido": "sim" if row["included"] else "não",
                "elegivel": "sim" if row["eligible"] else "não",
                "id_trecho": row["pipe_id"],
                "fid_trecho": row["pipe_fid"],
                "situacao_dimensionamento": _status_name(row["status"]),
                "situacao_aplicacao": _application_name(row["apply_status"]),
                "comprimento_original": row.get("length_original"),
                "unidade_comprimento": row.get("length_unit"),
                "comprimento_m": row.get("length_m"),
                "vazao_original": row.get("flow_original"),
                "unidade_vazao": row.get("flow_unit"),
                "vazao_utilizada_m3_s": row.get("flow_used_m3_s"),
                "material": row.get("material_code"),
                "produto": row.get("product_code"),
                "id_catalogo": row.get("selected_catalog_id"),
                "diametro_nominal": row.get("nominal_diameter"),
                "unidade_diametro_nominal": row.get("nominal_diameter_unit"),
                "diametro_interno": row.get("internal_diameter"),
                "unidade_diametro_interno": row.get("internal_diameter_unit"),
                "velocidade_m_s": row.get("velocity_m_s"),
                "metodo_hidraulico": method,
                "coeficiente_hazen_williams": row.get("hazen_williams_c"),
                "rugosidade_absoluta": row.get("absolute_roughness"),
                "unidade_rugosidade": row.get("roughness_unit"),
                "numero_reynolds": row.get("reynolds"),
                "regime_escoamento": _regime_name(row.get("regime")),
                "fator_atrito": row.get("friction_factor"),
                "perda_carga_unitaria_m_km": row.get("unit_headloss_m_km"),
                "perda_carga_trecho_m": row.get("total_headloss_m"),
                "no_inicial": row.get("initial_node_id"),
                "no_final": row.get("final_node_id"),
                "pressao_inicial_original": row.get("initial_pressure_original"),
                "pressao_final_original": row.get("final_pressure_original"),
                "unidade_pressao_nodal": row.get("endpoint_pressure_unit"),
                "pressao_inicial_pa": row.get("initial_pressure_pa"),
                "pressao_final_pa": row.get("final_pressure_pa"),
                "pressao_base_verificacao_pa": row.get("base_verification_pressure_pa"),
                "tipo_margem": _margin_name(row.get("margin_mode")),
                "fator_seguranca": row.get("safety_factor"),
                "margem_aditiva_original": row.get("additive_margin_original"),
                "unidade_margem_aditiva": row.get("additive_margin_unit"),
                "margem_aditiva_pa": row.get("additive_margin_pa"),
                "pressao_verificacao_pa": row.get("verification_pressure_pa"),
                "classe_pressao": row.get("pressure_class"),
                "pressao_admissivel_original": row.get("max_allowable_pressure"),
                "unidade_pressao_produto": row.get("pressure_unit"),
                "pressao_admissivel_pa": row.get("allowable_pressure_pa"),
                "custo_unitario_comprimento": row.get("cost_per_length"),
                "unidade_custo_comprimento": row.get("cost_length_unit"),
                "custo_trecho": row.get("segment_cost"),
                "criterio_controlador": _criterion_name(row.get("controlling_criterion")),
                "observacoes": _messages_pt(row.get("messages")),
            }
            writer.writerow({key: "" if value is None else value for key, value in values.items()})


def _summary(rows, applied_plan):
    changed = sum(row["status"] == "change" for row in applied_plan["rows"]) if applied_plan else 0
    maintained = sum(row["status"] == "maintained" for row in applied_plan["rows"]) if applied_plan else 0
    costs = [float(row["segment_cost"]) for row in rows if row["included"] and row.get("segment_cost") is not None]
    node_ids = {
        str(row[key])
        for row in rows
        for key in ("initial_node_id", "final_node_id")
        if row.get(key) not in {None, ""}
    }
    products = {
        int(row["selected_catalog_id"])
        for row in rows
        if row["included"] and row.get("selected_catalog_id") is not None
    }
    return {
        "processed_count": len(rows),
        "sized_count": sum(row["status"] == "sized" for row in rows),
        "warning_count": sum(row["status"] == "sized with warning" for row in rows),
        "included_count": sum(row["included"] for row in rows),
        "unique_nodes_count": len(node_ids),
        "unique_products_count": len(products),
        "proposed_count": sum(row["apply_status"] == "proposed" for row in rows),
        "changed_count": changed,
        "maintained_count": maintained + sum(not row["included"] for row in rows),
        "no_solution_count": sum(row["status"] == "no solution" for row in rows),
        "insufficient_count": sum(row["status"] == "insufficient data" for row in rows),
        "total_length_m": sum(row.get("length_m") or 0.0 for row in rows),
        "included_length_m": sum((row.get("length_m") or 0.0) for row in rows if row["included"]),
        "total_cost": sum(costs) if costs else None,
        "missing_cost_count": sum(row["included"] and row.get("selected_catalog_id") is not None and row.get("segment_cost") is None for row in rows),
    }


def _quantities(rows):
    grouped = {}
    for row in rows:
        if not row["included"] or row.get("selected_catalog_id") is None:
            continue
        diameter = _value_unit(row.get("nominal_diameter"), row.get("nominal_diameter_unit"))
        key = (str(row.get("material_code") or "Não informado"), str(row.get("product_code") or "Não informado"), diameter)
        item = grouped.setdefault(key, {"material": key[0], "product": key[1], "diameter": key[2], "count": 0, "length_m": 0.0, "cost": None})
        item["count"] += 1
        item["length_m"] += row.get("length_m") or 0.0
        if row.get("segment_cost") is not None:
            item["cost"] = (item["cost"] or 0.0) + float(row["segment_cost"])
    return [grouped[key] for key in sorted(grouped, key=lambda item: tuple(value.casefold() for value in item))]


def _critical_results(rows, metadata):
    included = [row for row in rows if row["included"] and row.get("selected_catalog_id") is not None]
    specifications = (
        ("Menor velocidade", "velocity_m_s", "m/s", min),
        ("Maior velocidade", "velocity_m_s", "m/s"),
        ("Maior perda de carga unitária", "unit_headloss_m_km", "m/km", max),
        ("Maior perda de carga no trecho", "total_headloss_m", "m", max),
    )
    results = []
    for specification in specifications:
        if len(specification) == 3:
            label, key, unit = specification
            selector = max
        else:
            label, key, unit, selector = specification
        valid = [row for row in included if row.get(key) is not None]
        if valid:
            row = selector(valid, key=lambda item: float(item[key]))
            results.append({"label": label, "pipe_id": row["pipe_id"], "display": _value_unit(row[key], unit)})
    endpoint_unit = _pressure_unit(rows, metadata)
    verification_rows = [
        row for row in included if row.get("verification_pressure_pa") is not None
    ]
    if verification_rows:
        row = max(
            verification_rows,
            key=lambda item: float(item["verification_pressure_pa"]),
        )
        value = convert(
            row["verification_pressure_pa"],
            "pressure",
            "Pa",
            endpoint_unit,
        )
        results.append({
            "label": "Maior pressão de verificação",
            "pipe_id": row["pipe_id"],
            "display": _value_unit(value, endpoint_unit),
        })
    endpoints = []
    for row in included:
        for node_key, pressure_key, pascal_key in (
            ("initial_node_id", "initial_pressure_original", "initial_pressure_pa"),
            ("final_node_id", "final_pressure_original", "final_pressure_pa"),
        ):
            value = row.get(pascal_key)
            if value is not None:
                try:
                    value = convert(value, "pressure", "Pa", endpoint_unit)
                except ValueError:
                    value = None
            elif row.get(pressure_key) is not None:
                value = float(row[pressure_key])
            if value is not None:
                endpoints.append((float(value), row.get(node_key), row))
    if endpoints:
        for label, item in (
            ("Trecho com menor pressão nas extremidades", min(endpoints, key=lambda value: value[0])),
            ("Trecho com maior pressão nas extremidades", max(endpoints, key=lambda value: value[0])),
        ):
            value, node_id, row = item
            results.append({
                "label": label,
                "pipe_id": f"{row['pipe_id']} / nó {node_id}",
                "display": _value_unit(value, endpoint_unit),
            })
    utilization = [row for row in included if row.get("verification_pressure_pa") is not None and row.get("allowable_pressure_pa")]
    if utilization:
        row = max(utilization, key=lambda item: item["verification_pressure_pa"] / item["allowable_pressure_pa"])
        ratio = 100 * row["verification_pressure_pa"] / row["allowable_pressure_pa"]
        results.append({"label": "Maior utilização da classe de pressão", "pipe_id": row["pipe_id"], "display": f"{_pt_number(ratio)} %"})
    return results


def _definition_table(items):
    return "<table><tbody>" + "".join(
        f"<tr><th>{escape(str(label))}</th><td>{escape(str('—' if value in {None, ''} else value))}</td></tr>"
        for label, value in items
    ) + "</tbody></table>"


def _messages_pt(messages):
    if not messages:
        return "Sem observações"
    return "; ".join(_message_pt(str(message)) for message in messages)


def _message_pt(message):
    exact = {
        "allowable product pressure is missing": "pressão admissível do produto não informada",
        "no active catalog product satisfies every required criterion": "nenhum produto ativo do catálogo atende a todos os critérios obrigatórios",
        "Original flow is negative; its sign is preserved and calculations use the magnitude.": "A vazão original é negativa; o sinal foi preservado e o módulo foi utilizado nos cálculos.",
        "Original flow is zero; a later stage must define the final sizing rule.": "A vazão original é zero; o critério final de dimensionamento requer revisão.",
        "At least one endpoint pressure is negative; review the hydraulic simulation before sizing.": "Há pressão negativa em pelo menos uma extremidade; revisar a simulação hidráulica.",
    }
    if message in exact:
        return exact[message]
    translated = message
    replacements = (
        ("unit headloss", "perda de carga unitária"),
        ("maximum velocity", "velocidade máxima"),
        ("minimum velocity", "velocidade mínima"),
        ("minimum nominal diameter", "diâmetro nominal mínimo"),
        ("Bresse initial diameter", "diâmetro inicial de Bresse"),
        ("pressure", "pressão"),
        ("velocity", "velocidade"),
        ("exceeds", "excede"),
        ("is below", "é inferior a"),
        ("initial endpoint node", "nó da extremidade inicial"),
        ("final endpoint node", "nó da extremidade final"),
        ("has no pressure result", "não possui resultado de pressão"),
        ("has conflicting pressure results", "possui resultados de pressão conflitantes"),
        ("was not found", "não foi encontrado"),
        ("is duplicated", "está duplicado"),
    )
    for source, target in replacements:
        translated = re.sub(re.escape(source), target, translated, flags=re.IGNORECASE)
    if re.search(r"\b(the|must|has|node|endpoint|flow|length|result|missing|invalid)\b", translated, re.IGNORECASE):
        return "Ocorrência de dados no trecho; revisar a validação e executar novamente o dimensionamento."
    return translated


def _status_name(value):
    return {"sized": "Dimensionado", "sized with warning": "Dimensionado com alerta", "no solution": "Sem solução no catálogo", "insufficient data": "Dados insuficientes"}.get(value, "Não informado")


def _application_name(value):
    return {"applied": "Alterado na sessão", "maintained": "Mantido", "proposed": "Proposto", "excluded": "Excluído da proposta"}.get(value, "Não informado")


def _criterion_name(value):
    return {"pressure": "Pressão", "unit headloss": "Perda de carga unitária", "maximum velocity": "Velocidade máxima", "minimum velocity": "Velocidade mínima", "minimum nominal diameter": "Diâmetro nominal mínimo", "Bresse initial diameter": "Diâmetro inicial de Bresse", "hydraulic data": "Dados hidráulicos"}.get(value, "Não aplicável" if not value else str(value))


def _regime_name(value):
    return {"laminar": "Laminar", "transitional": "Transição", "turbulent": "Turbulento", "stagnant": "Estagnado"}.get(value, "" if value in {None, ""} else str(value))


def _margin_name(value):
    return {"none": "Sem margem", "factor": "Fator de segurança", "additive": "Margem aditiva"}.get(value, "Não informada")


def _method_name(value):
    return {"H-W": "Hazen–Williams", "D-W": "Darcy–Weisbach"}.get(value, "Não informado")


def _pressure_margin(metadata):
    mode = metadata.get("pressure_margin_mode")
    if mode == "factor":
        return f"Fator de segurança = {_pt_number(metadata.get('safety_factor'))}"
    if mode == "additive":
        return "Margem aditiva = " + _value_unit(
            metadata.get("additive_margin_value"),
            metadata.get("additive_margin_unit"),
        )
    return "Sem margem adicional"


def _qgisred_version(value):
    if not value or str(value).casefold() in {"not detected", "not identified"}:
        return "Não identificada"
    return str(value)


def _project_pressure_unit(model):
    return _pressure_unit(model["rows"], model["metadata"])


def _pressure_unit(rows, metadata):
    """Usar a unidade do retrato calculado antes da configuração atual da UI."""
    for row in rows:
        if row.get("endpoint_pressure_unit"):
            return str(row["endpoint_pressure_unit"])
    configured = metadata.get("endpoint_pressure_unit")
    if configured:
        return str(configured)
    return "Pa"


def _pressure_pt(row, pascal_key, original_key, target_unit):
    pascal_value = row.get(pascal_key)
    if pascal_value is not None:
        try:
            return _pt_number(
                convert(pascal_value, "pressure", "Pa", target_unit)
            )
        except ValueError:
            pass
    if original_key and row.get(original_key) is not None:
        original_unit = row.get("endpoint_pressure_unit") or target_unit
        try:
            return _pt_number(
                convert(
                    row[original_key],
                    "pressure",
                    original_unit,
                    target_unit,
                )
            )
        except ValueError:
            return _pt_number(row[original_key])
    return "—"


def _selection_name(value):
    return {"all": "Todos os trechos mapeados", "selected": "Trechos selecionados"}.get(value, "Não informado")


def _yes_no(value):
    return "Sim" if bool(value) else "Não"


def _enabled_value(enabled, value, unit):
    return _value_unit(value, unit) if enabled else "Não aplicado"


def _value_unit(value, unit):
    if value in {None, ""}:
        return "Não informado"
    return f"{_pt_number(value)} {unit or ''}".strip()


def _pt_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return str(number)
    return f"{number:.8g}".replace(".", ",")


def _optional_pt(value):
    return "—" if value is None else _pt_number(value)


def _display_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.strftime("%d/%m/%Y %H:%M:%S %z")
    except ValueError:
        return str(value)


_REPORT_PT_TO_EN = {
    "Memória de cálculo hidráulico": "Hydraulic calculation memory",
    "Rede de distribuição de água": "Water distribution network",
    "Empreendimento não identificado": "Unidentified project",
    "Contratante não informado": "Client not provided",
    "Localidade": "Location",
    "Fase do projeto": "Project stage",
    "Código do documento": "Document code",
    "Revisão": "Revision",
    "Responsável técnico": "Responsible engineer",
    "Registro profissional": "Professional registration",
    "Data de emissão": "Issue date",
    "Não informada": "Not provided",
    "Não informado": "Not provided",
    "Documento gerado para revisão, complementação e assinatura do responsável técnico.": (
        "Document generated for review, completion, and signature by the responsible engineer."
    ),
    "1 Objeto e escopo": "1 Purpose and scope",
    "Esta memória apresenta os critérios, as premissas, o procedimento de cálculo e os resultados do dimensionamento hidráulico das tubulações da rede de distribuição de água do empreendimento": (
        "This calculation memory presents the criteria, assumptions, calculation procedure, and hydraulic sizing results for the pipes in the water distribution network of the project"
    ),
    "A concepção geral do empreendimento não foi informada no formulário de emissão.": (
        "The general project concept was not provided in the issue form."
    ),
    "O escopo automatizado abrange a verificação trecho a trecho, com vazões provenientes do modelo hidráulico identificado nesta memória, seleção de produtos do catálogo e verificação da pressão de serviço do produto. A análise não determina demandas, não redistribui vazões e não substitui a simulação hidráulica global da rede.": (
        "The automated scope covers pipe-by-pipe verification using flows from the hydraulic model identified in this document, catalog product selection, and product service-pressure verification. The analysis does not determine demands, redistribute flows, or replace the global hydraulic simulation of the network."
    ),
    "3 Dados de entrada e premissas": "3 Input data and assumptions",
    "3.1 Identificação do cenário hidráulico": "3.1 Hydraulic scenario identification",
    "Cenário analisado": "Analyzed scenario",
    "Método de perda de carga": "Headloss method",
    "Unidade da vazão de origem": "Source flow unit",
    "Unidade do comprimento de origem": "Source length unit",
    "Unidade da pressão nodal": "Node pressure unit",
    "Sistema de referência do projeto": "Project coordinate reference system",
    "4 Critérios de dimensionamento": "4 Sizing criteria",
    "Materiais admitidos no projeto": "Materials allowed in the project",
    "Todos os materiais ativos": "All active materials",
    "Perda de carga unitária máxima": "Maximum unit headloss",
    "Velocidade máxima": "Maximum velocity",
    "Velocidade mínima": "Minimum velocity",
    "Diâmetro nominal mínimo": "Minimum nominal diameter",
    "Estimativa inicial de Bresse": "Initial Bresse estimate",
    "Verificação da classe de pressão": "Pressure-class verification",
    "Margem de verificação da pressão": "Pressure verification margin",
    "Viscosidade cinemática": "Kinematic viscosity",
    "Não aplicado": "Not applied",
    "Alerta, sem rejeição": "Warning without rejection",
    "Obrigatório": "Required",
    "Sim": "Yes",
    "Não": "No",
    "Sem margem adicional": "No additional margin",
    "Fator de segurança": "Safety factor",
    "Margem aditiva": "Additive margin",
    "A escolha exige atendimento simultâneo a todos os critérios obrigatórios habilitados. Entre os produtos admissíveis, a ordenação considera menor DN, menor custo disponível, maior pressão admissível e, por fim, o identificador estável do catálogo.": (
        "Selection requires simultaneous compliance with every enabled mandatory criterion. Among admissible products, ordering considers smallest DN, lowest available cost, highest allowable pressure, and finally the stable catalog identifier."
    ),
    "5 Formulação hidráulica": "5 Hydraulic formulation",
    "5.1 Continuidade das unidades e velocidade": "5.1 Unit consistency and velocity",
    "5.2 Equação de Hazen–Williams": "5.2 Hazen–Williams equation",
    "5.2 Equação de Darcy–Weisbach": "5.2 Darcy–Weisbach equation",
    "O coeficiente C e o diâmetro interno real são obtidos do produto do catálogo. Para apresentação, J é convertido de m/m para m/km.": (
        "Coefficient C and the actual internal diameter are obtained from the catalog product. For presentation, J is converted from m/m to m/km."
    ),
    "Para regime laminar, f = 64/Re. Para regime turbulento é utilizada a aproximação explícita de Swamee–Jain. Na faixa de transição é aplicada interpolação entre os limites, com indicação para revisão técnica.": (
        "For laminar flow, f = 64/Re. For turbulent flow, the explicit Swamee–Jain approximation is used. In the transition range, interpolation is applied between the limits and flagged for technical review."
    ),
    "5.3 Verificação de pressão do produto": "5.3 Product pressure verification",
    "Pbase = máx(Pnó inicial, Pnó final)": "Pbase = max(Pinitial node, Pfinal node)",
    "Pverificação = Pbase × FS ou Pbase + margem aditiva": "Pverification = Pbase × SF or Pbase + additive margin",
    "máx": "max",
    "inicial": "initial",
    "final": "final",
    "verificação": "verification",
    "margem aditiva": "additive margin",
    "FS": "SF",
    "O produto é admissível quando a pressão de verificação não supera sua pressão máxima admissível. Esta checagem é de resistência do produto e não substitui a verificação das pressões mínimas e máximas de serviço em todos os nós e cenários da rede.": (
        "A product is admissible when the verification pressure does not exceed its maximum allowable pressure. This product-strength check does not replace verification of minimum and maximum service pressures at every node and network scenario."
    ),
    "5.4 Custo indicativo": "5.4 Indicative cost",
    "Custo do trecho = comprimento convertido para metro × custo por metro": "Pipe cost = length converted to metres × cost per metre",
    "O custo participa do desempate somente quando disponível e não constitui orçamento da obra.": (
        "Cost is used as a tie-breaker only when available and is not a construction estimate."
    ),
    "6 Síntese do dimensionamento": "6 Sizing summary",
    "Total de trechos": "Total pipes",
    "Extensão total": "Total length",
    "Custo total estimado": "Total estimated cost",
    "6.1 Valores críticos entre os trechos incluídos": "6.1 Critical values among included pipes",
    "6.1 Valores críticos": "6.1 Critical values",
    "Não há resultados hidráulicos válidos.": "No valid hydraulic results are available.",
    "Grandeza": "Quantity",
    "Trecho crítico": "Critical pipe",
    "Valor": "Value",
    "Menor velocidade": "Lowest velocity",
    "Maior velocidade": "Highest velocity",
    "Maior perda de carga unitária": "Highest unit headloss",
    "Maior perda de carga no trecho": "Highest pipe headloss",
    "Maior pressão de verificação": "Highest verification pressure",
    "Trecho com menor pressão nas extremidades": "Pipe with lowest endpoint pressure",
    "Trecho com maior pressão nas extremidades": "Pipe with highest endpoint pressure",
    "Maior utilização da classe de pressão": "Highest pressure-class utilization",
    "nó": "node",
    "6.2 Quantitativos de tubulações dimensionadas": "6.2 Sized pipe quantities",
    "Não há trechos dimensionados incluídos.": "No sized pipes are included.",
    "Material": "Material",
    "Produto": "Product",
    "Trechos": "Pipes",
    "Extensão (m)": "Length (m)",
    "Custo indicativo": "Indicative cost",
    "Os quantitativos consideram apenas os trechos incluídos na prévia. Custos são estimativos e permanecem sem unidade monetária quando ela não foi definida no catálogo.": (
        "Quantities include only pipes retained in the preview. Costs are estimates and remain without a currency unit when none is defined in the catalog."
    ),
    "Anexo A — Planilha de dimensionamento por trecho": "Appendix A — Pipe sizing worksheet",
    "Nenhum trecho processado.": "No pipe was processed.",
    "A.1 Grandezas hidráulicas e material selecionado": "A.1 Hydraulic quantities and selected material",
    "Trecho": "Pipe",
    "Q original": "Original Q",
    "Situação": "Status",
    "A.2 Pressões, custos e decisão": "A.2 Pressures, costs, and decision",
    "Nó inicial": "Initial node",
    "P inicial": "Initial P",
    "Nó final": "Final node",
    "P final": "Final P",
    "P verif.": "Verification P",
    "Classe": "Class",
    "P adm.": "Allowable P",
    "Custo": "Cost",
    "Critério controlador": "Controlling criterion",
    "Aplicação": "Application",
    "Observações": "Notes",
    "Não disponível": "Not available",
    "Dimensionado com alerta": "Sized with warning",
    "Dimensionado": "Sized",
    "Sem solução no catálogo": "No catalog solution",
    "Dados insuficientes": "Insufficient data",
    "Alterado na sessão": "Changed in session",
    "Mantido": "Kept",
    "Proposto": "Proposed",
    "Excluído da proposta": "Excluded from proposal",
    "Pressão": "Pressure",
    "Perda de carga unitária": "Unit headloss",
    "Diâmetro inicial de Bresse": "Initial Bresse diameter",
    "Dados hidráulicos": "Hydraulic data",
    "Não aplicável": "Not applicable",
    "Sem observações": "No notes",
    "Anexo B — Rastreabilidade computacional": "Appendix B — Computational traceability",
    "Ferramenta de cálculo": "Calculation tool",
    "Versão do HydroSizer": "HydroSizer version",
    "Versão do QGISRed": "QGISRed version",
    "Versão do QGIS": "QGIS version",
    "Não identificada": "Not identified",
}


def _report_language(metadata: Mapping[str, Any]) -> str:
    raw = str(metadata.get("language") or metadata.get("locale") or "pt_BR")
    return "pt_BR" if raw.replace("-", "_").casefold().startswith("pt") else "en"


def _localized_report_html(html: str, metadata: Mapping[str, Any]) -> str:
    """Translate rendered presentation text while preserving project data and markup."""
    if _report_language(metadata) == "pt_BR":
        return html

    def translate_section(section: str) -> str:
        def translate_text_node(match):
            original = match.group(1)
            if not original.strip():
                return match.group(0)
            translated = " ".join(original.split())
            translated = translated.replace(" ou ", " or ")
            for source in sorted(_REPORT_PT_TO_EN, key=len, reverse=True):
                translated = translated.replace(source, _REPORT_PT_TO_EN[source])
            translated = re.sub(r"(?<=\d),(?=\d)", ".", translated)
            return f">{translated}<"

        return re.sub(r">([^<]+)<", translate_text_node, section)

    before_style, marker, after_style = html.partition("<style>")
    if not marker:
        translated = translate_section(html)
    else:
        css, closing, body = after_style.partition("</style>")
        translated = (
            translate_section(before_style)
            + marker
            + css
            + closing
            + translate_section(body)
        )
    return translated.replace('<html lang="pt-BR">', '<html lang="en">')


def _converted(value, quantity, unit):
    if value is None or not unit:
        return None
    try:
        return to_si(value, quantity, unit)
    except ValueError:
        return None


def _converted_magnitude(value, quantity, unit):
    converted = _converted(value, quantity, unit)
    return None if converted is None else abs(converted)


def _temporary_path(directory, name):
    descriptor, raw_path = tempfile.mkstemp(dir=directory, prefix=f".{name}.", suffix=".tmp")
    os.close(descriptor)
    return Path(raw_path)
