"""Geração de relatório PDF com ReportLab."""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

from ..config import DB_PATH, RESPONSAVEL_RELATORIO
from ..models import Caso, Competencia

logger = logging.getLogger(__name__)

_RELATORIOS_DIR = DB_PATH.parent / "relatorios"
_RELATORIOS_DIR.mkdir(parents=True, exist_ok=True)

_AZUL = colors.HexColor("#1a3a6b")
_CINZA_CLARO = colors.HexColor("#f5f5f5")
_CINZA_ESCURO = colors.HexColor("#333333")
_VERDE = colors.HexColor("#2ecc71")


def _estilos():
    ss = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("titulo", parent=ss["Title"], fontSize=22, textColor=_AZUL, spaceAfter=8, alignment=TA_CENTER),
        "subtitulo": ParagraphStyle("subtitulo", parent=ss["Normal"], fontSize=14, textColor=_AZUL, spaceAfter=6, spaceBefore=12),
        "secao": ParagraphStyle("secao", parent=ss["Heading2"], fontSize=12, textColor=_AZUL, spaceAfter=4, spaceBefore=10),
        "normal": ParagraphStyle("normal", parent=ss["Normal"], fontSize=10, textColor=_CINZA_ESCURO, spaceAfter=4),
        "pequeno": ParagraphStyle("pequeno", parent=ss["Normal"], fontSize=8, textColor=colors.gray),
        "destaque": ParagraphStyle("destaque", parent=ss["Normal"], fontSize=11, textColor=_VERDE, spaceAfter=4),
        "aviso": ParagraphStyle("aviso", parent=ss["Normal"], fontSize=9, textColor=colors.gray, spaceAfter=6,
                                leftIndent=12, borderPad=4),
    }


def _rodape(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.gray)
    canvas.drawString(2 * cm, 1 * cm,
                      f"Página {doc.page}  |  Gerado em {date.today().strftime('%d/%m/%Y')}  |  Documento de uso interno")
    canvas.drawRightString(A4[0] - 2 * cm, 1 * cm, RESPONSAVEL_RELATORIO)
    canvas.restoreState()


