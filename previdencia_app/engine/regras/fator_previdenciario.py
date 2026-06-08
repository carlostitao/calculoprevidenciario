"""Cálculo do fator previdenciário conforme fórmula legal."""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

# Tabela de expectativa de sobrevida IBGE (2023 — atualizar anualmente)
# Fonte: IBGE Tábua Completa de Mortalidade 2023
# Formato: idade_inteira -> expectativa_em_anos
EXPECTATIVA_SOBREVIDA_IBGE_2023: dict[int, float] = {
    0: 75.5, 1: 75.4, 2: 74.5, 3: 73.5, 4: 72.6,
    5: 71.6, 10: 66.7, 15: 61.8, 20: 57.0, 25: 52.3,
    30: 47.7, 35: 43.1, 40: 38.6, 41: 37.7, 42: 36.8,
    43: 35.9, 44: 35.1, 45: 34.2, 46: 33.4, 47: 32.5,
    48: 31.7, 49: 30.9, 50: 30.1, 51: 29.3, 52: 28.5,
    53: 27.7, 54: 26.9, 55: 26.2, 56: 25.4, 57: 24.7,
    58: 24.0, 59: 23.3, 60: 22.6, 61: 21.9, 62: 21.2,
    63: 20.6, 64: 19.9, 65: 19.3, 66: 18.7, 67: 18.1,
    68: 17.5, 69: 16.9, 70: 16.3, 71: 15.8, 72: 15.2,
    73: 14.7, 74: 14.2, 75: 13.7, 80: 11.0, 85: 8.7,
    90: 6.8,
}

_ALIQUOTA = Decimal("0.31")


@dataclass
class ResultadoFator:
    fator: Decimal
    tempo_contribuicao_anos: Decimal
    idade_anos: Decimal
    expectativa_sobrevida: Decimal
    formula_detalhada: str


def obter_expectativa_sobrevida(idade: int, tabela: Optional[dict] = None) -> float:
    """Interpola linearmente para idades não presentes na tabela."""
    tab = tabela or EXPECTATIVA_SOBREVIDA_IBGE_2023
    if idade in tab:
        return tab[idade]
    # Interpolação linear entre os extremos mais próximos
    idades_ord = sorted(tab.keys())
    menor = max((i for i in idades_ord if i <= idade), default=idades_ord[0])
    maior = min((i for i in idades_ord if i >= idade), default=idades_ord[-1])
    if menor == maior:
        return tab[menor]
    frac = (idade - menor) / (maior - menor)
    return tab[menor] + frac * (tab[maior] - tab[menor])


def calcular_fator_previdenciario(
    tempo_contribuicao_anos: Decimal,
    idade_anos: Decimal,
    tabela_sobrevida: Optional[dict] = None,
) -> ResultadoFator:
    """
    f = (Tc × a / Es) × (1 + (Id + Tc × a) / 100)
    """
    tc = float(tempo_contribuicao_anos)
    id_ = float(idade_anos)
    aliq = float(_ALIQUOTA)
    es = obter_expectativa_sobrevida(int(id_), tabela_sobrevida)

    if es <= 0:
        raise ValueError(f"Expectativa de sobrevida inválida: {es}")

    fator = (tc * aliq / es) * (1 + (id_ + tc * aliq) / 100)
    fator_dec = Decimal(str(round(fator, 4)))

    return ResultadoFator(
        fator=fator_dec,
        tempo_contribuicao_anos=tempo_contribuicao_anos,
        idade_anos=idade_anos,
        expectativa_sobrevida=Decimal(str(round(es, 1))),
        formula_detalhada=(
            f"f = ({tc:.2f} × {aliq} / {es:.1f}) × "
            f"(1 + ({id_:.2f} + {tc:.2f} × {aliq}) / 100) = {fator_dec}"
        ),
    )
