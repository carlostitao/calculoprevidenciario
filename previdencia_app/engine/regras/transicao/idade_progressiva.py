"""Regra de idade mínima progressiva (Art. 16 EC 103/2019)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from ....models import Competencia
from ....models.caso import Caso, Sexo
from ...periodos import calcular_tempo_contributivo
from ..media_contribuicoes import calcular_media_100
from .._helpers import detalhe_tempo


def _idade_minima(sexo: Sexo, ano_req: int) -> Decimal:
    """
    Homens: 65 anos (estável).
    Mulheres: EC 103 Art. 16 §1º — 56 em 2020, +6 meses a cada ano até 62 em 2032.
      2020=56, 2021=56.5, 2022=57, 2023=57.5 ... 2032+=62.
    Retorna Decimal para preservar os meios anos (ex: 57.5).
    """
    if sexo == Sexo.MASCULINO:
        return Decimal("65")
    # Base 2020 = 56 anos; +0.5 por ano a partir de 2021
    acrescimo = Decimal(str(max(0, ano_req - 2020))) * Decimal("0.5")
    return min(Decimal("62"), Decimal("56") + acrescimo)


def _tempo_minimo_meses(sexo: Sexo) -> int:
    return 35 * 12 if sexo == Sexo.MASCULINO else 30 * 12


def verificar_elegibilidade(caso: Caso, competencias: List[Competencia], data_req: date) -> tuple[bool, str]:
    tempo = calcular_tempo_contributivo(competencias)
    min_meses = _tempo_minimo_meses(caso.sexo)

    if tempo.total_meses < min_meses:
        return False, f"Tempo insuficiente: faltam {min_meses - tempo.total_meses} meses"

    idade_anos = Decimal(str(round((data_req - caso.data_nascimento).days / 365.25, 4)))
    minima = _idade_minima(caso.sexo, data_req.year)

    if idade_anos < minima:
        minima_fmt = f"{int(minima)} anos" if minima == int(minima) else f"{int(minima)} anos e 6 meses"
        return False, f"Idade insuficiente: {float(idade_anos):.1f} anos (mínimo {minima_fmt})"

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

    minima = _idade_minima(caso.sexo, data_req.year)
    minima_fmt = f"{int(minima)} anos" if minima == int(minima) else f"{int(minima)} anos e 6 meses"
    anos_para_100 = Decimal(str(anos_min)) + Decimal("20")  # 60%+2%×20 = 100%

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
            "idade_minima_necessaria": minima_fmt,
            "tc_minimo_anos": anos_min,
            "tc_apurado_anos": float(anos_tc),
            "tc_para_100pct": float(anos_para_100),
            "coeficiente_pct": float(coeficiente * 100),
            "tempo_contributivo": detalhe_tempo(tempo),
        },
    }
