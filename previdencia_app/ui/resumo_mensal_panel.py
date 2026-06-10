"""Aba de resumo de contribuições por mês — teto, cortes e correção INPC."""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from datetime import date
from decimal import Decimal
from tkinter import ttk
from typing import TYPE_CHECKING, Dict, List, Optional

import customtkinter as ctk

from ..db import CompetenciaRepository
from ..models import Competencia

if TYPE_CHECKING:
    from .app import App

logger = logging.getLogger(__name__)

_COLS = [
    ("comp",           "Competência",          90,  "center"),
    ("fontes",         "Fontes / Registros",   180,  "w"),
    ("soma_base",      "Base somada",          110,  "e"),
    ("teto_epoca",     "Teto da época",        110,  "e"),
    ("corte",          "Corte (excesso)",      110,  "e"),
    ("base_efetiva",   "Base efetiva",         110,  "e"),
    ("base_corrigida", "Base corrigida INPC",  130,  "e"),
    ("teto_corrigido", "Teto corrigido INPC",  130,  "e"),
]


def _fmt(v) -> str:
    try:
        return f"R$ {float(v):,.2f}"
    except Exception:
        return "—"


def _comp_key(comp: str) -> int:
    try:
        m, a = comp.split("/")
        return int(a) * 100 + int(m)
    except (ValueError, AttributeError):
        return 0


