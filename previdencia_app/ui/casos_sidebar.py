"""Sidebar de lista de casos/clientes."""
from __future__ import annotations

import logging
from typing import Callable, Optional

import customtkinter as ctk

from ..db import CasoRepository
from ..models import Caso

logger = logging.getLogger(__name__)


class CasosSidebar(ctk.CTkFrame):

    def __init__(self, parent, width: int, on_select: Callable[[Caso], None], **kwargs) -> None:
        super().__init__(parent, width=width, **kwargs)
        self._on_select = on_select
        self._casos: list[Caso] = []
        self._selecionado: Optional[int] = None
        self._build()
        self.atualizar()

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

        for caso in casos:
            btn = ctk.CTkButton(
                self._scroll,
                text=f"{caso.nome}\n{_formatar_cpf(caso.cpf)}",
                anchor="w",
                font=ctk.CTkFont(size=12),
                height=48,
                fg_color=("gray75", "gray25") if caso.id == self._selecionado else "transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray65", "gray35"),
                command=lambda c=caso: self._selecionar(c),
            )
            btn.pack(fill="x", pady=2, padx=4)

    def _selecionar(self, caso: Caso) -> None:
        self._selecionado = caso.id
        self.atualizar()
        self._on_select(caso)


def _formatar_cpf(cpf: str) -> str:
    digitos = "".join(c for c in cpf if c.isdigit())
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return cpf
