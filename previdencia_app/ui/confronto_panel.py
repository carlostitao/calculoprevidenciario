"""Painel de confronto de fontes e inconsistências."""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, List

import customtkinter as ctk

from ..db import CompetenciaRepository

if TYPE_CHECKING:
    from .app import App

logger = logging.getLogger(__name__)


class ConfrontoPanel(ctk.CTkFrame):

    def __init__(self, parent, app: "App", **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._app = app
        self._caso = None
        self._build()

    def _build(self) -> None:
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=8, pady=8)

        ctk.CTkButton(barra, text="Executar Confronto", command=self._executar).pack(side="left", padx=4)
        ctk.CTkButton(barra, text="Analisar com IA", command=self._analisar_ia).pack(side="left", padx=4)
        self._lbl_status = ctk.CTkLabel(barra, text="")
        self._lbl_status.pack(side="left", padx=12)

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._lbl_vazio = ctk.CTkLabel(self._scroll, text="Execute o confronto para ver os resultados.", text_color="gray")
        self._lbl_vazio.pack(pady=20)

    def carregar_caso(self, caso) -> None:
        self._caso = caso
        self._limpar()

    def _limpar(self) -> None:
        for w in self._scroll.winfo_children():
            w.destroy()
        self._lbl_vazio = ctk.CTkLabel(self._scroll, text="Execute o confronto para ver os resultados.", text_color="gray")
        self._lbl_vazio.pack(pady=20)

    def _executar(self) -> None:
        if not self._caso:
            return
        self._lbl_status.configure(text="Processando...")

        def _trabalho() -> None:
            from ..engine.confronto import confrontar
            competencias = CompetenciaRepository.buscar_por_caso(self._caso.id)
            resultado = confrontar(self._caso.id, competencias)
            self._app.after(0, lambda: self._exibir_resultado(resultado))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _analisar_ia(self) -> None:
        if not self._caso:
            return
        self._lbl_status.configure(text="Analisando com IA...")

        def _trabalho() -> None:
            from ..ai.analyzer import analisar_inconsistencias
            competencias = CompetenciaRepository.buscar_por_caso(self._caso.id)
            inconsistencias = analisar_inconsistencias(competencias)
            self._app.after(0, lambda: self._exibir_inconsistencias_ia(inconsistencias))

        threading.Thread(target=_trabalho, daemon=True).start()

    def _exibir_resultado(self, resultado) -> None:
        self._lbl_status.configure(text="Confronto concluído")
        for w in self._scroll.winfo_children():
            w.destroy()

        secoes = [
            ("Ausentes no CNIS", resultado.competencias_apenas_fontes_externas, "#e74c3c"),
            ("Apenas no CNIS", resultado.competencias_apenas_cnis, "#3498db"),
            ("Pendências CNIS (informativo)", resultado.pendencias_cnis, "#888888"),
        ]

        for titulo, items, cor in secoes:
            self._criar_secao(titulo, items, cor, tipo="lista")

        if resultado.divergencias_valor:
            self._criar_secao_divergencias(resultado.divergencias_valor)

        if resultado.sobreposicoes:
            self._criar_secao_sobreposicoes(resultado.sobreposicoes)

        if resultado.gaps:
            self._criar_secao_gaps(resultado.gaps)

        if not any([resultado.competencias_apenas_fontes_externas, resultado.divergencias_valor,
                    resultado.sobreposicoes, resultado.gaps]):
            ctk.CTkLabel(self._scroll, text="✓ Nenhuma divergência encontrada.", text_color="#2ecc71").pack(pady=16)

    def _criar_secao(self, titulo: str, items: list, cor: str, tipo: str = "lista") -> None:
        frame = ctk.CTkFrame(self._scroll, corner_radius=8)
        frame.pack(fill="x", padx=4, pady=4)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(header, text=f"{titulo} ({len(items)})", font=ctk.CTkFont(weight="bold"), text_color=cor).pack(side="left")

        if titulo.startswith("Pendências"):
            ctk.CTkLabel(header, text="  ⓘ Não afetam o cálculo", text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left")

        if items:
            inner = ctk.CTkFrame(frame, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=(0, 8))
            for item in items[:50]:
                ctk.CTkLabel(inner, text=f"• {item}", anchor="w").pack(fill="x")
            if len(items) > 50:
                ctk.CTkLabel(inner, text=f"... e mais {len(items)-50}", text_color="gray").pack()
        else:
            ctk.CTkLabel(frame, text="Nenhum.", text_color="gray").pack(padx=16, pady=(0, 8))

    def _criar_secao_divergencias(self, divergencias) -> None:
        frame = ctk.CTkFrame(self._scroll, corner_radius=8)
        frame.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(frame, text=f"Divergências de Valor ({len(divergencias)})",
                     font=ctk.CTkFont(weight="bold"), text_color="#f39c12").pack(anchor="w", padx=8, pady=(8, 4))

        for d in divergencias[:30]:
            inner = ctk.CTkFrame(frame, fg_color=("gray90", "gray20"), corner_radius=4)
            inner.pack(fill="x", padx=8, pady=2)
            ctk.CTkLabel(inner, text=f"{d.competencia}  {d.empregador[:40]}",
                         font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=8, pady=(4, 0))
            ctk.CTkLabel(inner,
                         text=f"  {d.fonte_a.value}: R$ {d.valor_a:,.2f}  ✕  {d.fonte_b.value}: R$ {d.valor_b:,.2f}  ({float(d.percentual_diferenca):.1f}%)",
                         font=ctk.CTkFont(size=11), text_color="#f39c12").pack(anchor="w", padx=8, pady=(0, 4))

    def _criar_secao_sobreposicoes(self, sobreposicoes) -> None:
        frame = ctk.CTkFrame(self._scroll, corner_radius=8)
        frame.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(frame, text=f"Sobreposições de Vínculo ({len(sobreposicoes)})",
                     font=ctk.CTkFont(weight="bold"), text_color="#9b59b6").pack(anchor="w", padx=8, pady=(8, 4))

        for s in sobreposicoes[:20]:
            cor = "#2ecc71" if s.permitida else "#e74c3c"
            inner = ctk.CTkFrame(frame, fg_color="transparent")
            inner.pack(fill="x", padx=8, pady=2)
            ctk.CTkLabel(inner, text=f"{s.competencia}: {s.vinculo_a[:30]} + {s.vinculo_b[:30]}",
                         font=ctk.CTkFont(size=11)).pack(anchor="w")
            ctk.CTkLabel(inner, text=f"  {s.descricao}", text_color=cor, font=ctk.CTkFont(size=10)).pack(anchor="w")

    def _criar_secao_gaps(self, gaps) -> None:
        frame = ctk.CTkFrame(self._scroll, corner_radius=8)
        frame.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(frame, text=f"Gaps sem Contribuição ({len(gaps)})",
                     font=ctk.CTkFont(weight="bold"), text_color="#e67e22").pack(anchor="w", padx=8, pady=(8, 4))

        for g in gaps:
            ctk.CTkLabel(frame,
                         text=f"  • {g.competencia_anterior} → {g.competencia_posterior}: {g.meses_faltando} meses sem contribuição",
                         anchor="w").pack(fill="x", padx=8)

    def _exibir_inconsistencias_ia(self, inconsistencias) -> None:
        self._lbl_status.configure(text=f"IA encontrou {len(inconsistencias)} inconsistência(s)")
        _COR_SEV = {"ALTA": "#e74c3c", "MEDIA": "#f39c12", "BAIXA": "#3498db"}

        frame = ctk.CTkFrame(self._scroll, corner_radius=8)
        frame.pack(fill="x", padx=4, pady=8)
        ctk.CTkLabel(frame, text="Análise de IA — Inconsistências",
                     font=ctk.CTkFont(weight="bold", size=13)).pack(anchor="w", padx=8, pady=(8, 4))

        if not inconsistencias:
            ctk.CTkLabel(frame, text="✓ Nenhuma inconsistência detectada pela IA.", text_color="#2ecc71").pack(padx=16, pady=8)
            return

        for inc in inconsistencias:
            cor = _COR_SEV.get(inc.severidade, "gray")
            inner = ctk.CTkFrame(frame, fg_color=("gray90", "gray20"), corner_radius=4)
            inner.pack(fill="x", padx=8, pady=3)
            titulo = f"[{inc.severidade}] {inc.tipo.value}" + (f" — {inc.competencia}" if inc.competencia else "")
            ctk.CTkLabel(inner, text=titulo, font=ctk.CTkFont(weight="bold"), text_color=cor).pack(anchor="w", padx=8, pady=(4, 0))
            ctk.CTkLabel(inner, text=inc.descricao, wraplength=700, anchor="w").pack(anchor="w", padx=8)
            if inc.sugestao:
                ctk.CTkLabel(inner, text=f"↳ {inc.sugestao}", text_color="gray",
                             wraplength=700, anchor="w", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=8, pady=(0, 4))
