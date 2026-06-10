"""Aposentadoria por idade — transição (Art. 18 EC 103/2019) e regra geral."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from ....models import Competencia
from ....models.caso import Caso, Sexo
from ...periodos import calcular_tempo_contributivo
from ..media_contribuicoes import calcular_media_100
from .._helpers import detalhe_tempo


def _idade_minima_transicao(sexo: Sexo, ano_req: int) -> int:
    """
    Homens: 65 anos (estável).
    Mulheres — EC 103/2019 Art. 18: 60 (2020), 61 (2021), 62 (2022 em diante).
    """
    if sexo == Sexo.MASCULINO:
        return 65
    tabela = {2020: 60, 2021: 61}
    return tabela.get(ano_req, 62)


_CARENCIA_MESES = 15 * 12  # 180 meses


def verificar_elegibilidade(caso: Caso, competencias: List[Competencia], data_req: date) -> tuple[bool, str]:
    idade = (data_req - caso.data_nascimento).days / 365.25
    idade_min = _idade_minima_transicao(caso.sexo, data_req.year)

    if idade < idade_min:
        return False, f"Idade insuficiente: {idade:.1f} (mínimo {idade_min})"

    tempo = calcular_tempo_contributivo(competencias)
    if tempo.total_meses < _CARENCIA_MESES:
        return False, f"Carência insuficiente: {tempo.total_meses}/{_CARENCIA_MESES} meses"

    return True, ""


def calcular(caso: Caso, competencias: List[Competencia], data_req: date) -> dict:
    elegivel, motivo = verificar_elegibilidade(caso, competencias, data_req)
    tempo = calcular_tempo_contributivo(competencias)
    data_ref = data_req.strftime("%m/%Y")
    media_result = calcular_media_100(competencias, data_ref)

    # Coeficiente: 60% + 2% por ano excedente a 15 anos de carência
    anos_contrib = Decimal(str(tempo.total_meses)) / 12
    excedente = max(Decimal("0"), anos_contrib - Decimal("15"))
    coeficiente = min(Decimal("1.0"), Decimal("0.60") + excedente * Decimal("0.02"))
    rmi = (media_result.media * coeficiente).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "regra": "Aposentadoria por Idade (Art. 18 EC 103/2019)",
        "elegivel": elegivel,
        "motivo_inelegibilidade": motivo if not elegivel else None,
        "tempo_contributivo": tempo,
        "media_contribuicoes": media_result.media,
        "fator_previdenciario": None,
        "salario_beneficio": media_result.media,
        "coeficiente": coeficiente,
        "rmi": rmi,
        "detalhamento": {
            "idade_minima_necessaria": f"{_idade_minima_transicao(caso.sexo, data_req.year)} anos",
            "carencia_necessaria_anos": 15,
            "carencia_apurada_anos": float(anos_contrib),
            "tc_para_100pct": 35.0,  # 15 + 20 anos extras para atingir 100%
            "coeficiente_pct": float(coeficiente * 100),
            "tempo_contributivo": detalhe_tempo(tempo),
        },
    }
