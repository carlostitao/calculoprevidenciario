"""Cálculo da média dos salários de contribuição."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from ...models import Competencia
from ..correcao_monetaria import atualizar_inpc

logger = logging.getLogger(__name__)

_INICIO_PERIODO = "07/1994"


# Tabela histórica do teto do RGPS (MM/YYYY → valor em R$).
# Vigente a partir do mês indicado até a próxima entrada.
# Fontes: legislação previdenciária e portarias MPS/MF.
_TETO_HISTORICO: List[tuple] = [
    ("07/1994", Decimal("636.36")),
    ("03/1995", Decimal("672.29")),
    ("05/1995", Decimal("713.28")),
    ("05/1996", Decimal("957.56")),
    ("05/1997", Decimal("1031.87")),
    ("06/1998", Decimal("1081.50")),
    ("05/1999", Decimal("1255.32")),
    ("06/1999", Decimal("1328.25")),
    ("04/2000", Decimal("1328.25")),
    ("06/2000", Decimal("1430.88")),
    ("06/2001", Decimal("1430.88")),
    ("01/2002", Decimal("1561.56")),
    ("06/2002", Decimal("1561.56")),
    ("01/2003", Decimal("1869.34")),
    ("04/2003", Decimal("1869.34")),
    ("01/2004", Decimal("2400.00")),
    ("05/2004", Decimal("2400.00")),
    ("04/2005", Decimal("2508.72")),
    ("04/2006", Decimal("2801.82")),
    ("04/2007", Decimal("2894.28")),
    ("03/2008", Decimal("3038.99")),
    ("02/2009", Decimal("3218.90")),
    ("01/2010", Decimal("3416.54")),
    ("01/2011", Decimal("3691.74")),
    ("01/2012", Decimal("3916.20")),
    ("01/2013", Decimal("4159.00")),
    ("01/2014", Decimal("4390.24")),
    ("01/2015", Decimal("4663.75")),
    ("01/2016", Decimal("5189.82")),
    ("01/2017", Decimal("5531.31")),
    ("01/2018", Decimal("5645.80")),
    ("01/2019", Decimal("5839.45")),
    ("01/2020", Decimal("6101.06")),
    ("01/2021", Decimal("6433.57")),
    ("01/2022", Decimal("7087.22")),
    ("01/2023", Decimal("7507.49")),
    ("01/2024", Decimal("7786.02")),
    ("01/2025", Decimal("8157.41")),
    ("01/2026", Decimal("8475.55")),
]

# Tabela histórica do salário mínimo (MM/YYYY → valor em R$).
# MEI: base_contribuicao = salário mínimo vigente na competência.
_SALARIO_MINIMO_HISTORICO: List[tuple] = [
    ("01/2009", Decimal("465.00")),
    ("01/2010", Decimal("510.00")),
    ("03/2011", Decimal("545.00")),
    ("01/2012", Decimal("622.00")),
    ("01/2013", Decimal("678.00")),
    ("01/2014", Decimal("724.00")),
    ("01/2015", Decimal("788.00")),
    ("01/2016", Decimal("880.00")),
    ("01/2017", Decimal("937.00")),
    ("01/2018", Decimal("954.00")),
    ("01/2019", Decimal("998.00")),
    ("01/2020", Decimal("1039.00")),
    ("02/2020", Decimal("1045.00")),
    ("01/2021", Decimal("1100.00")),
    ("01/2022", Decimal("1212.00")),
    ("01/2023", Decimal("1302.00")),
    ("05/2023", Decimal("1320.00")),
    ("01/2024", Decimal("1412.00")),
    ("01/2025", Decimal("1518.00")),
    ("01/2026", Decimal("1622.00")),
]


def salario_minimo_para_competencia(competencia: str) -> Decimal:
    """Retorna o salário mínimo vigente para a competência informada (MM/YYYY)."""
    chave = _comp_key(competencia)
    sm_vigente = Decimal("465.00")  # valor base MEI (jan/2009)
    for comp_inicio, valor in sorted(_SALARIO_MINIMO_HISTORICO, key=lambda t: _comp_key(t[0])):
        if _comp_key(comp_inicio) <= chave:
            sm_vigente = valor
        else:
            break
    return sm_vigente


# Cache: MM/YYYY → teto como Decimal
_teto_cache: Dict[str, Decimal] = {}


def _comp_key(comp: str) -> int:
    try:
        m, a = comp.split("/")
        return int(a) * 100 + int(m)
    except (ValueError, AttributeError):
        return 0


def _construir_cache_teto() -> None:
    global _teto_cache
    if _teto_cache:
        return
    # Converte lista ordenada em lookup rápido por competência
    # Para qualquer competência, o teto é o da última entrada <= à competência
    sorted_entries = sorted(_TETO_HISTORICO, key=lambda t: _comp_key(t[0]))
    for i, (comp_inicio, valor) in enumerate(sorted_entries):
        _teto_cache[comp_inicio] = valor


def teto_para_competencia(competencia: str) -> Decimal:
    """Retorna o teto previdenciário vigente para a competência informada."""
    _construir_cache_teto()
    chave = _comp_key(competencia)
    teto_vigente = Decimal("636.36")  # valor mínimo histórico (jul/1994)
    for comp_inicio, valor in sorted(_TETO_HISTORICO, key=lambda t: _comp_key(t[0])):
        if _comp_key(comp_inicio) <= chave:
            teto_vigente = valor
        else:
            break
    return teto_vigente


def _cap_teto(valor: Decimal, competencia: str) -> Decimal:
    """Limita o valor ao teto previdenciário da competência."""
    teto = teto_para_competencia(competencia)
    return min(valor, teto)


def _agrupar_concomitantes(competencias: List[Competencia]) -> List[Competencia]:
    """
    Agrupa competências do mesmo mês de fontes diferentes (concomitância).
    Regra (Lei 13.846/2019 + STJ): soma dos salários de contribuição,
    limitada ao teto da competência. O tempo conta apenas uma vez.
    """
    por_competencia: Dict[str, List[Competencia]] = {}
    for c in competencias:
        por_competencia.setdefault(c.competencia, []).append(c)

    resultado: List[Competencia] = []
    for comp, grupo in por_competencia.items():
        if len(grupo) == 1:
            resultado.append(grupo[0])
            continue

        # Soma as bases de contribuição
        soma = sum((c.base_contribuicao for c in grupo), Decimal("0"))
        soma_limitada = _cap_teto(soma, comp)

        # Usa o primeiro registro como representante e ajusta a base
        principal = grupo[0]
        principal.base_contribuicao = soma_limitada
        principal.remuneracao_atualizada = None  # força recálculo INPC com valor somado
        logger.debug(
            "[CONCOMITANTE] %s: %d fontes, soma=%.2f, cap_teto=%.2f (teto=%.2f)",
            comp, len(grupo), soma, soma_limitada, teto_para_competencia(comp),
        )
        resultado.append(principal)

    return resultado


@dataclass
class ResultadoMedia:
    media: Decimal
    total_competencias: int
    competencias_consideradas: int
    competencias_descartadas: int
    soma_contribuicoes: Decimal
    menor_valor: Decimal
    maior_valor: Decimal
    data_referencia: str
    regra_aplicada: str


def _filtrar_desde_julho_1994(competencias: List[Competencia]) -> List[Competencia]:
    return [c for c in competencias if _comp_key(c.competencia) >= 199407]


def _garantir_atualizacao(competencias: List[Competencia], data_ref: str) -> List[Competencia]:
    """
    Para cada competência:
    1. Aplica cap do teto antes da correção
    2. Atualiza pelo INPC até data_ref
    """
    atualizadas = []
    for c in competencias:
        # Cap no teto da competência antes de corrigir
        base_capada = _cap_teto(c.base_contribuicao, c.competencia)
        if base_capada != c.base_contribuicao:
            logger.debug("[TETO] %s: %.2f → %.2f (teto=%.2f)",
                         c.competencia, c.base_contribuicao, base_capada,
                         teto_para_competencia(c.competencia))
            c.base_contribuicao = base_capada
            c.remuneracao_atualizada = None  # recalcular com valor correto

        if c.remuneracao_atualizada is None:
            try:
                c.remuneracao_atualizada = atualizar_inpc(c.base_contribuicao, c.competencia, data_ref)
            except Exception as exc:
                logger.warning("[INPC] Sem fator para %s (%s) — usando valor nominal",
                               c.competencia, exc)
                c.remuneracao_atualizada = c.base_contribuicao

        atualizadas.append(c)
    return atualizadas


def calcular_media_80_maiores(competencias: List[Competencia], data_ref: str) -> ResultadoMedia:
    """Regra pré-Lei 9.876/1999: 80% maiores contribuições desde jul/1994."""
    validas = _filtrar_desde_julho_1994(competencias)
    validas = _agrupar_concomitantes(validas)
    validas = _garantir_atualizacao(validas, data_ref)

    valores = sorted(
        [c.remuneracao_atualizada or c.base_contribuicao for c in validas],
        reverse=True,
    )
    n_considerar = max(1, round(len(valores) * 0.80))
    considerados = valores[:n_considerar]

    soma = sum(considerados, Decimal("0"))
    media = (soma / len(considerados)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if considerados else Decimal("0")

    return ResultadoMedia(
        media=media,
        total_competencias=len(validas),
        competencias_consideradas=len(considerados),
        competencias_descartadas=len(valores) - len(considerados),
        soma_contribuicoes=soma,
        menor_valor=min(considerados) if considerados else Decimal("0"),
        maior_valor=max(considerados) if considerados else Decimal("0"),
        data_referencia=data_ref,
        regra_aplicada="80% maiores contribuições desde jul/1994",
    )


def calcular_media_100(competencias: List[Competencia], data_ref: str) -> ResultadoMedia:
    """Regra pós EC 103: 100% das contribuições desde jul/1994."""
    validas = _filtrar_desde_julho_1994(competencias)
    validas = _agrupar_concomitantes(validas)
    validas = _garantir_atualizacao(validas, data_ref)

    valores = [c.remuneracao_atualizada or c.base_contribuicao for c in validas]
    soma = sum(valores, Decimal("0"))
    media = (soma / len(valores)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if valores else Decimal("0")

    return ResultadoMedia(
        media=media,
        total_competencias=len(validas),
        competencias_consideradas=len(valores),
        competencias_descartadas=0,
        soma_contribuicoes=soma,
        menor_valor=min(valores) if valores else Decimal("0"),
        maior_valor=max(valores) if valores else Decimal("0"),
        data_referencia=data_ref,
        regra_aplicada="100% das contribuições desde jul/1994 (EC 103/2019)",
    )


def calcular_media(competencias: List[Competencia], regra: str, data_ref: str) -> ResultadoMedia:
    if regra == "80_maiores":
        return calcular_media_80_maiores(competencias, data_ref)
    return calcular_media_100(competencias, data_ref)
