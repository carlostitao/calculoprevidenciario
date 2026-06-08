"""Tabela editável de competências — coração da UI."""
from __future__ import annotations

import logging
import threading
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, List, Optional

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

from ..db import CompetenciaRepository
from ..models import Competencia, FonteDocumento, TipoVinculo

if TYPE_CHECKING:
    from .app import App

logger = logging.getLogger(__name__)

_COLUNAS = [
    ("competencia", "Competência", 80),
    ("empregador_nome", "Empregador", 200),
    ("tipo_vinculo", "Tipo", 90),
    ("remuneracao_bruta", "Rem. Bruta", 100),
    ("base_contribuicao", "Base Contrib.", 100),
    ("remuneracao_atualizada", "Rem. Atualizada", 110),
    ("fonte", "Fonte", 80),
    ("flags", "Flags", 80),
]

_COR_FONTE = {
    FonteDocumento.CNIS: "#1a3a6b",
    FonteDocumento.CTPS: "#1a5c2e",
    FonteDocumento.CTC: "#4a1a7a",
    FonteDocumento.HOLERITE: "#1a5a5a",
    FonteDocumento.PRO_LABORE: "#7a3a1a",
    FonteDocumento.PGDAS: "#5a4a1a",
    FonteDocumento.DARF: "#5a1a1a",
    FonteDocumento.FGTS: "#1a4a5a",
    FonteDocumento.MANUAL: "#7a5a1a",
}


