"""Painel de cálculo do salário de benefício."""
from __future__ import annotations

import logging
import threading
from datetime import date
from typing import TYPE_CHECKING, List, Optional

import customtkinter as ctk

from ..db import CompetenciaRepository
from .theme import (
    AZUL_CLARO, AZUL_PRIMARIO, VERDE_OK, VERDE_ESCURO, AMARELO, VERMELHO,
    CINZA_TEXTO, BG_CARD, BG_CARD2, BG_SEP,
    font_secao, font_label, font_valor, font_destaque, font_pequeno,
    secao_header, card, stat_box,
)

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
        # ── Barra de controles ───────────────────────────────────────────
        barra = ctk.CTkFrame(self, fg_color=BG_CARD2, corner_radius=8, border_width=1, border_color=BG_SEP)
        barra.pack(fill="x", padx=10, pady=(10, 6))

        ctk.CTkLabel(barra, text="Data do requerimento:", font=font_label()).pack(side="left", padx=(12, 4), pady=10)
        self._entry_data = ctk.CTkEntry(barra, width=110, placeholder_text="DD/MM/YYYY",
                                        height=32, corner_radius=6)
        self._entry_data.insert(0, date.today().strftime("%d/%m/%Y"))
        self._entry_data.pack(side="left", padx=4, pady=10)

        ctk.CTkFrame(barra, width=1, height=28, fg_color=BG_SEP).pack(side="left", padx=10, pady=10)

        ctk.CTkLabel(barra, text="Competências:", font=font_label()).pack(side="left", padx=(0, 4))
        self._modo_var = ctk.StringVar(value="todas")
        ctk.CTkRadioButton(barra, text="Todas as fontes",
                           variable=self._modo_var, value="todas",
                           font=font_label()).pack(side="left", padx=4)
        ctk.CTkRadioButton(barra, text="Sem pendências CNIS",
                           variable=self._modo_var, value="validadas",
                           font=font_label()).pack(side="left", padx=(4, 12))

        ctk.CTkFrame(barra, width=1, height=28, fg_color=BG_SEP).pack(side="left", padx=6, pady=10)

        ctk.CTkButton(barra, text="🧮  Calcular", width=120, height=32, corner_radius=6,
                      font=font_valor(), command=self._calcular).pack(side="left", padx=4, pady=10)
        ctk.CTkButton(barra, text="⚖  Comparar ambos", width=150, height=32, corner_radius=6,
                      fg_color=(AZUL_PRIMARIO, "#1a3a6b"), hover_color=(AZUL_CLARO, AZUL_CLARO),
                      font=font_valor(), command=self._calcular_comparativo).pack(side="left", padx=4, pady=10)

        self._lbl_status = ctk.CTkLabel(barra, text="", font=font_pequeno(), text_color=CINZA_TEXTO)
        self._lbl_status.pack(side="left", padx=8)

        # ── Área de resultados ───────────────────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._mostrar_placeholder("Selecione um caso e clique em  🧮  Calcular.")

    def _mostrar_placeholder(self, msg: str) -> None:
        for w in self._scroll.winfo_children():
            w.destroy()
        f = ctk.CTkFrame(self._scroll, fg_color="transparent")
        f.pack(expand=True, fill="both", pady=40)
        ctk.CTkLabel(f, text="🧮", font=ctk.CTkFont(size=40)).pack()
        ctk.CTkLabel(f, text=msg, text_color=CINZA_TEXTO, font=font_label()).pack(pady=6)

    def carregar_caso(self, caso) -> None:
        self._caso = caso
        self._mostrar_placeholder("Clique em  🧮  Calcular  para ver os resultados.")

    # ── Cálculo ──────────────────────────────────────────────────────────

    def _parse_data(self) -> Optional[date]:
        try:
            d, m, a = self._entry_data.get().strip().split("/")
            return date(int(a), int(m), int(d))
        except ValueError:
            self._lbl_status.configure(text="Data inválida.", text_color=VERMELHO)
            return None

    def _calcular(self) -> None:
        if not self._caso:
            return
        data_req = self._parse_data()
        if not data_req:
            return
        self._lbl_status.configure(text="⏳  Calculando...", text_color=CINZA_TEXTO)
        modo = self._modo_var.get()

        def _trabalho() -> None:
            from ..engine.regras.salario_beneficio import calcular
            todas = CompetenciaRepository.buscar_por_caso(self._caso.id)
            competencias = [c for c in todas if not c.flag_pendencia_cnis] if modo == "validadas" else todas
            resultados = calcular(self._caso, competencias, data_req)
            label = "sem pendências CNIS" if modo == "validadas" else "todas as fontes"
            self._app.after(0, lambda: self._exibir(resultados, label=label))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _calcular_comparativo(self) -> None:
        if not self._caso:
            return
        data_req = self._parse_data()
        if not data_req:
            return
        self._lbl_status.configure(text="⏳  Calculando comparativo...", text_color=CINZA_TEXTO)

        def _trabalho() -> None:
            from ..engine.regras.salario_beneficio import calcular
            todas = CompetenciaRepository.buscar_por_caso(self._caso.id)
            validadas = [c for c in todas if not c.flag_pendencia_cnis]
            r_todas = calcular(self._caso, todas, data_req)
            r_valid = calcular(self._caso, validadas, data_req)
            self._app.after(0, lambda: self._exibir_comparativo(r_todas, r_valid, len(todas), len(validadas)))

        threading.Thread(target=_trabalho, daemon=True).start()

    # ── Exibição ─────────────────────────────────────────────────────────

    def _exibir(self, resultados, label: str = "") -> None:
        elegiveis = [r for r in resultados if r.elegivel]
        sufixo = f"  [{label}]" if label else ""
        self._lbl_status.configure(
            text=f"✅  {len(elegiveis)} regra(s) elegível(is){sufixo}",
            text_color=VERDE_OK if elegiveis else CINZA_TEXTO,
        )

        for w in self._scroll.winfo_children():
            w.destroy()

        # Painel de destaque: melhor RMI
        if elegiveis:
            melhor = elegiveis[0]
            self._criar_banner_melhor(melhor)

        for resultado in resultados:
            self._criar_card(resultado)

    def _criar_banner_melhor(self, resultado) -> None:
        banner = ctk.CTkFrame(
            self._scroll, corner_radius=12,
            fg_color=(AZUL_PRIMARIO, "#0d2040"),
            border_width=2, border_color=VERDE_OK,
        )
        banner.pack(fill="x", padx=4, pady=(4, 12))

        top = ctk.CTkFrame(banner, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(top, text="🏆  Melhor resultado", font=font_secao(),
                     text_color=VERDE_OK).pack(side="left")
        ctk.CTkLabel(top, text=resultado.regra, font=font_pequeno(),
                     text_color="#aaccee").pack(side="right")

        stats = ctk.CTkFrame(banner, fg_color="transparent")
        stats.pack(fill="x", padx=16, pady=(4, 12))

        def _stat(texto: str, valor: str, cor: str = AZUL_CLARO) -> None:
            box = ctk.CTkFrame(stats, corner_radius=8, fg_color="#1e2d45")
            box.pack(side="left", padx=6, pady=4, ipadx=10, ipady=6)
            ctk.CTkLabel(box, text=texto, font=font_pequeno(), text_color="#aaccee").pack()
            ctk.CTkLabel(box, text=valor, font=font_destaque(), text_color=cor).pack()

        tc = resultado.tempo_contributivo
        if tc:
            _stat("Tempo contributivo", f"{tc.anos}a {tc.meses}m")
        _stat("Média das contribuições", f"R$ {resultado.media_contribuicoes:,.2f}")
        if resultado.fator_previdenciario:
            _stat("Fator previdenciário", str(resultado.fator_previdenciario), AMARELO)
        _stat("RMI", f"R$ {resultado.rmi:,.2f}", VERDE_OK)

    def _exibir_comparativo(self, r_todas, r_valid, n_todas: int, n_valid: int) -> None:
        self._lbl_status.configure(text="⚖  Comparativo gerado", text_color=CINZA_TEXTO)

        for w in self._scroll.winfo_children():
            w.destroy()

        hdr = ctk.CTkFrame(self._scroll, corner_radius=10,
                           fg_color=(AZUL_PRIMARIO, "#0d2040"),
                           border_width=2, border_color=AMARELO)
        hdr.pack(fill="x", padx=4, pady=(4, 4))
        ctk.CTkLabel(hdr, text="⚖  COMPARATIVO: Todas as fontes  vs  Sem pendências CNIS",
                     font=font_secao(), text_color=AMARELO).pack(padx=16, pady=(10, 4))

        pendentes = n_todas - n_valid
        info = ctk.CTkFrame(hdr, fg_color="transparent")
        info.pack(padx=16, pady=(0, 10))
        for txt, val, cor in [
            ("Total", str(n_todas), AZUL_CLARO),
            ("Com pendência", str(pendentes), AMARELO),
            ("Sem pendência", str(n_valid), VERDE_OK),
        ]:
            b = ctk.CTkFrame(info, corner_radius=6, fg_color="#1e2d45")
            b.pack(side="left", padx=6, ipadx=8, ipady=4)
            ctk.CTkLabel(b, text=txt, font=font_pequeno(), text_color="#aaccee").pack()
            ctk.CTkLabel(b, text=val, font=font_valor(), text_color=cor).pack()

        r_valid_map = {r.regra: r for r in r_valid}
        for r_t in r_todas:
            r_v = r_valid_map.get(r_t.regra)
            self._criar_card_comparativo(r_t, r_v)

    def _criar_card_comparativo(self, r_todas, r_valid) -> None:
        frame = card(self._scroll, border_color=AMARELO, border_width=2)
        frame.pack(fill="x", padx=4, pady=6)

        ctk.CTkLabel(frame, text=r_todas.regra,
                     font=font_secao(), text_color=AMARELO).pack(anchor="w", padx=14, pady=(12, 4))

        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 12))
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_columnconfigure(2, weight=1)

        # Cabeçalhos das colunas
        ctk.CTkLabel(grid, text="").grid(row=0, column=0, sticky="w", padx=6)
        ctk.CTkLabel(grid, text="Todas as fontes", font=font_valor(),
                     text_color=AZUL_CLARO).grid(row=0, column=1, sticky="w", padx=6, pady=(0, 4))
        ctk.CTkLabel(grid, text="Sem pendências CNIS", font=font_valor(),
                     text_color=VERDE_OK).grid(row=0, column=2, sticky="w", padx=6, pady=(0, 4))

        def _linha(row: int, lbl: str, v_t, v_v, cor_v: str = None) -> None:
            ctk.CTkLabel(grid, text=lbl, anchor="w", width=220,
                         font=font_label(), text_color=CINZA_TEXTO).grid(row=row, column=0, sticky="w", padx=6, pady=2)
            ctk.CTkLabel(grid, text=str(v_t), anchor="w",
                         font=font_valor(), text_color=AZUL_CLARO).grid(row=row, column=1, sticky="w", padx=6, pady=2)
            v_str = str(v_v) if v_v is not None else "—"
            dif_cor = cor_v or (VERDE_OK if v_v == v_t else AMARELO)
            ctk.CTkLabel(grid, text=v_str, anchor="w",
                         font=font_valor(), text_color=dif_cor).grid(row=row, column=2, sticky="w", padx=6, pady=2)

        _linha(1, "Situação:",
               "✅ Elegível" if r_todas.elegivel else "❌ Inelegível",
               ("✅ Elegível" if r_valid.elegivel else "❌ Inelegível") if r_valid else None)

        if r_todas.elegivel or (r_valid and r_valid.elegivel):
            tc_t = f"{r_todas.tempo_contributivo.anos}a {r_todas.tempo_contributivo.meses}m" if r_todas.tempo_contributivo else "—"
            tc_v = f"{r_valid.tempo_contributivo.anos}a {r_valid.tempo_contributivo.meses}m" if r_valid and r_valid.tempo_contributivo else "—"
            _linha(2, "Tempo contributivo:", tc_t, tc_v)

            media_t = f"R$ {r_todas.media_contribuicoes:,.2f}" if r_todas.media_contribuicoes else "—"
            media_v = f"R$ {r_valid.media_contribuicoes:,.2f}" if r_valid and r_valid.media_contribuicoes else "—"
            _linha(3, "Média das contribuições:", media_t, media_v)

            rmi_t = f"R$ {r_todas.rmi:,.2f}" if r_todas.rmi else "—"
            rmi_v = f"R$ {r_valid.rmi:,.2f}" if r_valid and r_valid.rmi else "—"
            _linha(4, "RMI:", rmi_t, rmi_v, VERDE_OK)

    def _criar_card(self, resultado) -> None:
        elegivel = resultado.elegivel
        cor_borda = VERDE_OK if elegivel else ("#cccccc", "#444444")
        cor_titulo = VERDE_OK if elegivel else CINZA_TEXTO
        icone = "✅" if elegivel else "❌"

        frame = card(self._scroll, border_color=cor_borda, border_width=2 if elegivel else 1)
        frame.pack(fill="x", padx=4, pady=5)

        # Cabeçalho do card
        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(hdr, text=f"{icone}  {resultado.regra}",
                     font=font_secao(), text_color=cor_titulo).pack(side="left")

        if not elegivel:
            ctk.CTkLabel(frame,
                         text=resultado.motivo_inelegibilidade or "Inelegível",
                         text_color=CINZA_TEXTO, font=font_label(),
                         wraplength=700, anchor="w").pack(anchor="w", padx=14, pady=(0, 12))
            return

        # Stats em linha
        stats_row = ctk.CTkFrame(frame, fg_color="transparent")
        stats_row.pack(fill="x", padx=14, pady=(0, 4))

        def _stat(titulo: str, valor: str, cor: str = AZUL_CLARO) -> None:
            b = ctk.CTkFrame(stats_row, corner_radius=8, fg_color=BG_CARD2,
                             border_width=1, border_color=BG_SEP)
            b.pack(side="left", padx=(0, 10), pady=4, ipadx=10, ipady=6)
            ctk.CTkLabel(b, text=titulo, font=font_pequeno(), text_color=CINZA_TEXTO).pack()
            ctk.CTkLabel(b, text=valor, font=font_valor(), text_color=cor).pack()

        tc = resultado.tempo_contributivo
        if tc:
            _stat("Tempo contributivo", f"{tc.anos}a {tc.meses}m")
        _stat("Média das contribuições", f"R$ {resultado.media_contribuicoes:,.2f}")
        if resultado.fator_previdenciario:
            _stat("Fator previdenciário", str(resultado.fator_previdenciario), AMARELO)
        _stat("Coeficiente", f"{float(resultado.coeficiente)*100:.0f}%")

        # RMI destacado
        rmi_box = ctk.CTkFrame(frame, corner_radius=8,
                               fg_color=(VERDE_ESCURO, "#0a3020"),
                               border_width=1, border_color=VERDE_OK)
        rmi_box.pack(fill="x", padx=14, pady=(4, 4))
        rmi_inner = ctk.CTkFrame(rmi_box, fg_color="transparent")
        rmi_inner.pack(padx=14, pady=8)
        ctk.CTkLabel(rmi_inner, text="Renda Mensal Inicial  —  RMI",
                     font=font_label(), text_color="#aaffcc").pack(side="left", padx=(0, 20))
        ctk.CTkLabel(rmi_inner,
                     text=f"R$ {resultado.rmi:,.2f}",
                     font=font_destaque(), text_color=VERDE_OK).pack(side="left")

        ctk.CTkButton(frame, text="Ver detalhamento ›", width=150, height=28,
                      corner_radius=6,
                      fg_color="transparent", border_width=1, border_color=BG_SEP,
                      text_color=AZUL_CLARO, hover_color=BG_CARD2,
                      font=font_pequeno(),
                      command=lambda r=resultado: self._ver_detalhamento(r)).pack(anchor="e", padx=14, pady=(4, 12))

    def _ver_detalhamento(self, resultado) -> None:
        dlg = ctk.CTkToplevel(self._app)
        dlg.title(f"Detalhamento — {resultado.regra}")
        dlg.geometry("660x520")
        dlg.grab_set()

        hdr = ctk.CTkFrame(dlg, corner_radius=0, fg_color=(AZUL_PRIMARIO, "#0d2040"))
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=resultado.regra,
                     font=font_secao(), text_color="#ffffff").pack(anchor="w", padx=16, pady=10)

        scroll = ctk.CTkScrollableFrame(dlg)
        scroll.pack(fill="both", expand=True, padx=14, pady=14)

        def _rec(d: dict, indent: int = 0) -> None:
            for k, v in d.items():
                if isinstance(v, dict):
                    ctk.CTkLabel(scroll,
                                 text=f"{'  '*indent}{k}",
                                 font=font_valor(), text_color=AZUL_CLARO,
                                 anchor="w").pack(anchor="w", pady=(6, 0))
                    _rec(v, indent + 1)
                else:
                    row = ctk.CTkFrame(scroll, fg_color="transparent")
                    row.pack(fill="x", pady=1)
                    ctk.CTkLabel(row, text=f"{'  '*indent}{k}:", width=250,
                                 font=font_label(), text_color=CINZA_TEXTO,
                                 anchor="w").pack(side="left")
                    ctk.CTkLabel(row, text=str(v),
                                 font=font_valor(), anchor="w").pack(side="left", padx=8)

        _rec(resultado.detalhamento)
