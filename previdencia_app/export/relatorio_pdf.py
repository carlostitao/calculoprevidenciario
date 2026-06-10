"""Geração de relatório PDF com ReportLab — com gráficos e visualizações."""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle, KeepTogether,
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics import renderPDF
from reportlab.platypus import Flowable

from ..config import DB_PATH, RESPONSAVEL_RELATORIO
from ..models import Caso, Competencia

logger = logging.getLogger(__name__)

_RELATORIOS_DIR = DB_PATH.parent / "relatorios"
_RELATORIOS_DIR.mkdir(parents=True, exist_ok=True)

# ── Paleta ──────────────────────────────────────────────────────────────────
_AZUL_ESC   = colors.HexColor("#0d1b35")
_AZUL       = colors.HexColor("#1a3a6b")
_AZUL_MED   = colors.HexColor("#1a6fad")
_AZUL_CL    = colors.HexColor("#4a9eff")
_VERDE      = colors.HexColor("#2ecc71")
_VERDE_ESC  = colors.HexColor("#27ae60")
_AMARELO    = colors.HexColor("#f0a500")
_VERMELHO   = colors.HexColor("#e74c3c")
_ROXO       = colors.HexColor("#9b59b6")
_CINZA_CL   = colors.HexColor("#f5f7fa")
_CINZA_MED  = colors.HexColor("#e0e4ea")
_CINZA_TXT  = colors.HexColor("#555555")
_CINZA_ESC  = colors.HexColor("#333333")
_BRANCO     = colors.white
_TRANSPARENTE = colors.HexColor("#00000000")

# Cores por fonte
_COR_FONTE = {
    "CNIS":       colors.HexColor("#1a6fad"),
    "CTPS":       colors.HexColor("#27ae60"),
    "CTC":        colors.HexColor("#8e44ad"),
    "HOLERITE":   colors.HexColor("#16a085"),
    "PRO_LABORE": colors.HexColor("#d35400"),
    "PGDAS_MEI":  colors.HexColor("#f39c12"),
    "DARF":       colors.HexColor("#2980b9"),
    "FGTS":       colors.HexColor("#c0392b"),
    "MANUAL":     colors.HexColor("#7f8c8d"),
}

_GRAF_CORES = [
    "#1a6fad", "#2ecc71", "#f0a500", "#e74c3c",
    "#9b59b6", "#16a085", "#d35400", "#2980b9",
]


# ── Estilos de parágrafo ─────────────────────────────────────────────────────
def _estilos() -> dict:
    ss = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("titulo", parent=ss["Title"],
                                 fontSize=24, textColor=_BRANCO, spaceAfter=8,
                                 alignment=TA_CENTER, fontName="Helvetica-Bold"),
        "subtitulo": ParagraphStyle("subtitulo", parent=ss["Normal"],
                                    fontSize=14, textColor=_AZUL_CL, spaceAfter=4,
                                    spaceBefore=10, fontName="Helvetica-Bold"),
        "secao": ParagraphStyle("secao", parent=ss["Heading2"],
                                fontSize=13, textColor=_AZUL, spaceAfter=4,
                                spaceBefore=12, fontName="Helvetica-Bold"),
        "normal": ParagraphStyle("normal", parent=ss["Normal"],
                                 fontSize=10, textColor=_CINZA_ESC, spaceAfter=4,
                                 fontName="Helvetica"),
        "normal_branco": ParagraphStyle("normal_branco", parent=ss["Normal"],
                                        fontSize=10, textColor=_BRANCO, fontName="Helvetica"),
        "pequeno": ParagraphStyle("pequeno", parent=ss["Normal"],
                                  fontSize=8, textColor=_CINZA_TXT, fontName="Helvetica"),
        "destaque": ParagraphStyle("destaque", parent=ss["Normal"],
                                   fontSize=13, textColor=_VERDE, spaceAfter=4,
                                   fontName="Helvetica-Bold"),
        "rmi_titulo": ParagraphStyle("rmi_titulo", parent=ss["Normal"],
                                     fontSize=10, textColor=_VERDE, fontName="Helvetica"),
        "rmi_valor": ParagraphStyle("rmi_valor", parent=ss["Normal"],
                                    fontSize=22, textColor=_VERDE, fontName="Helvetica-Bold",
                                    spaceAfter=4),
        "aviso": ParagraphStyle("aviso", parent=ss["Normal"],
                                fontSize=9, textColor=_CINZA_TXT, spaceAfter=4,
                                leftIndent=8, fontName="Helvetica-Oblique"),
        "capa_campo": ParagraphStyle("capa_campo", parent=ss["Normal"],
                                     fontSize=12, textColor=_BRANCO, fontName="Helvetica",
                                     spaceAfter=6),
        "label_cinza": ParagraphStyle("label_cinza", parent=ss["Normal"],
                                      fontSize=9, textColor=_CINZA_TXT, fontName="Helvetica",
                                      spaceAfter=2),
    }


