"""Painel de preview e exportação de relatório PDF."""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from ..config import DB_PATH
from .theme import (AZUL_CLARO, AZUL_PRIMARIO, VERDE_OK, AMARELO, CINZA_TEXTO,
                    BG_CARD, BG_CARD2, BG_SEP,
                    font_secao, font_label, font_valor, font_pequeno, secao_header, card)

if TYPE_CHECKING:
    from .app import App

logger = logging.getLogger(__name__)

_SECOES = [
    ("capa",            "📄",  "Capa do relatório",               "Capa profissional com dados do segurado"),
    ("resumo",          "📊",  "Resumo executivo",                "Visão geral: tempo, fontes, inconsistências"),
    ("graficos",        "📈",  "Gráficos e visualizações",        "Evolução das contribuições e distribuição por fonte"),
    ("periodos",        "📅",  "Períodos contributivos",          "Tabela de vínculos por empregador"),
    ("tabela",          "📋",  "Tabela completa de competências", "Todas as competências importadas"),
    ("confronto",       "🔍",  "Confronto de fontes",             "Divergências, ausências e pendências CNIS"),
    ("calculo",         "🧮",  "Cálculo do salário de benefício", "Resultado de todas as regras de aposentadoria"),
    ("inconsistencias", "⚠",   "Inconsistências detectadas",      "Lista de divergências encontradas"),
]


class RelatorioPanel(ctk.CTkFrame):

    def __init__(self, parent, app: "App", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._app = app
        self._caso = None
        self._checks: dict[str, ctk.BooleanVar] = {}
        self._build()

    def _build(self) -> None:
        # Cabeçalho
        hdr = ctk.CTkFrame(self, corner_radius=0, fg_color=(AZUL_PRIMARIO, "#0d1b35"))
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="📑  Geração de Relatório PDF",
                     font=font_secao(), text_color="#ffffff").pack(anchor="w", padx=16, pady=10)

        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        # Seção: seleção de conteúdo
        sh = secao_header(body, "Conteúdo a incluir", AZUL_CLARO)
        sh.pack(fill="x", padx=4, pady=(4, 8))

        # Grid de checkboxes em cards
        grid_frame = ctk.CTkFrame(body, fg_color="transparent")
        grid_frame.pack(fill="x", padx=4)
        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)

        for i, (key, icone, titulo, desc) in enumerate(_SECOES):
            var = ctk.BooleanVar(value=True)
            self._checks[key] = var
            row, col = divmod(i, 2)

            item = card(grid_frame)
            item.grid(row=row, column=col, padx=4, pady=4, sticky="ew")

            inner = ctk.CTkFrame(item, fg_color="transparent")
            inner.pack(fill="x", padx=10, pady=8)

            cb = ctk.CTkCheckBox(inner, text="", variable=var, width=24)
            cb.pack(side="left")

            ctk.CTkLabel(inner, text=icone, font=ctk.CTkFont(size=18)).pack(side="left", padx=(4, 8))

            txt = ctk.CTkFrame(inner, fg_color="transparent")
            txt.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(txt, text=titulo, font=font_valor(), anchor="w").pack(anchor="w")
            ctk.CTkLabel(txt, text=desc, font=font_pequeno(),
                         text_color=CINZA_TEXTO, anchor="w").pack(anchor="w")

        # Separador
        ctk.CTkFrame(body, height=2, fg_color=BG_SEP).pack(fill="x", padx=4, pady=14)

        # Botões de ação
        acoes = ctk.CTkFrame(body, fg_color="transparent")
        acoes.pack(fill="x", padx=4, pady=(0, 6))

        ctk.CTkButton(
            acoes, text="✓  Selecionar todos", width=150, height=32, corner_radius=6,
            fg_color="transparent", border_width=1, border_color=BG_SEP,
            text_color=AZUL_CLARO, font=font_label(),
            command=lambda: [v.set(True) for v in self._checks.values()],
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            acoes, text="✗  Limpar seleção", width=140, height=32, corner_radius=6,
            fg_color="transparent", border_width=1, border_color=BG_SEP,
            text_color=CINZA_TEXTO, font=font_label(),
            command=lambda: [v.set(False) for v in self._checks.values()],
        ).pack(side="left")

        ctk.CTkFrame(body, height=2, fg_color=BG_SEP).pack(fill="x", padx=4, pady=14)

        # Botão principal
        gerar_frame = card(body, border_color=VERDE_OK)
        gerar_frame.pack(fill="x", padx=4, pady=4)
        gerar_inner = ctk.CTkFrame(gerar_frame, fg_color="transparent")
        gerar_inner.pack(fill="x", padx=14, pady=12)

        ctk.CTkButton(
            gerar_inner, text="📄  Gerar PDF",
            width=160, height=40, corner_radius=8,
            font=font_secao(),
            command=self._gerar,
        ).pack(side="left")

        self._lbl_status = ctk.CTkLabel(gerar_inner, text="Selecione um caso para gerar o relatório.",
                                        font=font_label(), text_color=CINZA_TEXTO, anchor="w")
        self._lbl_status.pack(side="left", padx=14, fill="x", expand=True)

    def carregar_caso(self, caso) -> None:
        self._caso = caso
        if caso:
            self._lbl_status.configure(
                text=f"Pronto para gerar relatório de  {caso.nome}.", text_color=CINZA_TEXTO)
        else:
            self._lbl_status.configure(
                text="Selecione um caso para gerar o relatório.", text_color=CINZA_TEXTO)

    def _gerar(self) -> None:
        if not self._caso:
            self._lbl_status.configure(text="⚠  Nenhum caso selecionado.", text_color=AMARELO)
            return

        secoes_ativas = [k for k, v in self._checks.items() if v.get()]
        if not secoes_ativas:
            self._lbl_status.configure(text="⚠  Selecione ao menos uma seção.", text_color=AMARELO)
            return

        self._lbl_status.configure(text="⏳  Gerando PDF...", text_color=CINZA_TEXTO)

        def _trabalho() -> None:
            try:
                from ..export.relatorio_pdf import gerar_relatorio
                from ..db import CompetenciaRepository
                from ..engine.confronto import confrontar
                from ..engine.regras.salario_beneficio import calcular
                from datetime import date

                competencias = CompetenciaRepository.buscar_por_caso(self._caso.id)
                confronto = confrontar(self._caso.id, competencias)
                resultados_calculo = calcular(self._caso, competencias, date.today())

                caminho = gerar_relatorio(
                    caso=self._caso,
                    competencias=competencias,
                    confronto=confronto,
                    resultados_calculo=resultados_calculo,
                    secoes=secoes_ativas,
                )
                self._app.after(0, lambda: self._pos_geracao(caminho))
            except Exception as exc:
                logger.error("Erro ao gerar relatório: %s", exc, exc_info=True)
                self._app.after(0, lambda: self._lbl_status.configure(
                    text=f"Erro: {exc}", text_color="#e74c3c"))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _pos_geracao(self, caminho: str) -> None:
        self._lbl_status.configure(
            text=f"✅  PDF gerado: {Path(caminho).name}", text_color=VERDE_OK)
        try:
            if sys.platform == "win32":
                subprocess.Popen(["start", "", caminho], shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", caminho])
            else:
                subprocess.Popen(["xdg-open", caminho])
        except Exception as exc:
            logger.warning("Não foi possível abrir o PDF: %s", exc)
