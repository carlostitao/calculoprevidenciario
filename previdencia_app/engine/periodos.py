"""Cálculo de tempo contributivo, carências e gaps."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Set

from ..models import Competencia

logger = logging.getLogger(__name__)


@dataclass
class TempoPeriodo:
    anos: int
    meses: int
    dias: int
    total_meses: int
    total_dias: int
    competencias_validas: int
    competencias_desconsideradas: int  # sobreposições já contadas


@dataclass
class Gap:
    competencia_anterior: str
    competencia_posterior: str
    meses_faltando: int


@dataclass
class ResultadoCarencia:
    beneficio: str
    carencia_necessaria: int  # em meses
    carencia_apurada: int
    suficiente: bool
    faltam_meses: int


# Carências mínimas por benefício (em meses)
_CARENCIAS: dict[str, int] = {
    "aposentadoria_por_idade": 180,
    "aposentadoria_por_tempo": 180,
    "aposentadoria_invalidez": 12,
    "auxilio_doenca": 12,
    "salario_maternidade_ci": 10,
    "salario_maternidade_clt": 0,
    "pensao_por_morte": 18,
    "auxilio_reclusao": 24,
}


def _comp_to_yyyymm(competencia: str) -> int:
    """'MM/YYYY' → YYYYMM como inteiro para comparação."""
    mes, ano = competencia.split("/")
    return int(ano) * 100 + int(mes)


def _comp_to_date(competencia: str) -> date:
    mes, ano = competencia.split("/")
    return date(int(ano), int(mes), 1)


def calcular_tempo_contributivo(competencias: List[Competencia]) -> TempoPeriodo:
    """
    Soma tempo de contribuição válido descontando sobreposições.
    Pendências CNIS não impedem a contagem.
    """
    # Coleta competências únicas (sobreposições contam uma vez)
    unicas: Set[str] = set()
    total = 0
    desconsideradas = 0

    for c in competencias:
        if c.competencia in unicas:
            desconsideradas += 1
            continue
        unicas.add(c.competencia)
        total += 1

    total_meses = len(unicas)
    total_dias = total_meses * 30  # convenção previdenciária

    anos = total_meses // 12
    meses_restantes = total_meses % 12
    dias = 0  # granularidade mensal

    return TempoPeriodo(
        anos=anos,
        meses=meses_restantes,
        dias=dias,
        total_meses=total_meses,
        total_dias=total_dias,
        competencias_validas=total,
        competencias_desconsideradas=desconsideradas,
    )


def verificar_carencia(competencias: List[Competencia], beneficio: str) -> ResultadoCarencia:
    """Verifica se a carência mínima para o benefício foi atingida."""
    necessaria = _CARENCIAS.get(beneficio, 180)
    apurada = len({c.competencia for c in competencias})

    return ResultadoCarencia(
        beneficio=beneficio,
        carencia_necessaria=necessaria,
        carencia_apurada=apurada,
        suficiente=apurada >= necessaria,
        faltam_meses=max(0, necessaria - apurada),
    )


def listar_periodos_sem_contribuicao(competencias: List[Competencia]) -> List[Gap]:
    """Identifica gaps (lacunas) na linha do tempo contributiva."""
    if not competencias:
        return []

    ordenadas = sorted(competencias, key=lambda c: _comp_to_yyyymm(c.competencia))
    unicas = sorted({c.competencia for c in ordenadas}, key=_comp_to_yyyymm)

    gaps: List[Gap] = []
    for i in range(len(unicas) - 1):
        atual = _comp_to_date(unicas[i])
        proxima = _comp_to_date(unicas[i + 1])

        # Meses entre competências consecutivas
        diff_meses = (proxima.year - atual.year) * 12 + (proxima.month - atual.month)
        if diff_meses > 1:
            gaps.append(Gap(
                competencia_anterior=unicas[i],
                competencia_posterior=unicas[i + 1],
                meses_faltando=diff_meses - 1,
            ))

    return gaps