# ── Rodapé / cabeçalho ───────────────────────────────────────────────────────
def _rodape(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(_CINZA_TXT)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(2 * cm, 1.2 * cm,
                      f"Página {doc.page}  ·  Gerado em {date.today().strftime('%d/%m/%Y')}  ·  Uso interno — documento confidencial")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, RESPONSAVEL_RELATORIO)
    # Linha do rodapé
    canvas.setStrokeColor(_CINZA_MED)
    canvas.setLineWidth(0.5)
    canvas.line(2 * cm, 1.6 * cm, A4[0] - 2 * cm, 1.6 * cm)
    canvas.restoreState()


# ── Flowable: caixa colorida (callout) ──────────────────────────────────────
class CalloutBox(Flowable):
    def __init__(self, largura: float, altura: float, cor_fundo, cor_borda=None, radius: float = 6):
        super().__init__()
        self.width = largura
        self.height = altura
        self._cor_fundo = cor_fundo
        self._cor_borda = cor_borda or cor_fundo
        self._radius = radius

    def draw(self) -> None:
        self.canv.setFillColor(self._cor_fundo)
        self.canv.setStrokeColor(self._cor_borda)
        self.canv.setLineWidth(1)
        self.canv.roundRect(0, 0, self.width, self.height, self._radius, fill=1, stroke=1)


# ── Função auxiliar de tabela estilizada ────────────────────────────────────
def _tabela(dados: list, col_widths: list, zebra: bool = True,
            cor_header=None, cor_header_txt=_BRANCO) -> Table:
    cor_h = cor_header or _AZUL
    t = Table(dados, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), cor_h),
        ("TEXTCOLOR", (0, 0), (-1, 0), cor_header_txt),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, _CINZA_MED),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_CINZA_CL, _BRANCO] if zebra else [_BRANCO]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    t.setStyle(TableStyle(style))
    return t


# ── Seção: título estilizado ─────────────────────────────────────────────────
def _titulo_secao(texto: str, est: dict, icone: str = "") -> list:
    items = [Spacer(1, 0.3 * cm)]
    label = f"{icone}  {texto}" if icone else texto
    items.append(Paragraph(label, est["secao"]))
    items.append(HRFlowable(width="100%", thickness=1.5, color=_AZUL_MED))
    items.append(Spacer(1, 0.3 * cm))
    return items


# ── MAIN ─────────────────────────────────────────────────────────────────────
def gerar_relatorio(
    caso: Caso,
    competencias: List[Competencia],
    confronto,
    resultados_calculo: list,
    secoes: List[str],
) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo = f"relatorio_{caso.cpf}_{ts}.pdf"
    caminho = str(_RELATORIOS_DIR / nome_arquivo)

    doc = SimpleDocTemplate(
        caminho, pagesize=A4,
        rightMargin=1.8 * cm, leftMargin=1.8 * cm,
        topMargin=2.2 * cm, bottomMargin=2.2 * cm,
        title=f"Análise Previdenciária — {caso.nome}",
        author=RESPONSAVEL_RELATORIO,
    )

    est = _estilos()
    story = []

    if "capa" in secoes:
        story.extend(_capa(caso, competencias, confronto, resultados_calculo, est))

    if "resumo" in secoes:
        story.extend(_resumo(caso, competencias, confronto, resultados_calculo, est))

    if "graficos" in secoes:
        story.extend(_secao_graficos(caso, competencias, resultados_calculo, est))

    if "periodos" in secoes:
        story.extend(_periodos(competencias, est))

    if "tabela" in secoes:
        story.extend(_tabela_competencias(competencias, est))

    if "confronto" in secoes:
        story.extend(_secao_confronto(confronto, est))

    if "calculo" in secoes:
        story.extend(_secao_calculo(resultados_calculo, competencias, est))

    if "inconsistencias" in secoes and confronto:
        story.extend(_secao_inconsistencias(confronto, est))

    doc.build(story, onLaterPages=_rodape, onFirstPage=_rodape)
    logger.info("Relatório gerado: %s", caminho)
    return caminho


# ── Seções ───────────────────────────────────────────────────────────────────