class CompetenciasTable(ctk.CTkFrame):

    def __init__(self, parent, app: "App", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._app = app
        self._caso = None
        self._competencias: List[Competencia] = []
        self._build()

    def _build(self) -> None:
        # Barra de ferramentas
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkButton(barra, text="+ Adicionar", width=100, command=self._adicionar).pack(side="left", padx=2)
        ctk.CTkButton(barra, text="Remover", width=90, command=self._remover_selecionado).pack(side="left", padx=2)
        ctk.CTkButton(barra, text="Atualizar INPC", width=120, command=self._atualizar_inpc).pack(side="left", padx=2)

        # Filtros
        filtros = ctk.CTkFrame(barra, fg_color="transparent")
        filtros.pack(side="left", padx=8)

        ctk.CTkLabel(filtros, text="Fonte:").pack(side="left")
        self._filtro_fonte = ctk.CTkComboBox(filtros, width=100,
            values=["Todos"] + [f.value for f in FonteDocumento],
            command=lambda _: self._aplicar_filtro())
        self._filtro_fonte.set("Todos")
        self._filtro_fonte.pack(side="left", padx=4)

        ctk.CTkLabel(filtros, text="De:").pack(side="left", padx=(8, 2))
        self._filtro_de = ctk.CTkEntry(filtros, width=72, placeholder_text="MM/YYYY")
        self._filtro_de.pack(side="left")
        ctk.CTkLabel(filtros, text="Até:").pack(side="left", padx=(4, 2))
        self._filtro_ate = ctk.CTkEntry(filtros, width=72, placeholder_text="MM/YYYY")
        self._filtro_ate.pack(side="left")
        ctk.CTkButton(filtros, text="Filtrar", width=70, command=self._aplicar_filtro).pack(side="left", padx=4)

        # Treeview com scrollbars
        frame_tree = ctk.CTkFrame(self)
        frame_tree.pack(fill="both", expand=True, padx=8, pady=4)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

        colunas = [c[0] for c in _COLUNAS]
        self._tree = ttk.Treeview(frame_tree, columns=colunas, show="headings", selectmode="extended")

        for col, titulo, largura in _COLUNAS:
            self._tree.heading(col, text=titulo, command=lambda c=col: self._ordenar(c))
            self._tree.column(col, width=largura, minwidth=60)

        sb_v = ttk.Scrollbar(frame_tree, orient="vertical", command=self._tree.yview)
        sb_h = ttk.Scrollbar(frame_tree, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        sb_v.grid(row=0, column=1, sticky="ns")
        sb_h.grid(row=1, column=0, sticky="ew")
        frame_tree.grid_rowconfigure(0, weight=1)
        frame_tree.grid_columnconfigure(0, weight=1)

        self._tree.bind("<Double-Button-1>", self._on_duplo_clique)

        # Rodapé
        self._lbl_rodape = ctk.CTkLabel(self, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self._lbl_rodape.pack(pady=4)

        # Tooltip de pendência
        self._tooltip = tk.Label(self, text="Pendências CNIS são informativas e NÃO afetam o cálculo",
                                  bg="#333333", fg="white", font=("Segoe UI", 9), padx=6, pady=3)

    def carregar_caso(self, caso) -> None:
        self._caso = caso
        if caso is None:
            self._competencias = []
            self._renderizar([])
            return
        self._competencias = sorted(
            CompetenciaRepository.buscar_por_caso(caso.id),
            key=lambda c: _comp_key(c.competencia),
        )
        self._renderizar(self._competencias)

    def _renderizar(self, competencias: List[Competencia]) -> None:
        self._tree.delete(*self._tree.get_children())

        # Garante ordem cronológica sempre que renderiza
        ordenadas = sorted(competencias, key=lambda c: _comp_key(c.competencia))

        for c in ordenadas:
            flags = self._montar_flags(c)
            valores = (
                c.competencia,
                c.empregador_nome,
                c.tipo_vinculo.value,
                f"R$ {c.remuneracao_bruta:,.2f}",
                f"R$ {c.base_contribuicao:,.2f}",
                f"R$ {c.remuneracao_atualizada:,.2f}" if c.remuneracao_atualizada else "—",
                c.fonte.value,
                flags,
            )
            tag = c.fonte.value.lower()
            item_id = self._tree.insert("", "end", iid=str(c.id), values=valores, tags=(tag,))

        # Aplica cores por fonte (melhor compatibilidade em dark mode via tag)
        for fonte in FonteDocumento:
            try:
                self._tree.tag_configure(fonte.value.lower(), background=_COR_FONTE.get(fonte, ""))
            except Exception:
                pass

        self._atualizar_rodape(competencias)

    def _montar_flags(self, c: Competencia) -> str:
        flags = []
        if c.flag_inconsistencia:
            flags.append("⚠")
        if c.flag_sobreposicao:
            flags.append("🔴")
        if c.flag_pendencia_cnis:
            flags.append("ℹ")
        if c.editado_manualmente:
            flags.append("✏")
        return " ".join(flags)

    def _atualizar_rodape(self, competencias: List[Competencia]) -> None:
        if not competencias:
            self._lbl_rodape.configure(text="Sem competências cadastradas.")
            return

        comps_ord = sorted(competencias, key=lambda c: _comp_key(c.competencia))
        primeiro = comps_ord[0].competencia
        ultimo = comps_ord[-1].competencia
        total_meses = len({c.competencia for c in competencias})
        anos = total_meses // 12
        meses = total_meses % 12

        self._lbl_rodape.configure(
            text=f"{len(competencias)} competências  |  {primeiro} a {ultimo}  |  Tempo apurado: {anos}a {meses}m"
        )

    def _aplicar_filtro(self) -> None:
        fonte_sel = self._filtro_fonte.get()
        de_str = self._filtro_de.get().strip()
        ate_str = self._filtro_ate.get().strip()

        filtradas = self._competencias
        if fonte_sel != "Todos":
            filtradas = [c for c in filtradas if c.fonte.value == fonte_sel]
        if de_str:
            filtradas = [c for c in filtradas if _comp_key(c.competencia) >= _comp_key(de_str)]
        if ate_str:
            filtradas = [c for c in filtradas if _comp_key(c.competencia) <= _comp_key(ate_str)]

        self._renderizar(filtradas)

    def _ordenar(self, coluna: str) -> None:
        # Competência e campos monetários precisam de chave numérica para ordenar certo
        if coluna == "competencia":
            self._competencias.sort(key=lambda c: _comp_key(c.competencia))
        elif coluna in ("remuneracao_bruta", "base_contribuicao", "remuneracao_atualizada"):
            self._competencias.sort(key=lambda c: float(getattr(c, coluna) or 0))
        else:
            self._competencias.sort(key=lambda c: str(getattr(c, coluna, "") or "").lower())
        self._renderizar(self._competencias)

    def _on_duplo_clique(self, event) -> None:
        item = self._tree.identify_row(event.y)
        coluna = self._tree.identify_column(event.x)
        if not item or not coluna:
            return

        comp_id = int(item)
        comp = next((c for c in self._competencias if c.id == comp_id), None)
        if comp is None:
            return

        col_idx = int(coluna[1:]) - 1
        col_nome = _COLUNAS[col_idx][0]
        editaveis = {"remuneracao_bruta", "base_contribuicao", "empregador_nome", "competencia"}

        if col_nome not in editaveis:
            return

        # Editor inline
        x, y, w, h = self._tree.bbox(item, coluna)
        entry = ctk.CTkEntry(self._tree, width=w)
        entry.place(x=x, y=y, width=w, height=h)

        valor_atual = getattr(comp, col_nome, "")
        if isinstance(valor_atual, Decimal):
            entry.insert(0, str(valor_atual))
        else:
            entry.insert(0, str(valor_atual))
        entry.focus_set()
        entry.select_range(0, "end")

        def _confirmar(event=None):
            novo = entry.get().strip()
            entry.destroy()
            self._salvar_edicao(comp, col_nome, novo)

        entry.bind("<Return>", _confirmar)
        entry.bind("<FocusOut>", _confirmar)
        entry.bind("<Escape>", lambda _: entry.destroy())

    def _salvar_edicao(self, comp: Competencia, campo: str, valor: str) -> None:
        try:
            if campo in ("remuneracao_bruta", "base_contribuicao"):
                setattr(comp, campo, Decimal(valor.replace(",", ".")))
            else:
                setattr(comp, campo, valor)
            comp.editado_manualmente = True
            CompetenciaRepository.atualizar(comp)
            self._renderizar(self._competencias)
        except (InvalidOperation, Exception) as exc:
            logger.warning("Edição inválida em %s: %s", campo, exc)

    def _adicionar(self) -> None:
        if not self._caso:
            return
        from .dialogs import AdicionarCompetenciaDialog
        dlg = AdicionarCompetenciaDialog(self._app, self._caso.id)
        self._app.wait_window(dlg)
        if dlg.resultado:
            comp_id = CompetenciaRepository.salvar(dlg.resultado)
            dlg.resultado.id = comp_id
            self._competencias.append(dlg.resultado)
            self._renderizar(self._competencias)

    def _remover_selecionado(self) -> None:
        selecionados = self._tree.selection()
        for item in selecionados:
            comp_id = int(item)
            CompetenciaRepository.deletar(comp_id)
            self._competencias = [c for c in self._competencias if c.id != comp_id]
        self._renderizar(self._competencias)

    def _atualizar_inpc(self) -> None:
        if not self._caso or not self._competencias:
            return

        from datetime import date
        data_ref = date.today().strftime("%m/%Y")
        btn = None  # referência ao botão seria necessária para desabilitar

        def _trabalho() -> None:
            from ..engine.correcao_monetaria import atualizar_lote
            atualizadas = atualizar_lote(list(self._competencias), data_ref)
            for c in atualizadas:
                if c.id:
                    CompetenciaRepository.atualizar(c)
            self._competencias = atualizadas
            self._app.after(0, lambda: self._renderizar(self._competencias))

        threading.Thread(target=_trabalho, daemon=True).start()

    @property
    def competencias(self) -> List[Competencia]:
        return list(self._competencias)


def _comp_key(competencia: str) -> int:
    try:
        m, a = competencia.split("/")
        return int(a) * 100 + int(m)
    except ValueError:
        return 0
