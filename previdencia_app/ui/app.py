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

logger = logging.getLogger(__name__)

ctk.set_appearance_mode(UI_APARENCIA_PADRAO)
ctk.set_default_color_theme(UI_TEMA_COR)


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
        self._topbar = ctk.CTkFrame(self, height=44, corner_radius=0)
        self._topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._build_topbar()

        # Sidebar de casos
        self._sidebar = CasosSidebar(self, width=220, on_select=self._on_caso_selecionado)
        self._sidebar.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=8)

        # Área de abas (área principal)
        self._tabs = ctk.CTkTabview(self)
        self._tabs.grid(row=1, column=1, sticky="nsew", padx=8, pady=8)

        for nome in ["Documentos", "Competências", "Confronto", "Cálculo", "Relatório"]:
            self._tabs.add(nome)

        self._panel_docs = DocumentsPanel(self._tabs.tab("Documentos"), app=self)
        self._panel_docs.pack(fill="both", expand=True)

        self._panel_comp = CompetenciasTable(self._tabs.tab("Competências"), app=self)
        self._panel_comp.pack(fill="both", expand=True)

        self._panel_conf = ConfrontoPanel(self._tabs.tab("Confronto"), app=self)
        self._panel_conf.pack(fill="both", expand=True)

        self._panel_calc = CalculoPanel(self._tabs.tab("Cálculo"), app=self)
        self._panel_calc.pack(fill="both", expand=True)

        self._panel_rel = RelatorioPanel(self._tabs.tab("Relatório"), app=self)
        self._panel_rel.pack(fill="both", expand=True)

    def _build_topbar(self) -> None:
        self._topbar.grid_columnconfigure(5, weight=1)

        ctk.CTkButton(self._topbar, text="Novo Caso", width=110, command=self._novo_caso).grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkButton(self._topbar, text="Aparência", width=100, command=self._toggle_aparencia).grid(row=0, column=1, padx=4, pady=8)

        self._lbl_status = ctk.CTkLabel(self._topbar, text="Nenhum caso aberto", anchor="e")
        self._lbl_status.grid(row=0, column=6, padx=12, pady=8, sticky="e")

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

    # ── Seleção de caso ──────────────────────────────────────────────────────

    def _on_caso_selecionado(self, caso: Caso) -> None:
        self._caso_ativo = caso
        self._atualizar_status()
        self._panel_docs.carregar_caso(caso)
        self._panel_comp.carregar_caso(caso)
        self._panel_conf.carregar_caso(caso)
        self._panel_calc.carregar_caso(caso)
        self._panel_rel.carregar_caso(caso)

    # ── Status e custos AI ───────────────────────────────────────────────────

    def _atualizar_status(self) -> None:
        if self._caso_ativo:
            casos = CasoRepository.listar_todos()
            self._lbl_status.configure(
                text=f"Caso: {self._caso_ativo.nome}  |  Total: {len(casos)}  |  Custo AI: ${self._custo_ai:.4f}"
            )

    def atualizar_custo_ai(self, custo: float) -> None:
        """Chamado de qualquer thread para atualizar o custo exibido."""
        self._custo_ai += custo
        self.after(0, self._atualizar_status)

    @property
    def caso_ativo(self) -> Optional[Caso]:
        return self._caso_ativo