def _capa(caso: Caso, competencias, confronto, resultados, est: dict) -> list:
    from ..engine.periodos import calcular_tempo_contributivo
    tempo = calcular_tempo_contributivo(competencias)
    elegiveis = [r for r in resultados if r.elegivel]
    melhor_rmi = elegiveis[0].rmi if elegiveis else None

    items = []

    # Fundo escuro no topo da capa — simulado com tabela
    capa_dados = [[Paragraph("ANÁLISE PREVIDENCIÁRIA", est["titulo"])]]
    capa_tbl = Table(capa_dados, colWidths=[A4[0] - 3.6 * cm])
    capa_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _AZUL_ESC),
        ("TOPPADDING", (0, 0), (-1, -1), 28),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 28),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    items.append(capa_tbl)
    items.append(Spacer(1, 0.6 * cm))

    # Linha azul decorativa
    items.append(HRFlowable(width="100%", thickness=3, color=_AZUL_MED))
    items.append(Spacer(1, 0.6 * cm))

    # Dados do segurado em tabela 2 colunas
    segurado_dados = [
        [Paragraph("<b>Segurado</b>", est["label_cinza"]),
         Paragraph(caso.nome, est["subtitulo"])],
        [Paragraph("<b>CPF</b>", est["label_cinza"]),
         Paragraph(_fmt_cpf(caso.cpf), est["normal"])],
        [Paragraph("<b>Data de nascimento</b>", est["label_cinza"]),
         Paragraph(caso.data_nascimento.strftime("%d/%m/%Y"), est["normal"])],
        [Paragraph("<b>Tempo contributivo</b>", est["label_cinza"]),
         Paragraph(f"{tempo.anos} anos e {tempo.meses} meses", est["normal"])],
    ]
    if melhor_rmi is not None:
        segurado_dados.append([
            Paragraph("<b>Melhor RMI calculado</b>", est["label_cinza"]),
            Paragraph(f"R$ {melhor_rmi:,.2f}", est["destaque"]),
        ])

    t_seg = Table(segurado_dados, colWidths=[5 * cm, A4[0] - 3.6 * cm - 5 * cm])
    t_seg.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    items.append(t_seg)
    items.append(Spacer(1, 1 * cm))

    # Stats rápidos
    n_fontes = len({c.fonte.value for c in competencias})
    n_meses = len({c.competencia for c in competencias})
    n_inconsistencias = (
        len(confronto.divergencias_valor) + len(confronto.sobreposicoes)
        if confronto else 0
    )

    stats_dados = [[
        Paragraph(f"<b>{n_meses}</b><br/>competências", est["normal"]),
        Paragraph(f"<b>{tempo.anos}a {tempo.meses}m</b><br/>tempo contributivo", est["normal"]),
        Paragraph(f"<b>{n_fontes}</b><br/>fonte(s) documentais", est["normal"]),
        Paragraph(f"<b>{n_inconsistencias}</b><br/>inconsistências", est["normal"]),
    ]]
    t_stats = Table(stats_dados, colWidths=[(A4[0] - 3.6 * cm) / 4] * 4)
    t_stats.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _AZUL),
        ("TEXTCOLOR", (0, 0), (-1, -1), _BRANCO),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, _AZUL_CL),
        ("ROUNDEDCORNERS", [6]),
    ]))
    items.append(t_stats)
    items.append(Spacer(1, 1.5 * cm))

    # Rodapé da capa
    items.append(HRFlowable(width="100%", thickness=0.5, color=_CINZA_MED))
    items.append(Spacer(1, 0.3 * cm))
    items.append(Paragraph(
        f"Data de elaboração: <b>{date.today().strftime('%d/%m/%Y')}</b>   ·   "
        f"Responsável: <b>{RESPONSAVEL_RELATORIO}</b>",
        est["pequeno"],
    ))
    items.append(Spacer(1, 0.3 * cm))
    items.append(Paragraph(
        "Este documento é de análise técnica e não substitui a decisão administrativa ou judicial do INSS.",
        est["aviso"],
    ))
    items.append(PageBreak())
    return items


def _resumo(caso: Caso, competencias: List[Competencia], confronto, resultados, est: dict) -> list:
    from ..engine.periodos import calcular_tempo_contributivo
    tempo = calcular_tempo_contributivo(competencias)
    fontes = sorted({c.fonte.value for c in competencias})
    elegiveis = [r for r in resultados if r.elegivel]
    melhor = elegiveis[0] if elegiveis else None
    n_inconsistencias = (
        len(confronto.divergencias_valor) + len(confronto.sobreposicoes)
        if confronto else 0
    )

    items = _titulo_secao("RESUMO EXECUTIVO", est, "📊")

    # RMI em destaque
    if melhor:
        rmi_dados = [[
            Paragraph("Melhor resultado elegível:", est["rmi_titulo"]),
            Paragraph(f"R$ {melhor.rmi:,.2f}", est["rmi_valor"]),
            Paragraph(melhor.regra, est["pequeno"]),
        ]]
        t_rmi = Table(rmi_dados, colWidths=[4.5 * cm, 6 * cm, A4[0] - 3.6 * cm - 10.5 * cm])
        t_rmi.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0a3020")),
            ("LINEAFTER", (0, 0), (0, 0), 2, _VERDE),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 1.5, _VERDE),
            ("ROUNDEDCORNERS", [6]),
        ]))
        items.append(t_rmi)
        items.append(Spacer(1, 0.5 * cm))

    # Tabela de resumo
    resumo_dados = [["Campo", "Valor"]]
    resumo_dados += [
        ["Segurado", caso.nome],
        ["CPF", _fmt_cpf(caso.cpf)],
        ["Data de nascimento", caso.data_nascimento.strftime("%d/%m/%Y")],
        ["Tempo contributivo total", f"{tempo.anos} anos e {tempo.meses} meses ({tempo.total_meses} meses)"],
        ["Competências registradas", str(len(competencias))],
        ["Meses únicos", str(len({c.competencia for c in competencias}))],
        ["Fontes documentais consultadas", ", ".join(fontes) or "Nenhuma"],
        ["Regras elegíveis", str(len(elegiveis))],
        ["Inconsistências encontradas", str(n_inconsistencias)],
    ]

    cw = [(A4[0] - 3.6 * cm) * 0.35, (A4[0] - 3.6 * cm) * 0.65]
    t = _tabela(resumo_dados, cw, cor_header=_AZUL_MED)
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
    ]))
    items.append(t)
    items.append(Spacer(1, 0.5 * cm))
    return items