class ResumoMensalPanel(ctk.CTkFrame):

    def __init__(self, parent, app: "App", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._app = app
        self._caso = None
        # Dados brutos por competência para o popup de detalhe
        self._por_comp: Dict[str, List[Competencia]] = {}
        self._build()

    # ── Layout ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(barra, text="Data de referência:").pack(side="left", padx=4)
        self._entry_data = ctk.CTkEntry(barra, width=110, placeholder_text="DD/MM/YYYY")
        self._entry_data.insert(0, date.today().strftime("%d/%m/%Y"))
        self._entry_data.pack(side="left", padx=4)

        ctk.CTkButton(barra, text="Gerar resumo", width=120,
                      command=self._gerar).pack(side="left", padx=8)

        self._lbl_status = ctk.CTkLabel(
            barra, text="Selecione um caso e clique em Gerar resumo.",
            text_color="gray", anchor="w",
        )
        self._lbl_status.pack(side="left", padx=4, fill="x", expand=True)

        # Legenda
        leg = ctk.CTkFrame(self, fg_color="transparent")
        leg.pack(fill="x", padx=12, pady=(0, 2))
        ctk.CTkLabel(leg, text="■  Mês com corte de teto",
                     text_color="#c87000", font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkLabel(leg, text="     Base corrigida INPC = base efetiva trazida a valor presente",
                     text_color="#666666", font=ctk.CTkFont(size=10)).pack(side="left", padx=8)
        ctk.CTkLabel(leg, text="  |  Clique em uma linha para ver empregadores e contribuições do mês",
                     text_color="#4a9eff", font=ctk.CTkFont(size=10)).pack(side="left")

        table_frame = tk.Frame(self, bg="#1e1e1e")
        table_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._tree = self._build_tree(table_frame)

    def _build_tree(self, parent: tk.Frame) -> ttk.Treeview:
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Resumo.Treeview",
                        background="#1e1e1e", foreground="#cccccc",
                        fieldbackground="#1e1e1e", rowheight=26,
                        font=("Segoe UI", 10))
        style.configure("Resumo.Treeview.Heading",
                        background="#2a2a3e", foreground="#aaaaaa",
                        font=("Segoe UI", 10, "bold"), relief="flat")
        style.map("Resumo.Treeview",
                  background=[("selected", "#2a4a7a")],
                  foreground=[("selected", "#ffffff")])
        style.map("Resumo.Treeview.Heading",
                  background=[("active", "#3a3a5e")])

        cols = [c[0] for c in _COLS]
        tree = ttk.Treeview(parent, columns=cols, show="headings",
                            style="Resumo.Treeview", selectmode="browse")

        for key, titulo, largura, ancora in _COLS:
            tree.heading(key, text=titulo, anchor="center")
            tree.column(key, width=largura, minwidth=60, anchor=ancora, stretch=False)

        tree.tag_configure("normal",      background="#222222", foreground="#cccccc")
        tree.tag_configure("normal_alt",  background="#2a2a2a", foreground="#cccccc")
        tree.tag_configure("cortado",     background="#3a2800", foreground="#f0a500")
        tree.tag_configure("cortado_alt", background="#332400", foreground="#f0a500")

        vsb = ttk.Scrollbar(parent, orient="vertical",   command=tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        style.configure("Vertical.TScrollbar",
                        background="#333333", troughcolor="#1e1e1e", arrowcolor="#888888")
        style.configure("Horizontal.TScrollbar",
                        background="#333333", troughcolor="#1e1e1e", arrowcolor="#888888")

        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right",  fill="y")
        tree.pack(side="left",  fill="both", expand=True)

        # Clique simples abre popup de detalhe
        tree.bind("<ButtonRelease-1>", self._on_linha_clicada)

        return tree

    # ── Dados ────────────────────────────────────────────────────────────────

    def carregar_caso(self, caso) -> None:
        self._caso = caso
        self._por_comp.clear()
        self._tree.delete(*self._tree.get_children())
        self._lbl_status.configure(
            text="Clique em 'Gerar resumo' para calcular." if caso
            else "Selecione um caso e clique em Gerar resumo.",
            text_color="gray",
        )

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
        self._tree.delete(*self._tree.get_children())
        self._por_comp.clear()

        def _trabalho() -> None:
            from ..engine.regras.media_contribuicoes import teto_para_competencia
            from ..engine.correcao_monetaria import atualizar_inpc

            data_ref = data_req.strftime("%m/%Y")
            todas = CompetenciaRepository.buscar_por_caso(self._caso.id)

            por_comp: Dict[str, List[Competencia]] = {}
            for c in todas:
                por_comp.setdefault(c.competencia, []).append(c)

            linhas = []
            for comp, lista in sorted(por_comp.items(), key=lambda x: _comp_key(x[0])):
                soma_base = sum((c.base_contribuicao for c in lista), Decimal("0"))
                fontes = sorted({c.fonte.value for c in lista})
                n_reg = len(lista)
                fontes_str = ", ".join(fontes)
                if n_reg > len(fontes):
                    fontes_str += f"  ({n_reg} registros)"

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

                linhas.append((
                    comp,
                    fontes_str,
                    _fmt(soma_base),
                    _fmt(teto_epoca),
                    f"- {_fmt(valor_cortado)}" if foi_cortado else "—",
                    _fmt(base_efetiva),
                    _fmt(base_corrigida),
                    _fmt(teto_corrigido),
                    foi_cortado,
                ))

            n_cortados = sum(1 for l in linhas if l[8])
            self._app.after(0, lambda: self._renderizar(linhas, por_comp, n_cortados))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _renderizar(self, linhas: list, por_comp: dict, n_cortados: int) -> None:
        self._tree.delete(*self._tree.get_children())
        self._por_comp = por_comp

        total = len(linhas)
        msg = f"{total} meses  —  clique em uma linha para detalhar"
        if n_cortados:
            msg += f"  |  ⚠  {n_cortados} com corte de teto"
        self._lbl_status.configure(
            text=msg,
            text_color="#f0a500" if n_cortados else "gray",
        )

        for i, linha in enumerate(linhas):
            *valores, foi_cortado = linha
            tag = ("cortado" if foi_cortado else "normal") if i % 2 == 0 \
                  else ("cortado_alt" if foi_cortado else "normal_alt")
            self._tree.insert("", "end", values=valores, tags=(tag,))

    # ── Popup de detalhe ─────────────────────────────────────────────────────

    def _on_linha_clicada(self, event) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        valores = self._tree.item(sel[0], "values")
        if not valores:
            return
        comp = valores[0]
        registros = self._por_comp.get(comp)
        if not registros:
            return
        self._abrir_popup_detalhe(comp, registros)

    def _abrir_popup_detalhe(self, comp: str, registros: List[Competencia]) -> None:
        popup = tk.Toplevel(self._app)
        popup.title(f"Detalhes — {comp}")
        popup.geometry("780x400")
        popup.configure(bg="#1e1e1e")
        popup.grab_set()

        # Cabeçalho
        hdr = tk.Frame(popup, bg="#2a2a3e")
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"Contribuições de  {comp}",
                 bg="#2a2a3e", fg="#f0a500",
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=14, pady=8)
        tk.Label(hdr, text=f"{len(registros)} registro(s)",
                 bg="#2a2a3e", fg="#888888",
                 font=("Segoe UI", 10)).pack(side="left", padx=4)

        # Tabela de registros
        DCOLS = [
            ("empregador",    "Empregador",          220, "w"),
            ("cnpj",          "CNPJ / CPF",          130, "center"),
            ("tipo",          "Vínculo",              90, "center"),
            ("fonte",         "Fonte",                70, "center"),
            ("remuneracao",   "Remuneração bruta",   120, "e"),
            ("base",          "Base contribuição",   120, "e"),
            ("inss",          "INSS recolhido",       110, "e"),
        ]

        style = ttk.Style()
        style.configure("Detalhe.Treeview",
                        background="#1e1e1e", foreground="#cccccc",
                        fieldbackground="#1e1e1e", rowheight=24,
                        font=("Segoe UI", 10))
        style.configure("Detalhe.Treeview.Heading",
                        background="#2a2a3e", foreground="#aaaaaa",
                        font=("Segoe UI", 10, "bold"), relief="flat")
        style.map("Detalhe.Treeview",
                  background=[("selected", "#2a4a7a")],
                  foreground=[("selected", "#ffffff")])

        frame_tree = tk.Frame(popup, bg="#1e1e1e")
        frame_tree.pack(fill="both", expand=True, padx=8, pady=8)

        tree = ttk.Treeview(frame_tree,
                            columns=[c[0] for c in DCOLS],
                            show="headings",
                            style="Detalhe.Treeview",
                            selectmode="none")

        for key, titulo, largura, ancora in DCOLS:
            tree.heading(key, text=titulo, anchor="center")
            tree.column(key, width=largura, minwidth=50, anchor=ancora, stretch=False)

        tree.tag_configure("par",   background="#222222", foreground="#cccccc")
        tree.tag_configure("impar", background="#2a2a2a", foreground="#cccccc")

        soma_base = Decimal("0")
        soma_inss = Decimal("0")

        for i, c in enumerate(registros):
            empregador = c.empregador_nome or "Não identificado"
            cnpj       = c.empregador_cnpj_cpf or "—"
            tipo       = c.tipo_vinculo.value if c.tipo_vinculo else "—"
            fonte      = c.fonte.value if c.fonte else "—"
            rem        = _fmt(c.remuneracao_bruta)
            base       = _fmt(c.base_contribuicao)
            inss       = _fmt(c.valor_contribuicao) if c.valor_contribuicao else "—"

            soma_base += c.base_contribuicao or Decimal("0")
            if c.valor_contribuicao:
                soma_inss += c.valor_contribuicao

            tag = "par" if i % 2 == 0 else "impar"
            tree.insert("", "end",
                        values=(empregador, cnpj, tipo, fonte, rem, base, inss),
                        tags=(tag,))

        vsb = ttk.Scrollbar(frame_tree, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        # Rodapé com totais
        rodape = tk.Frame(popup, bg="#2a2a3e")
        rodape.pack(fill="x", padx=8, pady=(0, 8))

        from ..engine.regras.media_contribuicoes import teto_para_competencia
        teto = teto_para_competencia(comp)
        base_efetiva = min(soma_base, teto)
        foi_cortado = base_efetiva < soma_base - Decimal("0.01")

        cor_total = "#f0a500" if foi_cortado else "#2ecc71"
        resumo = (
            f"Total base:  {_fmt(soma_base)}   "
            f"Teto da época:  {_fmt(teto)}   "
            f"Base efetiva:  {_fmt(base_efetiva)}"
        )
        if soma_inss > 0:
            resumo += f"   INSS total recolhido:  {_fmt(soma_inss)}"
        if foi_cortado:
            resumo += f"   ⚠ corte de {_fmt(soma_base - base_efetiva)}"

        tk.Label(rodape, text=resumo,
                 bg="#2a2a3e", fg=cor_total,
                 font=("Segoe UI", 10, "bold")).pack(padx=12, pady=6)
