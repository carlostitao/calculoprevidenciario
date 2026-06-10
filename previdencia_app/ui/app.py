"""Janela principal da aplicação."""
from __future__ import annotations

import logging
import threading
from typing import Optional

import customtkinter as ctk

from ..config import UI_APARENCIA_PADRAO, UI_TEMA_COR, UI_LARGURA_MIN, UI_ALTURA_MIN
from ..db import init_db, CasoRepository
from ..models import Caso
from .casos_sidebar import CasosSidebar
from .documents_panel import DocumentsPanel
from .competencias_table import CompetenciasTable
from .confronto_panel import ConfrontoPanel
from .calculo_panel import CalculoPanel
from .relatorio_panel import RelatorioPanel
from .resumo_mensal_panel import ResumoMensalPanel
from .theme import AZUL_PRIMARIO, AZUL_CLARO, CINZA_TEXTO, BG_CARD, font_secao, font_pequeno

logger = logging.getLogger(__name__)

ctk.set_appearance_mode(UI_APARENCIA_PADRAO)
ctk.set_default_color_theme(UI_TEMA_COR)

_TABS = [
    ("📄  Documentos",     "Documentos"),
    ("📊  Competências",   "Competências"),
    ("🔍  Confronto",      "Confronto"),
    ("🧮  Cálculo",        "Cálculo"),
    ("📅  Resumo Mensal",  "Resumo Mensal"),
    ("📑  Relatório",      "Relatório"),
]


class App(ctk.CTk):

    def __init__(self) -> None:
        super().__init__()
        init_db()

        self.title("Sistema de Análise Previdenciária")
        self.minsize(UI_LARGURA_MIN, UI_ALTURA_MIN)
        self.geometry(f"{UI_LARGURA_MIN}x{UI_ALTURA_MIN}")

        self._caso_ativo: Optional[Caso] = None
        self._custo_ai: float = 0.0

        self._build_layout()

    # ── Layout ──────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Barra superior
        self._topbar = ctk.CTkFrame(self, height=52, corner_radius=0,
                                    fg_color=(AZUL_PRIMARIO, "#0d1b35"))
        self._topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._topbar.grid_propagate(False)
        self._build_topbar()

        # Sidebar de casos
        self._sidebar = CasosSidebar(self, width=240, on_select=self._on_caso_selecionado)
        self._sidebar.set_on_deletar(self._on_caso_deletado)
        self._sidebar.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=8)

        # Área de abas
        self._tabs = ctk.CTkTabview(self)
        self._tabs.grid(row=1, column=1, sticky="nsew", padx=8, pady=8)

        for label, key in _TABS:
            self._tabs.add(label)

        def tab(key: str) -> ctk.CTkFrame:
            for label, k in _TABS:
                if k == key:
                    return self._tabs.tab(label)
            raise KeyError(key)

        self._tab = tab

        self._panel_docs  = DocumentsPanel(tab("Documentos"), app=self)
        self._panel_docs.pack(fill="both", expand=True)

        self._panel_comp  = CompetenciasTable(tab("Competências"), app=self)
        self._panel_comp.pack(fill="both", expand=True)

        self._panel_conf  = ConfrontoPanel(tab("Confronto"), app=self)
        self._panel_conf.pack(fill="both", expand=True)

        self._panel_calc  = CalculoPanel(tab("Cálculo"), app=self)
        self._panel_calc.pack(fill="both", expand=True)

        self._panel_resumo = ResumoMensalPanel(tab("Resumo Mensal"), app=self)
        self._panel_resumo.pack(fill="both", expand=True)

        self._panel_rel   = RelatorioPanel(tab("Relatório"), app=self)
        self._panel_rel.pack(fill="both", expand=True)

    def _build_topbar(self) -> None:
        self._topbar.grid_columnconfigure(3, weight=1)

        # Ícone + título
        ctk.CTkLabel(
            self._topbar,
            text="⚖",
            font=ctk.CTkFont(size=22),
            text_color="#ffffff",
        ).grid(row=0, column=0, padx=(16, 4), pady=10)

        ctk.CTkLabel(
            self._topbar,
            text="Análise Previdenciária",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#ffffff",
        ).grid(row=0, column=1, padx=(0, 24), pady=10)

        # Badge do caso ativo
        self._badge_caso = ctk.CTkLabel(
            self._topbar,
            text="Nenhum caso aberto",
            font=ctk.CTkFont(size=11),
            text_color="#aaccee",
            anchor="w",
        )
        self._badge_caso.grid(row=0, column=3, padx=8, sticky="ew")

        # Botão novo caso
        ctk.CTkButton(
            self._topbar,
            text="＋  Novo Caso",
            width=120,
            height=32,
            corner_radius=6,
            fg_color="#2a4a7a",
            hover_color="#3a5a8a",
            text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._novo_caso,
        ).grid(row=0, column=4, padx=6, pady=10)

        # Toggle de aparência
        ctk.CTkButton(
            self._topbar,
            text="☀ / ☾",
            width=70,
            height=32,
            corner_radius=6,
            fg_color="#2a4a7a",
            hover_color="#3a5a8a",
            text_color="#ffffff",
            command=self._toggle_aparencia,
        ).grid(row=0, column=5, padx=(0, 16), pady=10)

    # ── Ações da topbar ──────────────────────────────────────────────────────

    def _novo_caso(self) -> None:
        from .dialogs import NovoCasoDialog
        dlg = NovoCasoDialog(self)
        self.wait_window(dlg)
        if dlg.resultado:
            self._sidebar.atualizar()
            self._on_caso_selecionado(dlg.resultado)

    def _toggle_aparencia(self) -> None:
        atual = ctk.get_appearance_mode().lower()
        novo = "light" if atual == "dark" else "dark"
        ctk.set_appearance_mode(novo)

    # ── Seleção / deleção de caso ────────────────────────────────────────────

    def _on_caso_selecionado(self, caso: Caso) -> None:
        self._caso_ativo = caso
        self._atualizar_status()
        self._panel_docs.carregar_caso(caso)
        self._panel_comp.carregar_caso(caso)
        self._panel_conf.carregar_caso(caso)
        self._panel_calc.carregar_caso(caso)
        self._panel_resumo.carregar_caso(caso)
        self._panel_rel.carregar_caso(caso)

    def _on_caso_deletado(self, caso_id: int) -> None:
        if self._caso_ativo and self._caso_ativo.id == caso_id:
            self._caso_ativo = None
            self._badge_caso.configure(text="Nenhum caso aberto")
            for panel in (self._panel_docs, self._panel_comp, self._panel_conf,
                          self._panel_calc, self._panel_resumo, self._panel_rel):
                panel.carregar_caso(None)

    # ── Status ───────────────────────────────────────────────────────────────

    def _atualizar_status(self) -> None:
        if self._caso_ativo:
            c = self._caso_ativo
            self._badge_caso.configure(
                text=f"📂  {c.nome}  ·  CPF {_fmt_cpf(c.cpf)}  ·  Custo AI: ${self._custo_ai:.4f}"
            )

    def atualizar_custo_ai(self, custo: float) -> None:
        self._custo_ai += custo
        self.after(0, self._atualizar_status)

    @property
    def caso_ativo(self) -> Optional[Caso]:
        return self._caso_ativo


def _fmt_cpf(cpf: str) -> str:
    d = "".join(c for c in cpf if c.isdigit())
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else cpf
