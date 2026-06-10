"""Aba de resumo de contribuições por mês — teto, cortes e correção INPC."""
from __future__ import annotations

import logging
import threading
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

import customtkinter as ctk

from ..db import CompetenciaRepository

if TYPE_CHECKING:
    from .app import App

logger = logging.getLogger(__name__)


class ResumoMensalPanel(ctk.CTkFrame):

    def __init__(self, parent, app: "App", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._app = app
        self._caso = None
        self._build()

    def _build(self) -> None:
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=8, pady=8)

        ctk.CTkLabel(barra, text="Data de referência:").pack(side="left", padx=4)
        self._entry_data = ctk.CTkEntry(barra, width=100, placeholder_text="DD/MM/YYYY")
        self._entry_data.insert(0, date.today().strftime("%d/%m/%Y"))
        self._entry_data.pack(side="left", padx=4)

        ctk.CTkButton(barra, text="Gerar resumo", command=self._gerar).pack(side="left", padx=8)
        self._lbl_status = ctk.CTkLabel(barra, text="")
        self._lbl_status.pack(side="left", padx=4)

        # Legenda
        leg = ctk.CTkFrame(self, fg_color="transparent")
        leg.pack(fill="x", padx=12, pady=(0, 4))
        ctk.CTkLabel(leg, text="■", text_color="#f0a500", width=14).pack(side="left")
        ctk.CTkLabel(leg, text=" Mês com corte de teto  ",
                     text_color="#888888", font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkLabel(leg, text="  Base corrigida INPC",
                     text_color="#4a9eff", font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkLabel(leg, text="  |  Teto corrigido INPC = teto da época trazido a valor presente",
                     text_color="#666666", font=ctk.CTkFont(size=10)).pack(side="left")

        # Cabeçalho fixo da tabela
        HDR_BG = "#2a2a3e"
        HDR_FG = "#aaaaaa"
        self._COLS = [
            ("Competência",           90),
            ("Fontes / Reg.",         150),
            ("Base somada\n(nominal)", 115),
            ("Teto da época",          115),
            ("Corte\n(excesso)",       105),
            ("Base efetiva\n(nominal)",120),
            ("Base corrigida\nINPC",   125),
            ("Teto corrigido\nINPC",   125),
        ]

        hdr = ctk.CTkFrame(self, fg_color=HDR_BG, corner_radius=0, height=44)
        hdr.pack(fill="x", padx=0)
        hdr.pack_propagate(False)
        for titulo, largura in self._COLS:
            ctk.CTkLabel(hdr, text=titulo, text_color=HDR_FG,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         width=largura, anchor="center", justify="center").pack(side="left", padx=1)

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=0, pady=0)

        self._lbl_vazio = ctk.CTkLabel(
            self._scroll,
            text="Selecione um caso e clique em 'Gerar resumo'.",
            text_color="gray",
        )
        self._lbl_vazio.pack(pady=20)

    def carregar_caso(self, caso) -> None:
        self._caso = caso
        self._limpar_tabela()
        self._lbl_status.configure(text="")
        if caso:
            self._lbl_vazio = ctk.CTkLabel(
                self._scroll,
                text="Clique em 'Gerar resumo' para calcular.",
                text_color="gray",
            )
            self._lbl_vazio.pack(pady=20)

    def _limpar_tabela(self) -> None:
        for w in self._scroll.winfo_children():
            w.destroy()

    def _parse_data(self) -> Optional[date]:
        try:
            d, m, a = self._entry_data.get().strip().split("/")
            return date(int(a), int(m), int(d))
        except ValueError:
            self._lbl_status.configure(text="Data inválida.", text_color="red")
            return None

    def _gerar(self) -> None:
        if not self._caso:
            self._lbl_status.configure(text="Nenhum caso selecionado.", text_color="red")
            return
        data_req = self._parse_data()
        if not data_req:
            return

        self._lbl_status.configure(text="Calculando...", text_color="gray")
        self._limpar_tabela()

        def _trabalho() -> None:
            from ..engine.regras.media_contribuicoes import teto_para_competencia
            from ..engine.correcao_monetaria import atualizar_inpc

            def _comp_key(comp: str) -> int:
                try:
                    m, a = comp.split("/")
                    return int(a) * 100 + int(m)
                except (ValueError, AttributeError):
                    return 0

            data_ref = data_req.strftime("%m/%Y")
            todas = CompetenciaRepository.buscar_por_caso(self._caso.id)

            por_comp: dict = {}
            for c in todas:
                por_comp.setdefault(c.competencia, []).append(c)

            linhas = []
            for comp, lista in sorted(por_comp.items(), key=lambda x: _comp_key(x[0])):
                soma_base = sum((c.base_contribuicao for c in lista), Decimal("0"))
                fontes = sorted({c.fonte.value for c in lista})
                n_reg = len(lista)

                teto_epoca = teto_para_competencia(comp)
                base_efetiva = min(soma_base, teto_epoca)
                foi_cortado = base_efetiva < soma_base - Decimal("0.01")
                valor_cortado = soma_base - base_efetiva if foi_cortado else Decimal("0")

                try:
                    base_corrigida = atualizar_inpc(base_efetiva, comp, data_ref)
                    teto_corrigido = atualizar_inpc(teto_epoca, comp, data_ref)
                except Exception:
                    base_corrigida = base_efetiva
                    teto_corrigido = teto_epoca

                linhas.append({
                    "comp": comp,
                    "fontes": fontes,
                    "n_reg": n_reg,
                    "soma_base": soma_base,
                    "teto_epoca": teto_epoca,
                    "base_efetiva": base_efetiva,
                    "foi_cortado": foi_cortado,
                    "valor_cortado": valor_cortado,
                    "base_corrigida": base_corrigida,
                    "teto_corrigido": teto_corrigido,
                })

            n_cortados = sum(1 for l in linhas if l["foi_cortado"])
            self._app.after(0, lambda: self._renderizar(linhas, n_cortados))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _renderizar(self, linhas: list, n_cortados: int) -> None:
        self._limpar_tabela()

        total = len(linhas)
        msg = f"{total} meses"
        if n_cortados:
            msg += f"  |  {n_cortados} com corte de teto"
        self._lbl_status.configure(
            text=msg,
            text_color="#f0a500" if n_cortados else "gray",
        )

        def _fmt(v) -> str:
            try:
                return f"R$ {float(v):,.2f}"
            except Exception:
                return "—"

        COR_NORMAL   = "#cccccc"
        COR_INFO     = "#888888"
        COR_CORTE    = "#f0a500"
        COR_EXCESSO  = "#ff6b6b"
        COR_INPC     = "#4a9eff"

        for i, linha in enumerate(linhas):
            bg = "#2a2a2a" if i % 2 == 0 else "#222222"
            if linha["foi_cortado"]:
                bg = "#3a2800"

            row = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=0, height=34)
            row.pack(fill="x", padx=0, pady=0)
            row.pack_propagate(False)

            cor_linha = COR_CORTE if linha["foi_cortado"] else COR_NORMAL

            def _cel(texto, largura, cor=COR_NORMAL, bold=False):
                ctk.CTkLabel(
                    row, text=texto, text_color=cor,
                    font=ctk.CTkFont(size=11, weight="bold" if bold else "normal"),
                    width=largura, anchor="center",
                ).pack(side="left", padx=1)

            fontes_str = ", ".join(linha["fontes"])
            if linha["n_reg"] > 1:
                fontes_str += f"  ({linha['n_reg']})"

            _cel(linha["comp"],                self._COLS[0][1], cor_linha, bold=linha["foi_cortado"])
            _cel(fontes_str,                   self._COLS[1][1], COR_INFO)
            _cel(_fmt(linha["soma_base"]),      self._COLS[2][1], cor_linha)
            _cel(_fmt(linha["teto_epoca"]),     self._COLS[3][1], COR_INFO)

            if linha["foi_cortado"]:
                _cel(f"- {_fmt(linha['valor_cortado'])}", self._COLS[4][1], COR_EXCESSO, bold=True)
            else:
                _cel("—",                      self._COLS[4][1], "#444444")

            _cel(_fmt(linha["base_efetiva"]),   self._COLS[5][1], cor_linha)
            _cel(_fmt(linha["base_corrigida"]), self._COLS[6][1], COR_INPC, bold=True)
            _cel(_fmt(linha["teto_corrigido"]), self._COLS[7][1], COR_INFO)
