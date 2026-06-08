"""Pedágio de 100% — Art. 20 EC 103/2019."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from ....models import Competencia
from ....models.caso import Caso, Sexo
from ...periodos import calcular_tempo_contributivo
from ..media_contribuicoes import calcular_media_100
from .._helpers import detalhe_tempo

_REFORMA = date(2019, 11, 13)
_TEMPO_MIN_H = 35 * 12
_TEMPO_MIN_M = 30 * 12
_IDADE_MIN_H = 60
_IDADE_MIN_M = 57


def _competencias_ate_reforma(competencias: List[Competencia]) -> List[Competencia]:
    def _yyyymm(c: Competencia) -> int:
        m, a = c.competencia.split("/")
        return int(a) * 100 + int(m)
    limite = _REFORMA.year * 100 + _REFORMA.month
    return [c for c in competencias if _yyyymm(c) <= limite]


def verificar_elegibilidade(caso: Caso, competencias: List[Competencia], data_req: date) -> tuple[bool, str]:
    idade = (data_req - caso.data_nascimento).days / 365.25
    idade_min = _IDADE_MIN_H if caso.sexo == Sexo.MASCULINO else _IDADE_MIN_M

    if idade < idade_min:
        return False, f"Idade insuficiente: {idade:.1f} anos (mínimo {idade_min})"

    tempo_na_reforma = calcular_tempo_contributivo(_competencias_ate_reforma(competencias))
    min_meses = _TEMPO_MIN_H if caso.sexo == Sexo.MASCULINO else _TEMPO_MIN_M
    faltavam = max(0, min_meses - tempo_na_reforma.total_meses)

    if faltavam == 0:
        return False, "Já possuía tempo mínimo em 13/11/2019 — use outra regra"

    # Pedágio = 100% do que faltava
    total_necessario = min_meses + faltavam
    tempo_atual = calcular_tempo_contributivo(competencias)

    if tempo_atual.total_meses < total_necessario:
        return False, f"Pedágio incompleto: faltam {total_necessario - tempo_atual.total_meses} meses"

    return True, ""


def calcular(caso: Caso, competencias: List[Competencia], data_req: date) -> dict:
    elegivel, motivo = verificar_elegibilidade(caso, competencias, data_req)

    tempo_na_reforma = calcular_tempo_contributivo(_competencias_ate_reforma(competencias))
    min_meses = _TEMPO_MIN_H if caso.sexo == Sexo.MASCULINO else _TEMPO_MIN_M
    faltavam = max(0, min_meses - tempo_na_reforma.total_meses)

    tempo_atual = calcular_tempo_contributivo(competencias)
    data_ref = data_req.strftime("%m/%Y")
    media_result = calcular_media_100(competencias, data_ref)

    anos_tc = Decimal(str(tempo_atual.total_meses)) / 12
    anos_min = 35 if caso.sexo == Sexo.MASCULINO else 30
    excedente = max(Decimal("0"), anos_tc - Decimal(str(anos_min)))
    coeficiente = min(Decimal("1.0"), Decimal("0.60") + excedente * Decimal("0.02"))
    rmi = (media_result.media * coeficiente).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "regra": "Pedágio 100% (Art. 20 EC 103/2019)",
        "elegivel": elegivel,
        "motivo_inelegibilidade": motivo if not elegivel else None,
        "tempo_contributivo": tempo_atual,
        "media_contribuicoes": media_result.media,
        "fator_previdenciario": None,
        "salario_beneficio": media_result.media,
        "coeficiente": coeficiente,
        "rmi": rmi,
        "detalhamento": {
            "meses_faltavam_na_reforma": faltavam,
            "pedagio_meses": faltavam,
            "coeficiente_pct": float(coeficiente * 100),
            "tempo_contributivo": detalhe_tempo(tempo_atual),
        },
    }