def _secao_graficos(caso: Caso, competencias: List[Competencia], resultados: list, est: dict) -> list:
    items = [PageBreak()] + _titulo_secao("GRÁFICOS E VISUALIZAÇÕES", est, "📈")

    # ── Gráfico 1: Distribuição por fonte (pizza) ────────────────────────
    por_fonte: dict[str, float] = {}
    for c in competencias:
        por_fonte[c.fonte.value] = por_fonte.get(c.fonte.value, 0) + float(c.base_contribuicao or 0)

    if por_fonte:
        items.append(Paragraph("Distribuição do total de contribuições por fonte documental", est["pequeno"]))
        items.append(Spacer(1, 0.2 * cm))
        items.append(_grafico_pizza(por_fonte))
        items.append(Spacer(1, 0.6 * cm))

    # ── Gráfico 2: Evolução das contribuições (barras por ano) ──────────
    por_ano: dict[int, float] = {}
    for c in competencias:
        try:
            _m, a = c.competencia.split("/")
            ano = int(a)
            por_ano[ano] = por_ano.get(ano, 0) + float(c.base_contribuicao or 0)
        except Exception:
            pass

    if por_ano:
        items.append(Paragraph("Soma das bases de contribuição por ano", est["pequeno"]))
        items.append(Spacer(1, 0.2 * cm))
        items.append(_grafico_barras_anuais(por_ano))
        items.append(Spacer(1, 0.6 * cm))

    # ── Gráfico 3: Comparativo de RMI entre regras elegíveis ────────────
    elegiveis = [r for r in resultados if r.elegivel]
    if len(elegiveis) >= 2:
        items.append(Paragraph("Comparativo de RMI entre as regras elegíveis", est["pequeno"]))
        items.append(Spacer(1, 0.2 * cm))
        items.append(_grafico_comparativo_rmi(elegiveis))
        items.append(Spacer(1, 0.4 * cm))

    return items


def _grafico_pizza(por_fonte: dict) -> Drawing:
    w, h = 16 * cm, 7 * cm
    d = Drawing(w, h)

    pie = Pie()
    pie.x = 1 * cm
    pie.y = 0.5 * cm
    pie.width = 5.5 * cm
    pie.height = 5.5 * cm

    labels_list = list(por_fonte.keys())
    values_list = [v for v in por_fonte.values()]
    total = sum(values_list) or 1

    pie.data = values_list
    pie.labels = [f"{k}" for k in labels_list]
    pie.simpleLabels = 0
    pie.sideLabels = 1

    for i, fonte in enumerate(labels_list):
        cor_hex = _GRAF_CORES[i % len(_GRAF_CORES)]
        pie.slices[i].fillColor = colors.HexColor(cor_hex)
        pie.slices[i].strokeColor = _BRANCO
        pie.slices[i].strokeWidth = 1
        pie.slices[i].labelRadius = 1.2

    d.add(pie)

    # Legenda
    x_leg = 8 * cm
    y_leg = h - 0.8 * cm
    for i, (fonte, val) in enumerate(por_fonte.items()):
        cor = colors.HexColor(_GRAF_CORES[i % len(_GRAF_CORES)])
        d.add(Rect(x_leg, y_leg - i * 0.7 * cm, 0.35 * cm, 0.35 * cm,
                   fillColor=cor, strokeColor=cor))
        pct = val / total * 100
        d.add(String(x_leg + 0.5 * cm, y_leg - i * 0.7 * cm + 2,
                     f"{fonte}: R$ {val:,.0f} ({pct:.1f}%)",
                     fontSize=8, fillColor=_CINZA_ESC))

    return d


