"""Funções auxiliares compartilhadas pelas regras de cálculo."""
from __future__ import annotations

from ..periodos import TempoPeriodo


def detalhe_tempo(tempo: TempoPeriodo) -> dict:
    """
    Bloco padrão de detalhamento do tempo contributivo para o relatório.
    Expõe explicitamente o split pré/pós Plano Real.
    """
    return {
        "total": f"{tempo.anos}a {tempo.meses}m ({tempo.total_meses} meses)",
        "pos_plano_real_jul1994": f"{tempo.meses_pos_real} meses (entram na média)",
        "pre_plano_real": (
            f"{tempo.meses_pre_real} meses (contam tempo, NÃO entram na média)"
            if tempo.meses_pre_real
            else "nenhum"
        ),
    }
