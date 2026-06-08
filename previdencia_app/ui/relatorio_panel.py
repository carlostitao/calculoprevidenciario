"""Painel de preview e exportação de relatório PDF."""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from ..config import DB_PATH

if TYPE_CHECKING:
    from .app import App

logger = logging.getLogger(__name__)

_SECOES = [
    ("capa", "Capa do relatório"),
    ("resumo", "Resumo executivo"),
    ("periodos", "Períodos contributivos"),
    ("tabela", "Tabela completa de competências"),
    ("confronto", "Confronto de fontes"),
    ("calculo", "Cálculo do salário de benefício"),
    ("inconsistencias", "Inconsistências detectadas"),
]


class RelatorioPanel(ctk.CTkFrame):

    def __init__(self, parent, app: "App", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._app = app
        self._caso = None
        self._checks: dict[str, ctk.BooleanVar] = {}
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Seções a incluir no relatório:",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=16, pady=(12, 4))

        for key, label in _SECOES:
            var = ctk.BooleanVar(value=True)
            self._checks[key] = var
            ctk.CTkCheckBox(self, text=label, variable=var).pack(anchor="w", padx=24, pady=2)

        sep = ctk.CTkFrame(self, height=2, fg_color=("gray70", "gray30"))
        sep.pack(fill="x", padx=16, pady=12)

        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=16)
        ctk.CTkButton(barra, text="Gerar PDF", width=120, command=self._gerar).pack(side="left", padx=4)
        self._lbl_status = ctk.CTkLabel(barra, text="")
        self._lbl_status.pack(side="left", padx=8)

    def carregar_caso(self, caso) -> None:
        self._caso = caso

    def _gerar(self) -> None:
        if not self._caso:
            self._lbl_status.configure(text="Nenhum caso selecionado.", text_color="red")
            return

        secoes_ativas = [k for k, v in self._checks.items() if v.get()]
        self._lbl_status.configure(text="Gerando PDF...", text_color="gray")

        def _trabalho() -> None:
            try:
                from ..export.relatorio_pdf import gerar_relatorio
                from ..db import CompetenciaRepository
                from ..engine.confronto import confrontar
                from ..engine.regras.salario_beneficio import calcular
                from datetime import date

                competencias = CompetenciaRepository.buscar_por_caso(self._caso.id)
                confronto = confrontar(self._caso.id, competencias)
                resultados_calculo = calcular(self._caso, competencias, date.today())

                caminho = gerar_relatorio(
                    caso=self._caso,
                    competencias=competencias,
                    confronto=confronto,
                    resultados_calculo=resultados_calculo,
                    secoes=secoes_ativas,
                )
                self._app.after(0, lambda: self._pos_geracao(caminho))
            except Exception as exc:
                logger.error("Erro ao gerar relatório: %s", exc)
                self._app.after(0, lambda: self._lbl_status.configure(
                    text=f"Erro: {exc}", text_color="red"))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _pos_geracao(self, caminho: str) -> None:
        self._lbl_status.configure(text=f"PDF gerado: {Path(caminho).name}", text_color="#2ecc71")
        # Abre o PDF no visualizador padrão
        try:
            if sys.platform == "win32":
                subprocess.Popen(["start", "", caminho], shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", caminho])
            else:
                subprocess.Popen(["xdg-open", caminho])
        except Exception as exc:
            logger.warning("Não foi possível abrir o PDF: %s", exc)