def _grafico_barras_anuais(por_ano: dict) -> Drawing:
    anos = sorted(por_ano.keys())
    valores = [por_ano[a] / 12 for a in anos]  # média mensal do ano

    w = 16.4 * cm
    h = 6 * cm
    d = Drawing(w, h)

    if not anos:
        return d

    bar = VerticalBarChart()
    bar.x = 1.5 * cm
    bar.y = 1 * cm
    bar.width = w - 2.5 * cm
    bar.height = h - 1.8 * cm

    bar.data = [valores]
    bar.categoryAxis.categoryNames = [str(a) for a in anos]
    bar.categoryAxis.labels.fontSize = 7
    bar.categoryAxis.labels.angle = 45 if len(anos) > 10 else 0
    bar.categoryAxis.labels.dx = -4 if len(anos) > 10 else 0
    bar.categoryAxis.labels.dy = -6 if len(anos) > 10 else 0
    bar.categoryAxis.labels.fillColor = _CINZA_TXT
    bar.valueAxis.labels.fontSize = 7
    bar.valueAxis.labels.fillColor = _CINZA_TXT
    bar.valueAxis.labelTextFormat = lambda v: f"R$ {v:,.0f}"
    bar.barSpacing = 2
    bar.groupSpacing = 4
    bar.bars[0].fillColor = _AZUL_MED
    bar.bars[0].strokeColor = _AZUL
    bar.bars[0].strokeWidth = 0.5

    # Linhas de grade horizontais
    bar.valueAxis.gridStrokeColor = _CINZA_MED
    bar.valueAxis.gridStrokeDashArray = [2, 2]
    bar.valueAxis.visibleGrid = 1

    d.add(bar)

    # Título do eixo Y
    d.add(String(2, h / 2, "Média mensal por ano",
                 fontSize=7, fillColor=_CINZA_TXT))

    return d


def _grafico_comparativo_rmi(elegiveis: list) -> Drawing:
    w = 16.4 * cm
    h = max(4 * cm, len(elegiveis) * 1.2 * cm + 1.5 * cm)
    d = Drawing(w, h)

    max_rmi = max(float(r.rmi) for r in elegiveis) or 1
    bar_max_w = w - 7 * cm
    bar_h = 0.7 * cm
    y_start = h - 1 * cm

    for i, r in enumerate(elegiveis):
        y = y_start - i * 1.2 * cm
        # Label regra (truncado)
        nome = r.regra[:32] + "…" if len(r.regra) > 32 else r.regra
        d.add(String(0.1 * cm, y - bar_h / 2 + 2, nome,
                     fontSize=7, fillColor=_CINZA_ESC))
        # Barra
        bar_w = float(r.rmi) / max_rmi * bar_max_w
        cor_bar = _VERDE if i == 0 else colors.HexColor(_GRAF_CORES[i % len(_GRAF_CORES)])
        d.add(Rect(5.5 * cm, y - bar_h, bar_w, bar_h,
                   fillColor=cor_bar, strokeColor=cor_bar))
        # Valor
        d.add(String(5.5 * cm + bar_w + 0.2 * cm, y - bar_h / 2 + 2,
                     f"R$ {float(r.rmi):,.2f}",
                     fontSize=8, fillColor=_CINZA_ESC, fontName="Helvetica-Bold"))

    return d


def _periodos(competencias: List[Competencia], est: dict) -> list:
    items = [PageBreak()] + _titulo_secao("PERÍODOS CONTRIBUTIVOS", est, "📅")

    por_emp: dict = {}
    for c in sorted(competencias, key=lambda x: _comp_key(x.competencia)):
        chave = (c.empregador_nome or "Não identificado", c.tipo_vinculo.value if c.tipo_vinculo else "—")
        por_emp.setdefault(chave, []).append(c)

    cw = A4[0] - 3.6 * cm
    dados = [["Empregador / Organização", "Tipo vínculo", "Início", "Fim", "Duração", "Fontes"]]
    for (emp, tipo), comps in list(por_emp.items())[:60]:
        sorted_c = sorted(comps, key=lambda x: _comp_key(x.competencia))
        inicio = sorted_c[0].competencia
        fim = sorted_c[-1].competencia
        meses = len({c.competencia for c in comps})
        fontes = ", ".join(sorted({c.fonte.value for c in comps}))
        dados.append([
            Paragraph(emp[:50], est["normal"]),
            tipo, inicio, fim,
            f"{meses // 12}a {meses % 12}m",
            fontes,
        ])

    t = _tabela(dados, [6.5 * cm, 2.5 * cm, 2 * cm, 2 * cm, 1.8 * cm, 2.7 * cm])
    items.append(t)
    items.append(Spacer(1, 0.4 * cm))
    return items


def _tabela_competencias(competencias: List[Competencia], est: dict) -> list:
    items = [PageBreak()] + _titulo_secao("TABELA COMPLETA DE COMPETÊNCIAS", est, "📋")

    cabecalho = ["Competência", "Empregador", "Tipo", "Rem. Bruta", "Rem. Atualizada", "Fonte"]
    dados = [cabecalho]
    for c in sorted(competencias, key=lambda x: _comp_key(x.competencia)):
        fonte_val = c.fonte.value if c.fonte else "—"
        dados.append([
            c.competencia,
            Paragraph((c.empregador_nome or "—")[:42], est["normal"]),
            c.tipo_vinculo.value if c.tipo_vinculo else "—",
            f"R$ {c.remuneracao_bruta:,.2f}" if c.remuneracao_bruta else "—",
            f"R$ {c.remuneracao_atualizada:,.2f}" if c.remuneracao_atualizada else "—",
            fonte_val,
        ])

    t = _tabela(dados, [2 * cm, 5.5 * cm, 2 * cm, 2.6 * cm, 2.6 * cm, 1.8 * cm])
    items.append(t)
    items.append(Spacer(1, 0.4 * cm))
    return items


