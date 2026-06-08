"""Cálculo da média dos salários de contribuição."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from ...models import Competencia
from ..correcao_monetaria import atualizar_inpc

logger = logging.getLogger(__name__)

_INICIO_PERIODO = "07/1994"


@dataclass
class ResultadoMedia:
    media: Decimal
    total_competencias: int
    competencias_consideradas: int
    competencias_descartadas: int  # no caso dos 80% maiores
    soma_contribuicoes: Decimal
    menor_valor: Decimal
    maior_valor: Decimal
    data_referencia: str
    regra_aplicada: str


def _filtrar_desde_julho_1994(competencias: List[Competencia]) -> List[Competencia]:
    def _key(c: Competencia) -> int:
        mes, ano = c.competencia.split("/")
        return int(ano) * 100 + int(mes)

    return [c for c in competencias if _key(c) >= 199407]


def _garantir_atualizacao(competencias: List[Competencia], data_ref: str) -> List[Competencia]:
    """Garante que remuneracao_atualizada está preenchida, atualizando se necessário."""
    atualizadas = []
    for c in competencias:
        if c.remuneracao_atualizada is None:
            try:
                c.remuneracao_atualizada = atualizar_inpc(c.base_contribuicao, c.competencia, data_ref)
            except Exception as exc:
                logger.warning("Sem fator INPC para %s — usando valor nominal: %s", c.competencia, exc)
                c.remuneracao_atualizada = c.base_contribuicao
        atualizadas.append(c)
    return atualizadas


def calcular_media_80_maiores(competencias: List[Competencia], data_ref: str) -> ResultadoMedia:
    """
    Regra pré-Lei 9.876/1999: 80% maiores contribuições desde jul/1994.
    """
    validas = _filtrar_desde_julho_1994(competencias)
    validas = _garantir_atualizacao(validas, data_ref)

    valores = sorted(
        [c.remuneracao_atualizada or c.base_contribuicao for c in validas],
        reverse=True,
    )
    n_considerar = max(1, round(len(valores) * 0.80))
    considerados = valores[:n_considerar]

    soma = sum(considerados, Decimal("0"))
    media = (soma / len(considerados)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if considerados else Decimal("0")

    return ResultadoMedia(
        media=media,
        total_competencias=len(validas),
        competencias_consideradas=len(considerados),
        competencias_descartadas=len(valores) - len(considerados),
        soma_contribuicoes=soma,
        menor_valor=min(considerados) if considerados else Decimal("0"),
        maior_valor=max(considerados) if considerados else Decimal("0"),
        data_referencia=data_ref,
        regra_aplicada="80% maiores contribuições desde jul/1994",
    )


def calcular_media_100(competencias: List[Competencia], data_ref: str) -> ResultadoMedia:
    """
    Regra pós EC 103: 100% das contribuições desde jul/1994.
    """
    validas = _filtrar_desde_julho_1994(competencias)
    validas = _garantir_atualizacao(validas, data_ref)

    valores = [c.remuneracao_atualizada or c.base_contribuicao for c in validas]
    soma = sum(valores, Decimal("0"))
    media = (soma / len(valores)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if valores else Decimal("0")

    return ResultadoMedia(
        media=media,
        total_competencias=len(validas),
        competencias_consideradas=len(valores),
        competencias_descartadas=0,
        soma_contribuicoes=soma,
        menor_valor=min(valores) if valores else Decimal("0"),
        maior_valor=max(valores) if valores else Decimal("0"),
        data_referencia=data_ref,
        regra_aplicada="100% das contribuições desde jul/1994 (EC 103/2019)",
    )


def calcular_media(competencias: List[Competencia], regra: str, data_ref: str) -> ResultadoMedia:
    """
    Ponto de entrada. regra pode ser '80_maiores' ou '100'.
    """
    if regra == "80_maiores":
        return calcular_media_80_maiores(competencias, data_ref)
    return calcular_media_100(competencias, data_ref)
