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

        # Modo de cálculo: todas competências ou apenas validadas
        ctk.CTkLabel(barra, text="  Competências:").pack(side="left", padx=(12, 2))
        self._modo_var = ctk.StringVar(value="todas")
        ctk.CTkRadioButton(barra, text="Todas (CNIS completo)", variable=self._modo_var, value="todas").pack(side="left", padx=4)
        ctk.CTkRadioButton(barra, text="Somente validadas", variable=self._modo_var, value="validadas").pack(side="left", padx=4)

        ctk.CTkButton(barra, text="Calcular", command=self._calcular).pack(side="left", padx=8)
        ctk.CTkButton(barra, text="Comparar ambos", command=self._calcular_comparativo).pack(side="left", padx=4)
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

    def _parse_data(self) -> Optional[date]:
        data_str = self._entry_data.get().strip()
        try:
            d, m, a = data_str.split("/")
            return date(int(a), int(m), int(d))
        except ValueError:
            self._lbl_status.configure(text="Data inválida.", text_color="red")
            return None

    def _calcular(self) -> None:
        if not self._caso:
            return
        data_req = self._parse_data()
        if not data_req:
            return

        self._lbl_status.configure(text="Calculando...", text_color="gray")
        modo = self._modo_var.get()

        def _trabalho() -> None:
            from ..engine.regras.salario_beneficio import calcular
            todas = CompetenciaRepository.buscar_por_caso(self._caso.id)
            if modo == "validadas":
                competencias = [c for c in todas if not c.flag_pendencia_cnis]
            else:
                competencias = todas
            resultados = calcular(self._caso, competencias, data_req)
            label = "validadas" if modo == "validadas" else "todas"
            self._app.after(0, lambda: self._exibir(resultados, label=label))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _calcular_comparativo(self) -> None:
        if not self._caso:
            return
        data_req = self._parse_data()
        if not data_req:
            return

        self._lbl_status.configure(text="Calculando comparativo...", text_color="gray")

        def _trabalho() -> None:
            from ..engine.regras.salario_beneficio import calcular
            todas = CompetenciaRepository.buscar_por_caso(self._caso.id)
            validadas = [c for c in todas if not c.flag_pendencia_cnis]
            r_todas = calcular(self._caso, todas, data_req)
            r_valid = calcular(self._caso, validadas, data_req)
            self._app.after(0, lambda: self._exibir_comparativo(r_todas, r_valid, len(todas), len(validadas)))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _exibir(self, resultados, label: str = "") -> None:
        elegiveis = sum(1 for r in resultados if r.elegivel)
        sufixo = f" [{label}]" if label else ""
        self._lbl_status.configure(text=f"{elegiveis} regra(s) elegível(is){sufixo}", text_color="gray")

        for w in self._scroll.winfo_children():
            w.destroy()

        for resultado in resultados:
            self._criar_card(resultado)

    def _exibir_comparativo(self, r_todas, r_valid, n_todas: int, n_valid: int) -> None:
        self._lbl_status.configure(text="Comparativo gerado", text_color="gray")

        for w in self._scroll.winfo_children():
            w.destroy()

        # Cabeçalho comparativo
        hdr = ctk.CTkFrame(self._scroll, fg_color="#1a1a2e", corner_radius=8)
        hdr.pack(fill="x", padx=4, pady=(4, 8))
        ctk.CTkLabel(hdr, text="COMPARATIVO: CNIS completo vs Somente validadas",
                     font=ctk.CTkFont(size=13, weight="bold"), text_color="#f0a500").pack(padx=12, pady=6)

        pendentes = n_todas - n_valid
        info = ctk.CTkFrame(self._scroll, fg_color="transparent")
        info.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(info, text=f"Total de competências: {n_todas}  |  Com pendência CNIS: {pendentes}  |  Validadas: {n_valid}",
                     text_color="#888888", font=ctk.CTkFont(size=11)).pack()

        # Lado a lado por regra
        r_valid_map = {r.regra: r for r in r_valid}
        for r_t in r_todas:
            r_v = r_valid_map.get(r_t.regra)
            self._criar_card_comparativo(r_t, r_v)

    def _criar_card_comparativo(self, r_todas, r_valid) -> None:
        cor_borda = "#f0a500"
        frame = ctk.CTkFrame(self._scroll, corner_radius=10, border_width=2, border_color=cor_borda)
        frame.pack(fill="x", padx=4, pady=6)

        ctk.CTkLabel(frame, text=r_todas.regra,
                     font=ctk.CTkFont(size=13, weight="bold"), text_color="#f0a500").pack(anchor="w", padx=12, pady=(10, 4))

        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=(0, 10))
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_columnconfigure(2, weight=1)

        def _cabecalho(col: int, texto: str, cor: str) -> None:
            ctk.CTkLabel(grid, text=texto, font=ctk.CTkFont(weight="bold"),
                         text_color=cor).grid(row=0, column=col, sticky="w", padx=8, pady=(0, 4))

        ctk.CTkLabel(grid, text="").grid(row=0, column=0, sticky="w", padx=8)
        _cabecalho(1, "CNIS completo", "#4a9eff")
        _cabecalho(2, "Somente validadas", "#2ecc71")

        def _linha_comp(row: int, label: str, v_todas, v_valid) -> None:
            ctk.CTkLabel(grid, text=label, anchor="w", width=220).grid(row=row, column=0, sticky="w", padx=8, pady=2)
            ctk.CTkLabel(grid, text=str(v_todas), text_color="#4a9eff", anchor="w").grid(row=row, column=1, sticky="w", padx=8, pady=2)
            v_str = str(v_valid) if v_valid is not None else "—"
            cor = "#ff6b6b" if v_valid is not None and v_todas != v_valid else "#2ecc71"
            ctk.CTkLabel(grid, text=v_str, text_color=cor, anchor="w").grid(row=row, column=2, sticky="w", padx=8, pady=2)

        elegivel_t = "✅ Elegível" if r_todas.elegivel else "❌ Inelegível"
        elegivel_v = ("✅ Elegível" if r_valid.elegivel else "❌ Inelegível") if r_valid else "—"
        _linha_comp(1, "Situação:", elegivel_t, elegivel_v)

        if r_todas.elegivel or (r_valid and r_valid.elegivel):
            tempo_t = f"{r_todas.tempo_contributivo.anos}a {r_todas.tempo_contributivo.meses}m" if r_todas.tempo_contributivo else "—"
            tempo_v = (f"{r_valid.tempo_contributivo.anos}a {r_valid.tempo_contributivo.meses}m" if r_valid and r_valid.tempo_contributivo else "—")
            _linha_comp(2, "Tempo contributivo:", tempo_t, tempo_v)

            media_t = f"R$ {r_todas.media_contribuicoes:,.2f}" if r_todas.media_contribuicoes else "—"
            media_v = (f"R$ {r_valid.media_contribuicoes:,.2f}" if r_valid and r_valid.media_contribuicoes else "—")
            _linha_comp(3, "Média das contribuições:", media_t, media_v)

            rmi_t = f"R$ {r_todas.rmi:,.2f}" if r_todas.rmi else "—"
            rmi_v = f"R$ {r_valid.rmi:,.2f}" if r_valid and r_valid.rmi else "—"
            _linha_comp(4, "RMI:", rmi_t, rmi_v)

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