def _secao_confronto(confronto, est: dict) -> list:
    items = [PageBreak()] + _titulo_secao("CONFRONTO DE FONTES", est, "🔍")

    if not confronto:
        items.append(Paragraph("Confronto não executado.", est["normal"]))
        return items

    # Stats de confronto
    stats_d = [[
        Paragraph(f"<b>{len(confronto.competencias_apenas_fontes_externas)}</b><br/>Ausentes no CNIS", est["normal"]),
        Paragraph(f"<b>{len(confronto.divergencias_valor)}</b><br/>Divergências de valor", est["normal"]),
        Paragraph(f"<b>{len(confronto.gaps)}</b><br/>Gaps sem contribuição", est["normal"]),
        Paragraph(f"<b>{len(getattr(confronto, 'pendencias_cnis', []))}</b><br/>Pendências CNIS", est["normal"]),
    ]]
    cw4 = [(A4[0] - 3.6 * cm) / 4] * 4
    t_stats = Table(stats_d, colWidths=cw4)
    t_stats.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _CINZA_CL),
        ("BOX", (0, 0), (-1, -1), 0.5, _CINZA_MED),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, _CINZA_MED),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    items.append(t_stats)
    items.append(Spacer(1, 0.4 * cm))

    if getattr(confronto, "pendencias_cnis", []):
        items.append(Paragraph(
            "ℹ  Pendências CNIS são de caráter informativo e NÃO impedem o cômputo das competências para fins de benefício.",
            est["aviso"],
        ))

    # Divergências de valor
    divs = getattr(confronto, "divergencias_valor", [])
    if divs:
        items.append(Spacer(1, 0.3 * cm))
        items.append(Paragraph("Divergências de valor (> 5%):", est["normal"]))
        div_dados = [["Competência", "Empregador", "Fonte A", "Valor A", "Fonte B", "Valor B", "Diferença"]]
        for dv in divs[:30]:
            div_dados.append([
                getattr(dv, "competencia", "—"),
                Paragraph(getattr(dv, "empregador", "—")[:30], est["pequeno"]),
                getattr(dv, "fonte_a", "—"),
                f"R$ {float(getattr(dv, 'valor_a', 0)):,.2f}",
                getattr(dv, "fonte_b", "—"),
                f"R$ {float(getattr(dv, 'valor_b', 0)):,.2f}",
                f"{float(getattr(dv, 'diff_pct', 0)):.1f}%",
            ])
        t = _tabela(div_dados,
                    [2 * cm, 4 * cm, 1.5 * cm, 2.2 * cm, 1.5 * cm, 2.2 * cm, 2 * cm],
                    cor_header=_AMARELO, cor_header_txt=_CINZA_ESC)
        items.append(t)

    return items


def _secao_calculo(resultados: list, competencias: list, est: dict) -> list:
    items = [PageBreak()] + _titulo_secao("CÁLCULO DO SALÁRIO DE BENEFÍCIO", est, "🧮")

    elegiveis = [r for r in resultados if r.elegivel]

    if elegiveis:
        melhor = elegiveis[0]

        # Callout do melhor resultado
        melhor_d = [[
            Paragraph("Regra mais vantajosa", est["rmi_titulo"]),
            Paragraph(f"R$ {melhor.rmi:,.2f}", est["rmi_valor"]),
            Paragraph(melhor.regra, est["pequeno"]),
        ]]
        t_m = Table(melhor_d, colWidths=[4 * cm, 6 * cm, A4[0] - 3.6 * cm - 10 * cm])
        t_m.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0a3020")),
            ("BOX", (0, 0), (-1, -1), 2, _VERDE),
            ("LINEBEFORE", (0, 0), (0, -1), 6, _VERDE),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        items.append(t_m)
        items.append(Spacer(1, 0.6 * cm))

    # Tabela comparativa de todas as regras
    reg_dados = [["#", "Regra", "Elegível", "Tempo", "Média", "Coef.", "RMI"]]
    for i, r in enumerate(resultados, 1):
        elegivel_txt = "✓" if r.elegivel else "✗"
        if r.elegivel:
            tc = r.tempo_contributivo
            tempo_txt = f"{tc.anos}a {tc.meses}m" if tc else "—"
            reg_dados.append([
                str(i), Paragraph(r.regra, est["normal"]), elegivel_txt,
                tempo_txt,
                f"R$ {r.media_contribuicoes:,.2f}" if r.media_contribuicoes else "—",
                f"{float(r.coeficiente)*100:.0f}%",
                f"R$ {r.rmi:,.2f}",
            ])
        else:
            reg_dados.append([
                str(i),
                Paragraph(r.regra, est["normal"]),
                elegivel_txt,
                Paragraph(r.motivo_inelegibilidade or "", est["pequeno"]),
                "—", "—", "—",
            ])

    cw = [0.7 * cm, 5.5 * cm, 1.2 * cm, 2.4 * cm, 2.5 * cm, 1.4 * cm, 2.3 * cm]
    t = _tabela(reg_dados, cw)

    # Destacar linhas elegíveis
    style_extra = []
    for i, r in enumerate(resultados, 1):
        if r.elegivel:
            style_extra.append(("BACKGROUND", (2, i), (2, i), _VERDE))
            style_extra.append(("TEXTCOLOR", (2, i), (2, i), _BRANCO))
            style_extra.append(("TEXTCOLOR", (6, i), (6, i), _VERDE))
            style_extra.append(("FONTNAME", (6, i), (6, i), "Helvetica-Bold"))
        else:
            style_extra.append(("TEXTCOLOR", (2, i), (2, i), _VERMELHO))
            style_extra.append(("TEXTCOLOR", (3, i), (6, i), _CINZA_TXT))

    t.setStyle(TableStyle(style_extra))
    items.append(t)
    items.append(Spacer(1, 0.4 * cm))

    # Detalhamento por regra elegível
    for r in elegiveis:
        items.extend(_detalhe_regra(r, est))

    return items


