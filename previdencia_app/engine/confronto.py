"""Confronto de fontes — CNIS como fonte primária."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Set

from ..models import Competencia, FonteDocumento
from .periodos import Gap, listar_periodos_sem_contribuicao

logger = logging.getLogger(__name__)

_TOLERANCIA_DIVERGENCIA = Decimal("0.05")  # 5%


@dataclass
class DivergenciaValor:
    competencia: str
    empregador: str
    fonte_a: FonteDocumento
    valor_a: Decimal
    fonte_b: FonteDocumento
    valor_b: Decimal
    percentual_diferenca: Decimal


@dataclass
class Sobreposicao:
    competencia: str
    vinculo_a: str
    fonte_a: FonteDocumento
    vinculo_b: str
    fonte_b: FonteDocumento
    permitida: bool  # True = CLT + CI é permitido
    descricao: str


@dataclass
class ResultadoConfronto:
    competencias_apenas_cnis: List[str] = field(default_factory=list)
    competencias_apenas_fontes_externas: List[str] = field(default_factory=list)
    divergencias_valor: List[DivergenciaValor] = field(default_factory=list)
    sobreposicoes: List[Sobreposicao] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)
    pendencias_cnis: List[str] = field(default_factory=list)  # apenas informativo


# Combinações de vínculos simultâneos permitidas pelo RGPS
_SOBREPOSICOES_PERMITIDAS = {
    frozenset(["CLT", "AUTONOMO"]),
    frozenset(["CLT", "MEI"]),
    frozenset(["CLT", "FACULTATIVO"]),
    frozenset(["RPPS", "CLT"]),  # acumulação em casos específicos
}


def confrontar(caso_id: int, competencias: List[Competencia]) -> ResultadoConfronto:
    """
    Compara todas as competências do caso.
    CNIS é a fonte principal — desvios de outras fontes são alertas, não erros.
    """
    resultado = ResultadoConfronto()

    comp_cnis: Dict[str, List[Competencia]] = {}
    comp_externas: Dict[str, List[Competencia]] = {}
    pendentes: List[str] = []

    for c in competencias:
        if c.flag_pendencia_cnis:
            pendentes.append(c.competencia)
        if c.fonte == FonteDocumento.CNIS:
            comp_cnis.setdefault(c.competencia, []).append(c)
        else:
            comp_externas.setdefault(c.competencia, []).append(c)

    resultado.pendencias_cnis = sorted(set(pendentes))

    # Competências somente no CNIS
    resultado.competencias_apenas_cnis = sorted(
        set(comp_cnis.keys()) - set(comp_externas.keys())
    )

    # Competências em fontes externas, ausentes no CNIS
    resultado.competencias_apenas_fontes_externas = sorted(
        set(comp_externas.keys()) - set(comp_cnis.keys())
    )

    # Divergências de valor
    for comp, externas in comp_externas.items():
        if comp not in comp_cnis:
            continue
        cnis_ref = comp_cnis[comp][0]
        for ext in externas:
            if cnis_ref.base_contribuicao == Decimal("0"):
                continue
            diff = abs(cnis_ref.base_contribuicao - ext.base_contribuicao)
            pct = diff / cnis_ref.base_contribuicao
            if pct > _TOLERANCIA_DIVERGENCIA:
                resultado.divergencias_valor.append(DivergenciaValor(
                    competencia=comp,
                    empregador=cnis_ref.empregador_nome,
                    fonte_a=FonteDocumento.CNIS,
                    valor_a=cnis_ref.base_contribuicao,
                    fonte_b=ext.fonte,
                    valor_b=ext.base_contribuicao,
                    percentual_diferenca=pct * 100,
                ))

    # Sobreposições de vínculo (dois vínculos na mesma competência)
    todas_por_comp: Dict[str, List[Competencia]] = {}
    for c in competencias:
        todas_por_comp.setdefault(c.competencia, []).append(c)

    for comp, lista in todas_por_comp.items():
        if len(lista) < 2:
            continue
        vistos: List[Competencia] = []
        for c in lista:
            for outro in vistos:
                if c.empregador_nome == outro.empregador_nome:
                    continue  # mesmo empregador — não é sobreposição
                tipos = frozenset([c.tipo_vinculo.value, outro.tipo_vinculo.value])
                permitida = tipos in _SOBREPOSICOES_PERMITIDAS
                resultado.sobreposicoes.append(Sobreposicao(
                    competencia=comp,
                    vinculo_a=c.empregador_nome,
                    fonte_a=c.fonte,
                    vinculo_b=outro.empregador_nome,
                    fonte_b=outro.fonte,
                    permitida=permitida,
                    descricao=(
                        "Sobreposição permitida (CLT + CI/MEI/Facultativo)"
                        if permitida else
                        "Sobreposição possivelmente indevida — verificar"
                    ),
                ))
            vistos.append(c)

    # Gaps
    resultado.gaps = listar_periodos_sem_contribuicao(competencias)

    return resultado
