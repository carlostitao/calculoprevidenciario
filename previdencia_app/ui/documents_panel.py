"""Painel de upload e gerenciamento de documentos."""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import customtkinter as ctk
from tkinter import filedialog

from ..config import DB_PATH
from ..db import DocumentoRepository
from ..models import Documento
from ..models.documento import StatusDocumento, TipoDocumento

if TYPE_CHECKING:
    from .app import App

logger = logging.getLogger(__name__)

_DOCS_DIR = DB_PATH.parent / "documentos"
_DOCS_DIR.mkdir(parents=True, exist_ok=True)

_STATUS_COR = {
    StatusDocumento.AGUARDANDO: "#888888",
    StatusDocumento.PROCESSANDO: "#f0a500",
    StatusDocumento.CONCLUIDO: "#2ecc71",
    StatusDocumento.ERRO: "#e74c3c",
}

_STATUS_ICONE = {
    StatusDocumento.AGUARDANDO: "○",
    StatusDocumento.PROCESSANDO: "◐",
    StatusDocumento.CONCLUIDO: "●",
    StatusDocumento.ERRO: "✕",
}


class DocumentsPanel(ctk.CTkFrame):

    def __init__(self, parent, app: "App", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._app = app
        self._caso = None
        self._rows: dict[int, ctk.CTkFrame] = {}
        self._build()

    def _build(self) -> None:
        # Barra de ações
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=8, pady=8)

        ctk.CTkButton(barra, text="+ Adicionar Documentos", command=self._adicionar).pack(side="left", padx=4)
        ctk.CTkButton(barra, text="Processar Todos", command=self._processar_todos).pack(side="left", padx=4)

        # Lista scrollável
        self._scroll = ctk.CTkScrollableFrame(self, label_text="Documentos importados")
        self._scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Mensagem vazia
        self._lbl_vazio = ctk.CTkLabel(self._scroll, text="Nenhum documento adicionado.", text_color="gray")
        self._lbl_vazio.pack(pady=20)

    def carregar_caso(self, caso) -> None:
        self._caso = caso
        self._atualizar_lista()

    def _atualizar_lista(self) -> None:
        for w in self._scroll.winfo_children():
            w.destroy()
        self._rows.clear()

        if not self._caso:
            return

        docs = DocumentoRepository.buscar_por_caso(self._caso.id)
        if not docs:
            self._lbl_vazio = ctk.CTkLabel(self._scroll, text="Nenhum documento adicionado.", text_color="gray")
            self._lbl_vazio.pack(pady=20)
            return

        for doc in docs:
            self._criar_linha(doc)

    def _criar_linha(self, doc: Documento) -> None:
        frame = ctk.CTkFrame(self._scroll, corner_radius=6)
        frame.pack(fill="x", padx=4, pady=3)
        frame.grid_columnconfigure(1, weight=1)

        icone = _STATUS_ICONE.get(doc.status, "?")
        cor = _STATUS_COR.get(doc.status, "gray")
        ctk.CTkLabel(frame, text=icone, text_color=cor, width=24, font=ctk.CTkFont(size=16)).grid(row=0, column=0, padx=6, pady=6)
        ctk.CTkLabel(frame, text=doc.nome_arquivo, anchor="w").grid(row=0, column=1, sticky="w", pady=6)
        ctk.CTkLabel(frame, text=doc.tipo.value, width=100, text_color="gray").grid(row=0, column=2, padx=4)
        ctk.CTkLabel(frame, text=doc.status.value, width=100, text_color=cor).grid(row=0, column=3, padx=4)

        btns = ctk.CTkFrame(frame, fg_color="transparent")
        btns.grid(row=0, column=4, padx=6)

        ctk.CTkButton(btns, text="Processar", width=80,
                      command=lambda d=doc: self._processar_documento(d)).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="Abrir", width=60,
                      command=lambda d=doc: self._abrir_arquivo(d)).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="✕", width=32, fg_color="#c0392b",
                      command=lambda d=doc: self._remover(d)).pack(side="left", padx=2)

        frame.bind("<Double-Button-1>", lambda _, d=doc: self._abrir_arquivo(d))
        self._rows[doc.id] = frame

    def _adicionar(self) -> None:
        if not self._caso:
            return
        arquivos = filedialog.askopenfilenames(
            title="Selecionar documentos",
            filetypes=[("Documentos", "*.pdf *.png *.jpg *.jpeg"), ("PDF", "*.pdf"), ("Imagens", "*.png *.jpg *.jpeg")],
        )
        for caminho in arquivos:
            self._importar_arquivo(caminho)

    def _importar_arquivo(self, caminho: str) -> None:
        p = Path(caminho)
        destino = _DOCS_DIR / f"{self._caso.id}_{p.name}"
        shutil.copy2(caminho, destino)

        doc = Documento(
            caso_id=self._caso.id,
            nome_arquivo=p.name,
            caminho=str(destino),
            tipo=TipoDocumento.DESCONHECIDO,
            status=StatusDocumento.AGUARDANDO,
        )
        doc_id = DocumentoRepository.salvar(doc)
        doc.id = doc_id
        self._criar_linha(doc)

    def _processar_documento(self, doc: Documento) -> None:
        """Processa em thread separada — extrai texto e chama IA."""
        DocumentoRepository.atualizar_status(doc.id, StatusDocumento.PROCESSANDO.value)
        self._atualizar_linha_status(doc.id, StatusDocumento.PROCESSANDO)

        def _trabalho() -> None:
            try:
                texto = _extrair_texto(doc.caminho)
                DocumentoRepository.atualizar_texto(doc.id, texto)

                from ..ai.classifier import classificar_documento
                tipo = classificar_documento(texto)
                doc.tipo = tipo

                from ..ai.extractor import extrair
                from ..db import CompetenciaRepository
                competencias = extrair(texto, tipo, self._caso.id, doc.id)

                if competencias:
                    CompetenciaRepository.salvar_lote(competencias)

                DocumentoRepository.atualizar_status(doc.id, StatusDocumento.CONCLUIDO.value)
                self._app.after(0, lambda: self._pos_processamento(doc.id, StatusDocumento.CONCLUIDO, len(competencias)))
            except Exception as exc:
                logger.error("Erro processando documento %s: %s", doc.nome_arquivo, exc)
                DocumentoRepository.atualizar_status(doc.id, StatusDocumento.ERRO.value, str(exc))
                self._app.after(0, lambda: self._atualizar_linha_status(doc.id, StatusDocumento.ERRO))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _pos_processamento(self, doc_id: int, status: StatusDocumento, n_competencias: int) -> None:
        self._atualizar_linha_status(doc_id, status)
        if self._caso and self._app.caso_ativo:
            self._app._panel_comp.carregar_caso(self._app.caso_ativo)

    def _atualizar_linha_status(self, doc_id: int, status: StatusDocumento) -> None:
        self._app.after(0, self._atualizar_lista)

    def _processar_todos(self) -> None:
        if not self._caso:
            return
        docs = DocumentoRepository.buscar_por_caso(self._caso.id)
        for doc in docs:
            if doc.status in (StatusDocumento.AGUARDANDO, StatusDocumento.ERRO):
                self._processar_documento(doc)

    def _remover(self, doc: Documento) -> None:
        try:
            Path(doc.caminho).unlink(missing_ok=True)
        except Exception:
            pass
        from sqlalchemy import delete
        from ..db.database import documentos_table, get_session
        with get_session() as conn:
            conn.execute(delete(documentos_table).where(documentos_table.c.id == doc.id))
        self._atualizar_lista()

    def _abrir_arquivo(self, doc: Documento) -> None:
        caminho = Path(doc.caminho)
        if not caminho.exists():
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(["start", "", str(caminho)], shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(caminho)])
            else:
                subprocess.Popen(["xdg-open", str(caminho)])
        except Exception as exc:
            logger.warning("Não foi possível abrir o arquivo: %s", exc)


def _extrair_texto(caminho: str) -> str:
    """Extrai texto do PDF/imagem, com fallback para OCR."""
    p = Path(caminho)
    sufixo = p.suffix.lower()

    if sufixo == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(caminho) as pdf:
                partes = [page.extract_text() or "" for page in pdf.pages]
            texto = "\n".join(partes).strip()
            if texto:
                return texto
        except Exception as exc:
            logger.warning("pdfplumber falhou em %s: %s — tentando OCR", caminho, exc)

    # Fallback OCR
    try:
        import pytesseract
        from PIL import Image

        if sufixo == ".pdf":
            import pdfplumber
            with pdfplumber.open(caminho) as pdf:
                partes = []
                for page in pdf.pages:
                    img = page.to_image(resolution=200).original
                    partes.append(pytesseract.image_to_string(img, lang="por"))
            return "\n".join(partes)
        else:
            img = Image.open(caminho)
            return pytesseract.image_to_string(img, lang="por")
    except Exception as exc:
        logger.error("OCR falhou em %s: %s", caminho, exc)
        return ""