def _detalhe_regra(r, est: dict) -> list:
    items = []
    d = r.detalhamento or {}

    hdr_d = [[Paragraph(f"Detalhamento: {r.regra}", est["normal"])]]
    t_hdr = Table(hdr_d, colWidths=[A4[0] - 3.6 * cm])
    t_hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _AZUL),
        ("TEXTCOLOR", (0, 0), (-1, -1), _BRANCO),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    items.append(Spacer(1, 0.3 * cm))
    items.append(t_hdr)

    det_dados = []
    for k, v in d.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                det_dados.append([f"{k} › {kk}", str(vv)])
        else:
            det_dados.append([str(k), str(v)])

    if det_dados:
        cw = [(A4[0] - 3.6 * cm) * 0.4, (A4[0] - 3.6 * cm) * 0.6]
        t = _tabela([["Campo", "Valor"]] + det_dados, cw, cor_header=_AZUL_MED)
        items.append(t)

    return items


def _secao_inconsistencias(confronto, est: dict) -> list:
    items = _titulo_secao("INCONSISTÊNCIAS DETECTADAS", est, "⚠")
    total = len(getattr(confronto, "divergencias_valor", []))
    if total == 0:
        items.append(Paragraph("✓  Nenhuma inconsistência relevante detectada.", est["normal"]))
    else:
        items.append(Paragraph(
            f"Foram detectadas <b>{total}</b> divergência(s) de valor entre as fontes.",
            est["normal"],
        ))
    return items


# ── Resumo Mensal ────────────────────────────────────────────────────────────

def gerar_resumo_mensal_pdf(caso: Caso, linhas: list, data_ref: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo = f"resumo_mensal_{caso.cpf}_{ts}.pdf"
    caminho = str(_RELATORIOS_DIR / nome_arquivo)

    doc = SimpleDocTemplate(
        caminho, pagesize=A4,
        rightMargin=1.5 * cm, leftMargin=1.5 * cm,
        topMargin=2.2 * cm, bottomMargin=2.2 * cm,
        title=f"Resumo Mensal — {caso.nome}",
        author=RESPONSAVEL_RELATORIO,
    )

    est = _estilos()
    story = []

    # Cabeçalho
    capa_d = [[Paragraph("RESUMO MENSAL DE CONTRIBUIÇÕES", est["titulo"])]]
    capa_tbl = Table(capa_d, colWidths=[A4[0] - 3 * cm])
    capa_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _AZUL_ESC),
        ("TOPPADDING", (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
    ]))
    story.append(capa_tbl)
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph(
        f"<b>Segurado:</b> {caso.nome}  ·  <b>CPF:</b> {_fmt_cpf(caso.cpf)}  ·  "
        f"<b>Referência INPC:</b> {data_ref}  ·  <b>Total:</b> {len(linhas)} competências",
        est["normal"],
    ))

    n_cortados = sum(1 for l in linhas if l[8])
    if n_cortados:
        story.append(Paragraph(
            f"⚠  {n_cortados} competência(s) com corte de teto (base efetiva inferior à soma das fontes).",
            est["aviso"],
        ))

    story.append(Spacer(1, 0.4 * cm))

    # Gráfico: base efetiva vs base somada (barras)
    if linhas:
        story.append(_grafico_resumo_mensal(linhas, est))
        story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph(
        "ℹ  Linhas destacadas em laranja indicam corte de teto. "
        "Base corrigida INPC = base efetiva a valor presente na data de referência.",
        est["pequeno"],
    ))
    story.append(Spacer(1, 0.3 * cm))

    # Tabela principal
    _LARANJA_D = colors.HexColor("#c87000")
    _LARANJA_F = colors.HexColor("#fff3dc")

    cabecalho = ["Comp.", "Fontes / Registros", "Base somada",
                 "Teto época", "Corte", "Base efetiva",
                 "Base corrig.\nINPC", "Teto corrig.\nINPC"]
    dados = [cabecalho]
    estilos_extra = []

    for i, linha in enumerate(linhas):
        comp, fontes, soma_base, teto_epoca, corte, base_efetiva, base_corrigida, teto_corrigido, foi_cortado = linha
        dados.append([comp, Paragraph(fontes, est["pequeno"]),
                      soma_base, teto_epoca, corte,
                      base_efetiva, base_corrigida, teto_corrigido])
        row = i + 1
        if foi_cortado:
            estilos_extra.append(("BACKGROUND", (0, row), (-1, row), _LARANJA_F))
            estilos_extra.append(("TEXTCOLOR", (0, row), (-1, row), _LARANJA_D))
            estilos_extra.append(("FONTNAME", (0, row), (-1, row), "Helvetica-Bold"))

    cw = [1.7 * cm, 3.8 * cm, 2.3 * cm, 2.2 * cm, 2.2 * cm, 2.3 * cm, 2.3 * cm, 2.3 * cm]
    t = _tabela(dados, cw)
    t.setStyle(TableStyle(estilos_extra))
    story.append(t)
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(
        "Teto corrigido INPC = teto histórico da competência atualizado pela mesma variação INPC.",
        est["pequeno"],
    ))

    doc.build(story, onLaterPages=_rodape, onFirstPage=_rodape)
    logger.info("Resumo mensal PDF gerado: %s", caminho)
    return caminho


