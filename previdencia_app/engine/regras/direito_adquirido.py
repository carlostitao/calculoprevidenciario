"""Direito adquirido — quem implementou requisitos até 13/11/2019."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from ...models import Competencia
from ...models.caso import Caso, Sexo
from ..periodos import calcular_tempo_contributivo
from .media_contribuicoes import calcular_media_80_maiores
from .fator_previdenciario import calcular_fator_previdenciario
from ._helpers import detalhe_tempo

_REFORMA = date(2019, 11, 13)
_TEMPO_MIN_H = 35 * 12
_TEMPO_MIN_M = 30 * 12


def _competencias_ate_reforma(competencias: List[Competencia]) -> List[Competencia]:
    def _yyyymm(c: Competencia) -> int:
        m, a = c.competencia.split("/")
        return int(a) * 100 + int(m)
    limite = _REFORMA.year * 100 + _REFORMA.month
    return [c for c in competencias if _yyyymm(c) <= limite]


def verificar_elegibilidade(caso: Caso, competencias: List[Competencia], data_req: date) -> tuple[bool, str]:
    comp_ate_reforma = _competencias_ate_reforma(competencias)
    tempo = calcular_tempo_contributivo(comp_ate_reforma)
    min_meses = _TEMPO_MIN_H if caso.sexo == Sexo.MASCULINO else _TEMPO_MIN_M

    if tempo.total_meses >= min_meses:
        return True, ""
    return False, f"Não possuía tempo mínimo em 13/11/2019 (tinha {tempo.total_meses}/{min_meses} meses)"


def calcular(caso: Caso, competencias: List[Competencia], data_req: date) -> dict:
    elegivel, motivo = verificar_elegibilidade(caso, competencias, data_req)
    comp_ate_reforma = _competencias_ate_reforma(competencias)
    tempo = calcular_tempo_contributivo(comp_ate_reforma)

    data_ref = _REFORMA.strftime("%m/%Y")  # média calculada até a data da reforma
    media_result = calcular_media_80_maiores(comp_ate_reforma, data_ref)

    anos_tc = Decimal(str(tempo.total_meses)) / 12
    idade_na_reforma = Decimal(str(
        (_REFORMA - caso.data_nascimento).days / 365.25
    ))
    fator_result = calcular_fator_previdenciario(anos_tc, idade_na_reforma)

    # Aplica fator somente se diminui o benefício (favorável ao segurado: ignorar fator < 1)
    fator_aplicavel = fator_result.fator if fator_result.fator >= Decimal("1") else Decimal("1")
    salario_beneficio = (media_result.media * fator_aplicavel).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    anos_min = 35 if caso.sexo == Sexo.MASCULINO else 30
    excedente = max(Decimal("0"), anos_tc - Decimal(str(anos_min)))
    coeficiente = min(Decimal("1.0"), Decimal("0.60") + excedente * Decimal("0.02"))
    rmi = (salario_beneficio * coeficiente).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "regra": "Direito Adquirido (implementado até 13/11/2019)",
        "elegivel": elegivel,
        "motivo_inelegibilidade": motivo if not elegivel else None,
        "tempo_contributivo": tempo,
        "media_contribuicoes": media_result.media,
        "fator_previdenciario": fator_result.fator,
        "salario_beneficio": salario_beneficio,
        "coeficiente": coeficiente,
        "rmi": rmi,
        "detalhamento": {
            "fator_formula": fator_result.formula_detalhada,
            "fator_aplicado": str(fator_aplicavel),
            "nota": "Fator previdenciário ignorado se < 1 (interpretação mais favorável ao segurado)",
            "media_regra": media_result.regra_aplicada,
            "tempo_contributivo": detalhe_tempo(tempo),
        },
    }
