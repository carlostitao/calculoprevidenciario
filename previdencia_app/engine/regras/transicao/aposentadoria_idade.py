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
    """Mulheres: 60 (2020) → 62 (2023+), +1 a cada ano. Homens: 65 estável."""
    if sexo == Sexo.MASCULINO:
        return 65
    tabela = {2020: 60, 2021: 61, 2022: 61, 2023: 62}
    return tabela.get(ano_req, 62 if ano_req >= 2023 else 60)


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
            "carencia_necessaria_meses": _CARENCIA_MESES,
            "carencia_apurada_meses": tempo.total_meses,
            "coeficiente_pct": float(coeficiente * 100),
            "tempo_contributivo": detalhe_tempo(tempo),
        },
    }
