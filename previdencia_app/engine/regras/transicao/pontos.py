"""Regra de pontos progressivos (Art. 15 EC 103/2019)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from ....models import Competencia
from ....models.caso import Caso, Sexo
from ...periodos import calcular_tempo_contributivo
from ..media_contribuicoes import calcular_media_100
from ..fator_previdenciario import calcular_fator_previdenciario


# Pontos mínimos por ano (2019-2033 e posteriores)
# Homens: 96 → 105 (limite), +1/ano a partir de 2020
# Mulheres: 86 → 100 (limite), +1/ano a partir de 2020
def _pontos_minimos(sexo: Sexo, ano_requerimento: int) -> int:
    if sexo == Sexo.MASCULINO:
        base, limite = 96, 105
    else:
        base, limite = 86, 100
    acrescimo = max(0, ano_requerimento - 2019)
    return min(base + acrescimo, limite)


def _tempo_minimo_meses(sexo: Sexo) -> int:
    return 35 * 12 if sexo == Sexo.MASCULINO else 30 * 12


def verificar_elegibilidade(caso: Caso, competencias: List[Competencia], data_req: date) -> tuple[bool, str]:
    tempo = calcular_tempo_contributivo(competencias)
    min_meses = _tempo_minimo_meses(caso.sexo)

    if tempo.total_meses < min_meses:
        faltam = min_meses - tempo.total_meses
        return False, f"Tempo insuficiente: faltam {faltam} meses"

    anos_tc = Decimal(str(tempo.total_meses / 12))
    idade = Decimal(str(
        (data_req - caso.data_nascimento).days / 365.25
    ))
    pontos = int(anos_tc + idade)
    minimos = _pontos_minimos(caso.sexo, data_req.year)

    if pontos < minimos:
        return False, f"Pontuação insuficiente: {pontos}/{minimos} pontos"

    return True, ""


def calcular(caso: Caso, competencias: List[Competencia], data_req: date) -> dict:
    elegivel, motivo = verificar_elegibilidade(caso, competencias, data_req)
    tempo = calcular_tempo_contributivo(competencias)
    data_ref = data_req.strftime("%m/%Y")

    media_result = calcular_media_100(competencias, data_ref)
    anos_tc = Decimal(str(tempo.total_meses)) / 12
    idade = Decimal(str((data_req - caso.data_nascimento).days / 365.25))
    pontos = int(anos_tc + idade)
    minimos = _pontos_minimos(caso.sexo, data_req.year)

    # Coeficiente: 60% + 2% por ano excedente ao mínimo
    anos_min = 35 if caso.sexo == Sexo.MASCULINO else 30
    excedente = max(Decimal("0"), anos_tc - Decimal(str(anos_min)))
    coeficiente = min(Decimal("1.0"), Decimal("0.60") + excedente * Decimal("0.02"))

    rmi = (media_result.media * coeficiente).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "regra": "Regra de Pontos (Art. 15 EC 103/2019)",
        "elegivel": elegivel,
        "motivo_inelegibilidade": motivo if not elegivel else None,
        "tempo_contributivo": tempo,
        "media_contribuicoes": media_result.media,
        "fator_previdenciario": None,  # regra de pontos não aplica fator
        "salario_beneficio": media_result.media,
        "coeficiente": coeficiente,
        "rmi": rmi,
        "detalhamento": {
            "pontos_obtidos": pontos,
            "pontos_minimos": minimos,
            "anos_tc": float(anos_tc),
            "idade": float(idade),
            "coeficiente_pct": float(coeficiente * 100),
            "media_result": {
                "media": str(media_result.media),
                "competencias_consideradas": media_result.competencias_consideradas,
                "regra": media_result.regra_aplicada,
            },
        },
    }
