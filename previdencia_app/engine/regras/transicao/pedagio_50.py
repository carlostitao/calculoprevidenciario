"""Pedágio de 50% — Art. 17 EC 103/2019."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from ....models import Competencia
from ....models.caso import Caso, Sexo
from ...periodos import calcular_tempo_contributivo
from ..media_contribuicoes import calcular_media_100
from ..fator_previdenciario import calcular_fator_previdenciario
from .._helpers import detalhe_tempo

_REFORMA = date(2019, 11, 13)
_TEMPO_MIN_H = 35 * 12
_TEMPO_MIN_M = 30 * 12
# Janela: quem faltava MENOS de 2 anos em 13/11/2019
_JANELA_MESES = 24


def _competencias_ate_reforma(competencias: List[Competencia]) -> List[Competencia]:
    def _yyyymm(c: Competencia) -> int:
        m, a = c.competencia.split("/")
        return int(a) * 100 + int(m)
    limite = _REFORMA.year * 100 + _REFORMA.month
    return [c for c in competencias if _yyyymm(c) <= limite]


def verificar_elegibilidade(caso: Caso, competencias: List[Competencia], data_req: date) -> tuple[bool, str]:
    tempo_na_reforma = calcular_tempo_contributivo(_competencias_ate_reforma(competencias))
    min_meses = _TEMPO_MIN_H if caso.sexo == Sexo.MASCULINO else _TEMPO_MIN_M
    faltavam = min_meses - tempo_na_reforma.total_meses

    if faltavam <= 0:
        return False, "Já possuía tempo mínimo em 13/11/2019 — não se enquadra no pedágio 50%"
    if faltavam > _JANELA_MESES:
        return False, f"Faltavam {faltavam} meses em 13/11/2019 (limite da regra: {_JANELA_MESES} meses)"

    # Com pedágio de 50%: precisa cumprir faltavam + 50% a mais
    pedagio = max(1, faltavam // 2)
    total_necessario = min_meses + pedagio
    tempo_atual = calcular_tempo_contributivo(competencias)

    if tempo_atual.total_meses < total_necessario:
        faltam_agora = total_necessario - tempo_atual.total_meses
        return False, f"Falta cumprir o pedágio: {faltam_agora} meses ainda necessários"

    return True, ""


def calcular(caso: Caso, competencias: List[Competencia], data_req: date) -> dict:
    elegivel, motivo = verificar_elegibilidade(caso, competencias, data_req)

    tempo_na_reforma = calcular_tempo_contributivo(_competencias_ate_reforma(competencias))
    min_meses = _TEMPO_MIN_H if caso.sexo == Sexo.MASCULINO else _TEMPO_MIN_M
    faltavam = max(0, min_meses - tempo_na_reforma.total_meses)
    pedagio = max(1, faltavam // 2) if faltavam > 0 else 0

    tempo_atual = calcular_tempo_contributivo(competencias)
    data_ref = data_req.strftime("%m/%Y")
    media_result = calcular_media_100(competencias, data_ref)

    anos_tc = Decimal(str(tempo_atual.total_meses)) / 12
    idade = Decimal(str((data_req - caso.data_nascimento).days / 365.25))

    fator_result = calcular_fator_previdenciario(anos_tc, idade)

    # Fator previdenciário obrigatório no pedágio 50%
    salario_beneficio = (media_result.media * fator_result.fator).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    anos_min = 35 if caso.sexo == Sexo.MASCULINO else 30
    excedente = max(Decimal("0"), anos_tc - Decimal(str(anos_min)))
    coeficiente = min(Decimal("1.0"), Decimal("0.60") + excedente * Decimal("0.02"))
    rmi = (salario_beneficio * coeficiente).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "regra": "Pedágio 50% (Art. 17 EC 103/2019)",
        "elegivel": elegivel,
        "motivo_inelegibilidade": motivo if not elegivel else None,
        "tempo_contributivo": tempo_atual,
        "media_contribuicoes": media_result.media,
        "fator_previdenciario": fator_result.fator,
        "salario_beneficio": salario_beneficio,
        "coeficiente": coeficiente,
        "rmi": rmi,
        "detalhamento": {
            "meses_faltavam_na_reforma": faltavam,
            "pedagio_meses": pedagio,
            "fator_formula": fator_result.formula_detalhada,
            "coeficiente_pct": float(coeficiente * 100),
            "tempo_contributivo": detalhe_tempo(tempo_atual),
        },
    }