def gerar_relatorio(
    caso: Caso,
    competencias: List[Competencia],
    confronto,
    resultados_calculo: list,
    secoes: List[str],
) -> str:
    """Gera o relatório PDF e retorna o caminho do arquivo gerado."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo = f"relatorio_{caso.cpf}_{ts}.pdf"
    caminho = str(_RELATORIOS_DIR / nome_arquivo)

    doc = SimpleDocTemplate(
        caminho, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=2.5 * cm, bottomMargin=2 * cm,
    )

    est = _estilos()
    story = []

    if "capa" in secoes:
        story.extend(_capa(caso, est))

    if "resumo" in secoes:
        story.extend(_resumo(caso, competencias, confronto, est))

    if "periodos" in secoes:
        story.extend(_periodos(competencias, est))

    if "tabela" in secoes:
        story.extend(_tabela_competencias(competencias, est))

    if "confronto" in secoes:
        story.extend(_secao_confronto(confronto, est))

    if "calculo" in secoes:
        story.extend(_secao_calculo(resultados_calculo, est))

    if "inconsistencias" in secoes and confronto:
        story.extend(_secao_inconsistencias(confronto, est))

    doc.build(story, onLaterPages=_rodape, onFirstPage=_rodape)
    logger.info("Relatório gerado: %s", caminho)
    return caminho


def _capa(caso: Caso, est: dict) -> list:
    items = [
        Spacer(1, 3 * cm),
        Paragraph("ANÁLISE PREVIDENCIÁRIA", est["titulo"]),
        HRFlowable(width="100%", thickness=2, color=_AZUL),
        Spacer(1, 1 * cm),
        Paragraph(f"<b>Segurado:</b> {caso.nome}", est["subtitulo"]),
        Paragraph(f"<b>CPF:</b> {_fmt_cpf(caso.cpf)}", est["normal"]),
        Paragraph(f"<b>Data de nascimento:</b> {caso.data_nascimento.strftime('%d/%m/%Y')}", est["normal"]),
        Spacer(1, 2 * cm),
        Paragraph(f"<b>Data de elaboração:</b> {date.today().strftime('%d/%m/%Y')}", est["normal"]),
        Paragraph(f"<b>Responsável:</b> {RESPONSAVEL_RELATORIO}", est["normal"]),
        Spacer(1, 1.5 * cm),
        Paragraph(
            "Este documento é de análise técnica e não substitui a decisão administrativa ou judicial do INSS.",
            est["aviso"],
        ),
        PageBreak(),
    ]
    return items


def _resumo(caso: Caso, competencias: List[Competencia], confronto, est: dict) -> list:
    from ..engine.periodos import calcular_tempo_contributivo
    tempo = calcular_tempo_contributivo(competencias)
    fontes = sorted({c.fonte.value for c in competencias})
    n_inconsistencias = (
        len(confronto.divergencias_valor) + len(confronto.sobreposicoes)
        if confronto else 0
    )

    items = [
        Paragraph("RESUMO EXECUTIVO", est["secao"]),
        HRFlowable(width="100%", thickness=1, color=_AZUL),
        Spacer(1, 0.3 * cm),
        Paragraph(f"Período total apurado: <b>{tempo.anos} anos e {tempo.meses} meses</b>", est["normal"]),
        Paragraph(f"Total de competências: <b>{len(competencias)}</b>", est["normal"]),
        Paragraph(f"Fontes consultadas: <b>{', '.join(fontes) or 'Nenhuma'}</b>", est["normal"]),
        Paragraph(f"Inconsistências encontradas: <b>{n_inconsistencias}</b>", est["normal"]),
        Spacer(1, 0.5 * cm),
    ]
    return items


def _periodos(competencias: List[Competencia], est: dict) -> list:
    items = [
        Paragraph("PERÍODOS CONTRIBUTIVOS", est["secao"]),
        HRFlowable(width="100%", thickness=1, color=_AZUL),
        Spacer(1, 0.3 * cm),
    ]

    # Agrupa por empregador
    por_emp: dict[str, list] = {}
    for c in sorted(competencias, key=lambda x: _comp_key(x.competencia)):
        por_emp.setdefault(c.empregador_nome, []).append(c)

    tabela_data = [["Empregador", "Tipo", "Início", "Fim", "Duração"]]
    for emp, comps in list(por_emp.items())[:50]:
        sorted_comps = sorted(comps, key=lambda x: _comp_key(x.competencia))
        inicio = sorted_comps[0].competencia
        fim = sorted_comps[-1].competencia
        meses = len({c.competencia for c in comps})
        tabela_data.append([emp[:45], comps[0].tipo_vinculo.value, inicio, fim, f"{meses // 12}a {meses % 12}m"])

    tabela = Table(tabela_data, colWidths=[7 * cm, 2.5 * cm, 2.2 * cm, 2.2 * cm, 2 * cm])
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_CINZA_CLARO, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    items.append(tabela)
    items.append(Spacer(1, 0.5 * cm))
    return items


def _tabela_competencias(competencias: List[Competencia], est: dict) -> list:
    items = [
        PageBreak(),
        Paragraph("TABELA COMPLETA DE COMPETÊNCIAS", est["secao"]),
        HRFlowable(width="100%", thickness=1, color=_AZUL),
        Spacer(1, 0.3 * cm),
    ]

    cabecalho = ["Competência", "Empregador", "Tipo", "Rem. Bruta", "Rem. Atualizada", "Fonte"]
    dados = [cabecalho]
    for c in sorted(competencias, key=lambda x: _comp_key(x.competencia)):
        dados.append([
            c.competencia,
            c.empregador_nome[:40],
            c.tipo_vinculo.value,
            f"R$ {c.remuneracao_bruta:,.2f}",
            f"R$ {c.remuneracao_atualizada:,.2f}" if c.remuneracao_atualizada else "—",
            c.fonte.value,
        ])

    tabela = Table(dados, colWidths=[2 * cm, 5.5 * cm, 2 * cm, 2.8 * cm, 2.8 * cm, 1.8 * cm])
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_CINZA_CLARO, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    items.append(tabela)
    items.append(Spacer(1, 0.5 * cm))
    return items


def _secao_confronto(confronto, est: dict) -> list:
    items = [
        PageBreak(),
        Paragraph("CONFRONTO DE FONTES", est["secao"]),
        HRFlowable(width="100%", thickness=1, color=_AZUL),
        Spacer(1, 0.3 * cm),
    ]
    if not confronto:
        items.append(Paragraph("Confronto não executado.", est["normal"]))
        return items

    items.append(Paragraph(f"Competências ausentes no CNIS: {len(confronto.competencias_apenas_fontes_externas)}", est["normal"]))
    items.append(Paragraph(f"Divergências de valor: {len(confronto.divergencias_valor)}", est["normal"]))
    items.append(Paragraph(f"Gaps sem contribuição: {len(confronto.gaps)}", est["normal"]))

    if confronto.pendencias_cnis:
        items.append(Spacer(1, 0.3 * cm))
        items.append(Paragraph(
            f"<b>Pendências CNIS ({len(confronto.pendencias_cnis)} competências):</b> "
            "As pendências do CNIS são de caráter informativo e NÃO impedem o cômputo das competências para fins de cálculo do benefício.",
            est["aviso"],
        ))

    return items


def _secao_calculo(resultados: list, est: dict) -> list:
    items = [
        PageBreak(),
        Paragraph("CÁLCULO DO SALÁRIO DE BENEFÍCIO", est["secao"]),
        HRFlowable(width="100%", thickness=1, color=_AZUL),
        Spacer(1, 0.3 * cm),
    ]

    elegiveis = [r for r in resultados if r.elegivel]
    if elegiveis:
        melhor = elegiveis[0]
        items.append(Paragraph(f"Regra mais vantajosa: <b>{melhor.regra}</b>", est["destaque"]))
        items.append(Paragraph(f"Renda Mensal Inicial (RMI): <b>R$ {melhor.rmi:,.2f}</b>", est["destaque"]))
        items.append(Spacer(1, 0.3 * cm))

    for resultado in resultados:
        marcador = "✓" if resultado.elegivel else "✗"
        cor = "#2ecc71" if resultado.elegivel else "#888888"
        items.append(Paragraph(f"{marcador} <b>{resultado.regra}</b>", est["normal"]))
        if resultado.elegivel:
            items.append(Paragraph(f"  Média: R$ {resultado.media_contribuicoes:,.2f} | Coef.: {float(resultado.coeficiente)*100:.0f}% | RMI: R$ {resultado.rmi:,.2f}", est["normal"]))
        else:
            items.append(Paragraph(f"  {resultado.motivo_inelegibilidade}", est["pequeno"]))

    return items


def _secao_inconsistencias(confronto, est: dict) -> list:
    items = [
        Paragraph("INCONSISTÊNCIAS DETECTADAS", est["secao"]),
        HRFlowable(width="100%", thickness=1, color=_AZUL),
        Spacer(1, 0.3 * cm),
    ]
    total = len(getattr(confronto, "divergencias_valor", []))
    if total == 0:
        items.append(Paragraph("Nenhuma inconsistência relevante detectada.", est["normal"]))
    return items


def _fmt_cpf(cpf: str) -> str:
    d = "".join(c for c in cpf if c.isdigit())
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return cpf


def _comp_key(competencia: str) -> int:
    try:
        m, a = competencia.split("/")
        return int(a) * 100 + int(m)
    except ValueError:
        return 0
