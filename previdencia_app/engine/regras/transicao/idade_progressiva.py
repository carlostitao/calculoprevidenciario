"""Regra de idade mínima progressiva (Art. 16 EC 103/2019)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from ....models import Competencia
from ....models.caso import Caso, Sexo
from ...periodos import calcular_tempo_contributivo
from ..media_contribuicoes import calcular_media_100


def _idade_minima(sexo: Sexo, ano_req: int) -> int:
    """
    Homens: 65 anos (estável).
    Mulheres: 56 (2019) → 62 (2031+), +0.5 ano/ano.
    """
    if sexo == Sexo.MASCULINO:
        return 65
    acrescimo_semestres = max(0, ano_req - 2019)
    anos_acrescidos = acrescimo_semestres * 0.5
    return min(62, int(56 + anos_acrescidos))


def _tempo_minimo_meses(sexo: Sexo) -> int:
    return 35 * 12 if sexo == Sexo.MASCULINO else 30 * 12


def verificar_elegibilidade(caso: Caso, competencias: List[Competencia], data_req: date) -> tuple[bool, str]:
    tempo = calcular_tempo_contributivo(competencias)
    min_meses = _tempo_minimo_meses(caso.sexo)

    if tempo.total_meses < min_meses:
        return False, f"Tempo insuficiente: faltam {min_meses - tempo.total_meses} meses"

    idade_anos = (data_req - caso.data_nascimento).days / 365.25
    minima = _idade_minima(caso.sexo, data_req.year)

    if idade_anos < minima:
        return False, f"Idade insuficiente: {idade_anos:.1f} anos (mínimo {minima})"

    return True, ""


def calcular(caso: Caso, competencias: List[Competencia], data_req: date) -> dict:
    elegivel, motivo = verificar_elegibilidade(caso, competencias, data_req)
    tempo = calcular_tempo_contributivo(competencias)
    data_ref = data_req.strftime("%m/%Y")
    media_result = calcular_media_100(competencias, data_ref)

    anos_tc = Decimal(str(tempo.total_meses)) / 12
    anos_min = 35 if caso.sexo == Sexo.MASCULINO else 30
    excedente = max(Decimal("0"), anos_tc - Decimal(str(anos_min)))
    coeficiente = min(Decimal("1.0"), Decimal("0.60") + excedente * Decimal("0.02"))
    rmi = (media_result.media * coeficiente).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "regra": "Idade Mínima Progressiva (Art. 16 EC 103/2019)",
        "elegivel": elegivel,
        "motivo_inelegibilidade": motivo if not elegivel else None,
        "tempo_contributivo": tempo,
        "media_contribuicoes": media_result.media,
        "fator_previdenciario": None,
        "salario_beneficio": media_result.media,
        "coeficiente": coeficiente,
        "rmi": rmi,
        "detalhamento": {
            "idade_minima_necessaria": _idade_minima(caso.sexo, data_req.year),
            "anos_tc": float(anos_tc),
            "coeficiente_pct": float(coeficiente * 100),
        },
    }
