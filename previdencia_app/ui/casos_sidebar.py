"""Sidebar de lista de casos/clientes."""
from __future__ import annotations

import logging
from tkinter import messagebox
from typing import Callable, Optional

import customtkinter as ctk

from ..db import CasoRepository
from ..models import Caso
from .theme import (AZUL_CLARO, AZUL_PRIMARIO, VERDE_OK, VERMELHO_ESCURO,
                    CINZA_TEXTO, BG_CARD, BG_CARD2, BG_SEP,
                    font_secao, font_label, font_pequeno)

logger = logging.getLogger(__name__)


def _iniciais(nome: str) -> str:
    partes = nome.strip().split()
    if len(partes) >= 2:
        return (partes[0][0] + partes[-1][0]).upper()
    return nome[:2].upper() if nome else "??"


def _formatar_cpf(cpf: str) -> str:
    d = "".join(c for c in cpf if c.isdigit())
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else cpf


_CORES_AVATAR = [
    "#1a6fad", "#2e86de", "#8e44ad", "#16a085",
    "#d35400", "#c0392b", "#27ae60", "#2c3e50",
]


class CasosSidebar(ctk.CTkFrame):

    def __init__(self, parent, width: int, on_select: Callable[[Caso], None], **kwargs) -> None:
        super().__init__(parent, width=width, corner_radius=10, **kwargs)
        self._on_select = on_select
        self._on_deletar: Optional[Callable[[int], None]] = None
        self._casos: list[Caso] = []
        self._selecionado: Optional[int] = None
        self._build()
        self.atualizar()

    def set_on_deletar(self, callback: Callable[[int], None]) -> None:
        self._on_deletar = callback

    def _build(self) -> None:
        self.grid_propagate(False)

        # Cabeçalho da sidebar
        hdr = ctk.CTkFrame(self, fg_color=(AZUL_PRIMARIO, "#0d1b35"), corner_radius=8)
        hdr.pack(fill="x", padx=6, pady=(8, 6))
        ctk.CTkLabel(
            hdr, text="📋  CASOS",
            font=font_secao(), text_color="#ffffff",
        ).pack(side="left", padx=12, pady=8)

        # Botão novo caso dentro da sidebar
        ctk.CTkButton(
            hdr, text="＋", width=32, height=28,
            corner_radius=6,
            fg_color="#ffffff22", hover_color="#ffffff44",
            text_color="#ffffff",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._novo_caso_sidebar,
        ).pack(side="right", padx=8)

        # Busca
        busca_frame = ctk.CTkFrame(self, fg_color="transparent")
        busca_frame.pack(fill="x", padx=6, pady=(0, 6))
        ctk.CTkLabel(busca_frame, text="🔎", font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 0))
        self._entry_busca = ctk.CTkEntry(
            busca_frame, placeholder_text="Buscar por nome ou CPF...",
            height=32, corner_radius=8,
        )
        self._entry_busca.pack(side="left", fill="x", expand=True, padx=4)
        self._entry_busca.bind("<KeyRelease>", lambda _: self._filtrar())

        # Lista scrollável
        self._scroll = ctk.CTkScrollableFrame(self, label_text="", corner_radius=8)
        self._scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def _novo_caso_sidebar(self) -> None:
        """Aciona o diálogo de novo caso através da janela pai."""
        w = self
        while w.master:
            w = w.master
            if hasattr(w, "_novo_caso"):
                w._novo_caso()
                return

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
            vazio = ctk.CTkFrame(self._scroll, fg_color="transparent")
            vazio.pack(fill="x", pady=20)
            ctk.CTkLabel(vazio, text="👤", font=ctk.CTkFont(size=28)).pack()
            ctk.CTkLabel(vazio, text="Nenhum caso encontrado.",
                         text_color=CINZA_TEXTO, font=font_pequeno()).pack()
            return

        for caso in casos:
            self._criar_item(caso)

    def _criar_item(self, caso: Caso) -> None:
        selecionado = caso.id == self._selecionado
        cor_borda = AZUL_CLARO if selecionado else "transparent"
        cor_fundo = (("#e8f4fd", "#1a2a3e") if selecionado else ("transparent", "transparent"))

        frame = ctk.CTkFrame(
            self._scroll, corner_radius=8,
            fg_color=cor_fundo,
            border_width=2 if selecionado else 0,
            border_color=cor_borda,
        )
        frame.pack(fill="x", pady=3, padx=2)
        frame.grid_columnconfigure(1, weight=1)

        # Avatar com iniciais
        cor_av = _CORES_AVATAR[hash(caso.nome) % len(_CORES_AVATAR)]
        avatar = ctk.CTkFrame(frame, width=40, height=40, corner_radius=20, fg_color=cor_av)
        avatar.grid(row=0, column=0, rowspan=2, padx=(8, 6), pady=8)
        avatar.grid_propagate(False)
        ctk.CTkLabel(
            avatar,
            text=_iniciais(caso.nome),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#ffffff",
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Nome + CPF (clicáveis)
        nome_btn = ctk.CTkButton(
            frame,
            text=caso.nome,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold" if selecionado else "normal"),
            height=20,
            fg_color="transparent",
            text_color=(("#1a1a2e", "#e0e8f0") if selecionado else ("#333333", "#cccccc")),
            hover_color=("gray80", "gray30"),
            command=lambda c=caso: self._selecionar(c),
        )
        nome_btn.grid(row=0, column=1, sticky="ew", padx=(0, 4), pady=(6, 0))

        cpf_btn = ctk.CTkButton(
            frame,
            text=_formatar_cpf(caso.cpf),
            anchor="w",
            font=font_pequeno(),
            height=16,
            fg_color="transparent",
            text_color=CINZA_TEXTO,
            hover_color=("gray80", "gray30"),
            command=lambda c=caso: self._selecionar(c),
        )
        cpf_btn.grid(row=1, column=1, sticky="ew", padx=(0, 4), pady=(0, 6))

        # Botão deletar
        btn_del = ctk.CTkButton(
            frame, text="✕", width=26, height=26, corner_radius=13,
            fg_color="transparent",
            text_color=CINZA_TEXTO,
            hover_color=(VERMELHO_ESCURO, VERMELHO_ESCURO),
            font=ctk.CTkFont(size=11),
            command=lambda c=caso: self._confirmar_deletar(c),
        )
        btn_del.grid(row=0, column=2, rowspan=2, padx=(0, 6))

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

        if self._selecionado == caso_id:
            self._selecionado = None

        self.atualizar()
        if self._on_deletar:
            self._on_deletar(caso_id)