def _grafico_resumo_mensal(linhas: list, est: dict) -> Drawing:
    """Gráfico de barras: base efetiva vs teto da época — últimas 36 competências."""
    sample = linhas[-36:] if len(linhas) > 36 else linhas

    w = 16.4 * cm
    h = 5 * cm
    d = Drawing(w, h)

    try:
        from reportlab.graphics.charts.barcharts import VerticalBarChart as VBC
        bar = VBC()
        bar.x = 1.5 * cm
        bar.y = 1 * cm
        bar.width = w - 2.5 * cm
        bar.height = h - 1.8 * cm

        def _parse_r(s: str) -> float:
            try:
                return float(s.replace("R$ ", "").replace(".", "").replace(",", ".").strip())
            except Exception:
                return 0.0

        vals_base = [_parse_r(l[5]) for l in sample]   # base_efetiva
        vals_teto = [_parse_r(l[3]) for l in sample]   # teto_epoca

        bar.data = [vals_teto, vals_base]
        bar.categoryAxis.categoryNames = [l[0] for l in sample]
        bar.categoryAxis.labels.fontSize = 6
        bar.categoryAxis.labels.angle = 60
        bar.categoryAxis.labels.dx = -4
        bar.categoryAxis.labels.dy = -8
        bar.categoryAxis.labels.fillColor = _CINZA_TXT
        bar.valueAxis.labels.fontSize = 7
        bar.valueAxis.labels.fillColor = _CINZA_TXT
        bar.valueAxis.labelTextFormat = lambda v: f"R$ {v:,.0f}"
        bar.valueAxis.visibleGrid = 1
        bar.valueAxis.gridStrokeColor = _CINZA_MED
        bar.barSpacing = 1
        bar.groupSpacing = 3
        bar.bars[0].fillColor = _CINZA_MED
        bar.bars[0].strokeColor = colors.HexColor("#b0b8c8")
        bar.bars[1].fillColor = _AZUL_MED
        bar.bars[1].strokeColor = _AZUL

        d.add(bar)

        # Legenda
        d.add(Rect(1.5 * cm, h - 0.6 * cm, 0.4 * cm, 0.3 * cm,
                   fillColor=_CINZA_MED, strokeColor=_CINZA_MED))
        d.add(String(2.1 * cm, h - 0.55 * cm, "Teto época", fontSize=7, fillColor=_CINZA_TXT))
        d.add(Rect(5 * cm, h - 0.6 * cm, 0.4 * cm, 0.3 * cm,
                   fillColor=_AZUL_MED, strokeColor=_AZUL))
        d.add(String(5.6 * cm, h - 0.55 * cm, "Base efetiva", fontSize=7, fillColor=_CINZA_TXT))

    except Exception as exc:
        logger.warning("Erro ao gerar gráfico resumo mensal: %s", exc)

    return d


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_cpf(cpf: str) -> str:
    d = "".join(c for c in cpf if c.isdigit())
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else cpf


def _comp_key(competencia: str) -> int:
    try:
        m, a = competencia.split("/")
        return int(a) * 100 + int(m)
    except ValueError:
        return 0
