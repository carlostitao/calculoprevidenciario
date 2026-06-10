"""Painel de upload e gerenciamento de documentos."""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        self._atualizar_lista() if caso else self._limpar_lista()

    def _limpar_lista(self) -> None:
        for w in self._scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._scroll, text="Selecione ou crie um caso.", text_color="gray").pack(pady=20)

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
                # B) Cache: reutiliza texto já extraído anteriormente
                if doc.texto_extraido and len(doc.texto_extraido) >= 100:
                    logger.info("[CACHE] Reutilizando texto salvo para %s (%d chars)", doc.nome_arquivo, len(doc.texto_extraido))
                    texto = doc.texto_extraido
                else:
                    texto = _extrair_texto(doc.caminho)
                    DocumentoRepository.atualizar_texto(doc.id, texto)

                from ..ai.classifier import classificar_documento
                tipo = classificar_documento(texto)
                doc.tipo = tipo
                DocumentoRepository.atualizar_tipo(doc.id, tipo.value)

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
    """
    Extrai texto do documento usando três estratégias em cascata:

    1. pdfplumber — rápido e gratuito para PDFs digitais (texto selecionável)
    2. Claude Vision — OCR via API para PDFs escaneados e imagens,
       sem necessidade do Tesseract instalado localmente
    3. Fallback Tesseract local — se disponível e as anteriores falharem
    """
    p = Path(caminho)
    sufixo = p.suffix.lower()

    # ── Estratégia 1: pdfplumber para PDFs com texto nativo ─────────────────
    if sufixo == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(caminho) as pdf:
                partes = [page.extract_text() or "" for page in pdf.pages]
            texto = "\n".join(partes).strip()
            # Considera válido se tiver ao menos 100 chars de conteúdo real
            if len(texto) >= 100:
                logger.info("pdfplumber extraiu %d chars de %s", len(texto), p.name)
                return texto
            logger.info("pdfplumber retornou texto curto (%d chars) — tentando OCR", len(texto))
        except Exception as exc:
            logger.warning("pdfplumber falhou em %s: %s", p.name, exc)

    # ── Estratégia 2: Claude Vision (sem Tesseract) ──────────────────────────
    texto_vision = _ocr_via_claude(caminho, sufixo)
    if texto_vision:
        return texto_vision

    # ── Estratégia 3: Tesseract local (fallback, opcional) ───────────────────
    return _ocr_tesseract(caminho, sufixo)


def _ocr_via_claude(caminho: str, sufixo: str) -> str:
    """
    Usa a API de visão do Claude para extrair texto de imagens e PDFs escaneados.
    Não requer nenhuma instalação local (Tesseract, Poppler, etc.).
    """
    from ..ai.client import get_client, _MIME_MAP
    from ..config import MODEL_EXTRACAO

    _SYSTEM_OCR = (
        "Você é um sistema de OCR especializado em documentos previdenciários brasileiros. "
        "Transcreva TODO o texto visível na imagem, preservando a estrutura (tabelas, colunas, "
        "cabeçalhos). Mantenha números, datas e valores exatamente como aparecem. "
        "Retorne apenas o texto transcrito, sem comentários adicionais."
    )
    _INSTRUCAO = "Transcreva todo o texto desta página do documento."

    partes: list[str] = []

    try:
        if sufixo == ".pdf":
            # A) OCR paralelo — renderiza todas as páginas e envia concorrentemente
            try:
                import pdfplumber
                from PIL import Image
                import io

                with pdfplumber.open(caminho) as pdf:
                    paginas_bytes: list[tuple[int, bytes]] = []
                    for i, page in enumerate(pdf.pages):
                        try:
                            img_pil: Image.Image = page.to_image(resolution=150).original
                            buf = io.BytesIO()
                            img_pil.save(buf, format="PNG")
                            paginas_bytes.append((i, buf.getvalue()))
                        except Exception as exc:
                            logger.warning("Erro ao renderizar pág %d: %s", i + 1, exc)

                logger.info("[OCR] %d páginas renderizadas — enviando em paralelo (workers=2)", len(paginas_bytes))

                resultados_ocr: dict[int, str] = {}

                def _ocr_pagina(item: tuple[int, bytes]) -> tuple[int, str]:
                    idx, img_bytes = item
                    r = get_client().chamar_com_imagem(
                        system=_SYSTEM_OCR,
                        instrucao=_INSTRUCAO,
                        imagem_bytes=img_bytes,
                        mime_type="image/png",
                        modelo=MODEL_EXTRACAO,
                        operacao="ocr_pdf_pagina",
                    )
                    if r.success and r.data:
                        return (idx, r.data["texto"])
                    logger.warning("[OCR] Falha na pág %d: %s", idx + 1, r.error)
                    return (idx, "")

                # 2 workers + submissão escalonada (0.3s entre jobs) para evitar
                # burst de 429 no rate limit da API
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futuros = {}
                    for i, item in enumerate(paginas_bytes):
                        if i > 0:
                            import time as _time
                            _time.sleep(0.3)
                        fut = pool.submit(_ocr_pagina, item)
                        futuros[fut] = item[0]
                    for futuro in as_completed(futuros):
                        try:
                            idx, texto_pag = futuro.result()
                            resultados_ocr[idx] = texto_pag
                        except Exception as exc:
                            logger.warning("[OCR] Exceção em pág %d: %s", futuros[futuro] + 1, exc)

                partes = [resultados_ocr.get(i, "") for i in range(len(paginas_bytes))]

            except ImportError:
                logger.warning("pdfplumber/Pillow não disponível para renderizar páginas PDF")

        elif sufixo in _MIME_MAP:
            # Imagem direta (PNG, JPG, etc.)
            mime = _MIME_MAP[sufixo]
            img_bytes = Path(caminho).read_bytes()
            result = get_client().chamar_com_imagem(
                system=_SYSTEM_OCR,
                instrucao=_INSTRUCAO,
                imagem_bytes=img_bytes,
                mime_type=mime,
                modelo=MODEL_EXTRACAO,
                operacao="ocr_imagem",
            )
            if result.success and result.data:
                partes.append(result.data["texto"])

    except Exception as exc:
        logger.error("OCR via Claude Vision falhou em %s: %s", caminho, exc)

    texto = "\n".join(partes).strip()
    if texto:
        logger.info("Claude Vision extraiu %d chars de %s", len(texto), Path(caminho).name)
    return texto


def _ocr_tesseract(caminho: str, sufixo: str) -> str:
    """Fallback com Tesseract local — usado apenas se disponível na máquina."""
    try:
        import pytesseract
        from PIL import Image

        if sufixo == ".pdf":
            import pdfplumber
            import io
            with pdfplumber.open(caminho) as pdf:
                partes = []
                for page in pdf.pages:
                    img: Image.Image = page.to_image(resolution=200).original
                    partes.append(pytesseract.image_to_string(img, lang="por"))
            return "\n".join(partes)
        else:
            img = Image.open(caminho)
            return pytesseract.image_to_string(img, lang="por")
    except ImportError:
        logger.debug("Tesseract não disponível — ignorado")
        return ""
    except Exception as exc:
        logger.error("Tesseract falhou em %s: %s", caminho, exc)
        return ""
