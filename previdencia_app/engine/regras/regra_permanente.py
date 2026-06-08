"""Regra permanente pós EC 103/2019 — novos filiados."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from ...models import Competencia
from ...models.caso import Caso, Sexo
from ..periodos import calcular_tempo_contributivo
from .media_contribuicoes import calcular_media_100
from ._helpers import detalhe_tempo

# Regra permanente: 65H/62M + 20H/15M
_IDADES_MIN = {Sexo.MASCULINO: 65, Sexo.FEMININO: 62}
_TEMPO_MIN = {Sexo.MASCULINO: 20 * 12, Sexo.FEMININO: 15 * 12}


def verificar_elegibilidade(caso: Caso, competencias: List[Competencia], data_req: date) -> tuple[bool, str]:
    idade = (data_req - caso.data_nascimento).days / 365.25
    idade_min = _IDADES_MIN[caso.sexo]
    tempo = calcular_tempo_contributivo(competencias)
    min_meses = _TEMPO_MIN[caso.sexo]

    if idade < idade_min:
        return False, f"Idade insuficiente: {idade:.1f} anos (mínimo {idade_min})"
    if tempo.total_meses < min_meses:
        return False, f"Tempo insuficiente: {tempo.total_meses}/{min_meses} meses"
    return True, ""


def calcular(caso: Caso, competencias: List[Competencia], data_req: date) -> dict:
    elegivel, motivo = verificar_elegibilidade(caso, competencias, data_req)
    tempo = calcular_tempo_contributivo(competencias)
    data_ref = data_req.strftime("%m/%Y")
    media_result = calcular_media_100(competencias, data_ref)

    anos_tc = Decimal(str(tempo.total_meses)) / 12
    anos_min = 20 if caso.sexo == Sexo.MASCULINO else 15
    excedente = max(Decimal("0"), anos_tc - Decimal(str(anos_min)))
    coeficiente = min(Decimal("1.0"), Decimal("0.60") + excedente * Decimal("0.02"))
    rmi = (media_result.media * coeficiente).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "regra": "Regra Permanente (Art. 19 EC 103/2019)",
        "elegivel": elegivel,
        "motivo_inelegibilidade": motivo if not elegivel else None,
        "tempo_contributivo": tempo,
        "media_contribuicoes": media_result.media,
        "fator_previdenciario": None,
        "salario_beneficio": media_result.media,
        "coeficiente": coeficiente,
        "rmi": rmi,
        "detalhamento": {
            "coeficiente_pct": float(coeficiente * 100),
            "anos_minimos": anos_min,
            "tempo_contributivo": detalhe_tempo(tempo),
        },
    }
