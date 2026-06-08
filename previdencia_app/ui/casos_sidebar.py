"""Sidebar de lista de casos/clientes."""
from __future__ import annotations

import logging
from tkinter import messagebox
from typing import Callable, Optional

import customtkinter as ctk

from ..db import CasoRepository
from ..models import Caso

logger = logging.getLogger(__name__)


class CasosSidebar(ctk.CTkFrame):

    def __init__(self, parent, width: int, on_select: Callable[[Caso], None], **kwargs) -> None:
        super().__init__(parent, width=width, **kwargs)
        self._on_select = on_select
        self._on_deletar: Optional[Callable[[int], None]] = None
        self._casos: list[Caso] = []
        self._selecionado: Optional[int] = None
        self._build()
        self.atualizar()

    def set_on_deletar(self, callback: Callable[[int], None]) -> None:
        """Registra callback chamado após deletar um caso (recebe o caso_id deletado)."""
        self._on_deletar = callback

    def _build(self) -> None:
        self.grid_propagate(False)
        ctk.CTkLabel(self, text="CASOS", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12, 4))

        self._entry_busca = ctk.CTkEntry(self, placeholder_text="Buscar por nome...")
        self._entry_busca.pack(fill="x", padx=8, pady=4)
        self._entry_busca.bind("<KeyRelease>", lambda _: self._filtrar())

        self._scroll = ctk.CTkScrollableFrame(self, label_text="")
        self._scroll.pack(fill="both", expand=True, padx=4, pady=4)

    def atualizar(self) -> None:
        self._casos = CasoRepository.listar_todos()
        self._renderizar(self._casos)

    def _filtrar(self) -> None:
        termo = self._entry_busca.get().lower()
        filtrados = [c for c in self._casos if termo in c.nome.lower() or termo in c.cpf]
        self._renderizar(filtrados)

    def _renderizar(self, casos: list[Caso]) -> None:
        for widget in self._scroll.winfo_children():
            widget.destroy()

        if not casos:
            ctk.CTkLabel(self._scroll, text="Nenhum caso.", text_color="gray").pack(pady=8)
            return

        for caso in casos:
            self._criar_item(caso)

    def _criar_item(self, caso: Caso) -> None:
        selecionado = caso.id == self._selecionado

        # Container da linha
        frame = ctk.CTkFrame(
            self._scroll,
            corner_radius=6,
            fg_color=("gray75", "gray25") if selecionado else "transparent",
        )
        frame.pack(fill="x", pady=2, padx=4)
        frame.grid_columnconfigure(0, weight=1)

        # Botão de seleção (ocupa quase toda a largura)
        btn = ctk.CTkButton(
            frame,
            text=f"{caso.nome}\n{_formatar_cpf(caso.cpf)}",
            anchor="w",
            font=ctk.CTkFont(size=12),
            height=44,
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            hover_color=("gray65", "gray35"),
            command=lambda c=caso: self._selecionar(c),
        )
        btn.grid(row=0, column=0, sticky="ew", padx=(4, 0))

        # Botão deletar — visível sempre, cor discreta
        btn_del = ctk.CTkButton(
            frame,
            text="✕",
            width=28,
            height=28,
            corner_radius=4,
            fg_color="transparent",
            text_color=("gray50", "gray60"),
            hover_color=("#c0392b", "#922b21"),
            command=lambda c=caso: self._confirmar_deletar(c),
        )
        btn_del.grid(row=0, column=1, padx=(2, 6))

    def _selecionar(self, caso: Caso) -> None:
        self._selecionado = caso.id
        self.atualizar()
        self._on_select(caso)

    def _confirmar_deletar(self, caso: Caso) -> None:
        confirmado = messagebox.askyesno(
            title="Deletar caso",
            message=(
                f"Deletar o caso de {caso.nome}?\n\n"
                "Todas as competências e documentos vinculados serão removidos permanentemente."
            ),
            icon="warning",
        )
        if not confirmado:
            return

        caso_id = caso.id
        CasoRepository.deletar(caso_id)
        logger.info("Caso %d (%s) deletado", caso_id, caso.nome)

        # Limpa seleção se era o caso ativo
        if self._selecionado == caso_id:
            self._selecionado = None

        self.atualizar()

        if self._on_deletar:
            self._on_deletar(caso_id)


def _formatar_cpf(cpf: str) -> str:
    digitos = "".join(c for c in cpf if c.isdigit())
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return cpf
