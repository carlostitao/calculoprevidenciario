"""Painel de cálculo do salário de benefício."""
from __future__ import annotations

import logging
import threading
from datetime import date
from typing import TYPE_CHECKING, List, Optional

import customtkinter as ctk

from ..db import CompetenciaRepository

if TYPE_CHECKING:
    from .app import App

logger = logging.getLogger(__name__)


class CalculoPanel(ctk.CTkFrame):

    def __init__(self, parent, app: "App", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._app = app
        self._caso = None
        self._build()

    def _build(self) -> None:
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=8, pady=8)

        ctk.CTkLabel(barra, text="Data do requerimento:").pack(side="left", padx=4)
        self._entry_data = ctk.CTkEntry(barra, width=100, placeholder_text="DD/MM/YYYY")
        hoje = date.today().strftime("%d/%m/%Y")
        self._entry_data.insert(0, hoje)
        self._entry_data.pack(side="left", padx=4)

        ctk.CTkButton(barra, text="Calcular", command=self._calcular).pack(side="left", padx=8)
        self._lbl_status = ctk.CTkLabel(barra, text="")
        self._lbl_status.pack(side="left", padx=4)

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._lbl_vazio = ctk.CTkLabel(self._scroll, text="Clique em Calcular para ver os resultados.", text_color="gray")
        self._lbl_vazio.pack(pady=20)

    def carregar_caso(self, caso) -> None:
        self._caso = caso
        for w in self._scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._scroll, text="Clique em Calcular para ver os resultados.", text_color="gray").pack(pady=20)

    def _calcular(self) -> None:
        if not self._caso:
            return

        data_str = self._entry_data.get().strip()
        try:
            d, m, a = data_str.split("/")
            data_req = date(int(a), int(m), int(d))
        except ValueError:
            self._lbl_status.configure(text="Data inválida.", text_color="red")
            return

        self._lbl_status.configure(text="Calculando...", text_color="gray")

        def _trabalho() -> None:
            from ..engine.regras.salario_beneficio import calcular
            competencias = CompetenciaRepository.buscar_por_caso(self._caso.id)
            resultados = calcular(self._caso, competencias, data_req)
            self._app.after(0, lambda: self._exibir(resultados))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _exibir(self, resultados) -> None:
        self._lbl_status.configure(text=f"{sum(1 for r in resultados if r.elegivel)} regra(s) elegível(is)", text_color="gray")

        for w in self._scroll.winfo_children():
            w.destroy()

        for resultado in resultados:
            self._criar_card(resultado)

    def _criar_card(self, resultado) -> None:
        cor_borda = "#2ecc71" if resultado.elegivel else "#555555"
        cor_titulo = "#2ecc71" if resultado.elegivel else "#888888"
        icone = "✅" if resultado.elegivel else "❌"

        frame = ctk.CTkFrame(self._scroll, corner_radius=10, border_width=2, border_color=cor_borda)
        frame.pack(fill="x", padx=4, pady=6)

        # Cabeçalho
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(header, text=f"{icone}  {resultado.regra}",
                     font=ctk.CTkFont(size=13, weight="bold"), text_color=cor_titulo).pack(side="left")

        if not resultado.elegivel:
            ctk.CTkLabel(frame, text=resultado.motivo_inelegibilidade or "Inelegível",
                         text_color="#888888", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(0, 8))
            return

        # Detalhes do resultado
        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=4)

        tempo = resultado.tempo_contributivo
        if tempo:
            self._linha(grid, 0, "Tempo contributivo:", f"{tempo.anos}a {tempo.meses}m")

        self._linha(grid, 1, "Média das contribuições:", f"R$ {resultado.media_contribuicoes:,.2f}")

        if resultado.fator_previdenciario:
            self._linha(grid, 2, "Fator previdenciário:", str(resultado.fator_previdenciario))

        self._linha(grid, 3, "Coeficiente:", f"{float(resultado.coeficiente)*100:.0f}%")
        self._linha(grid, 4, "RMI (Renda Mensal Inicial):",
                    f"R$ {resultado.rmi:,.2f}", destaque=True)

        ctk.CTkButton(frame, text="Ver detalhamento", width=140,
                      command=lambda r=resultado: self._ver_detalhamento(r)).pack(anchor="e", padx=12, pady=(4, 10))

    @staticmethod
    def _linha(parent, row: int, label: str, valor: str, destaque: bool = False) -> None:
        ctk.CTkLabel(parent, text=label, anchor="w", width=220).grid(row=row, column=0, sticky="w", pady=2)
        ctk.CTkLabel(parent, text=valor, anchor="w",
                     font=ctk.CTkFont(weight="bold" if destaque else "normal"),
                     text_color="#2ecc71" if destaque else None).grid(row=row, column=1, sticky="w", padx=8, pady=2)

    def _ver_detalhamento(self, resultado) -> None:
        dlg = ctk.CTkToplevel(self._app)
        dlg.title(f"Detalhamento — {resultado.regra}")
        dlg.geometry("600x500")
        dlg.grab_set()

        scroll = ctk.CTkScrollableFrame(dlg)
        scroll.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(scroll, text=resultado.regra, font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 8))

        def _rec(d: dict, indent: int = 0) -> None:
            for k, v in d.items():
                if isinstance(v, dict):
                    ctk.CTkLabel(scroll, text=f"{'  '*indent}{k}:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
                    _rec(v, indent + 1)
                else:
                    ctk.CTkLabel(scroll, text=f"{'  '*indent}{k}: {v}", anchor="w").pack(anchor="w")

        _rec(resultado.detalhamento)
