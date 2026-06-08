"""Orquestrador do cálculo do salário de benefício."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional

from ...models import Competencia
from ...models.caso import Caso
from ..periodos import TempoPeriodo
from . import direito_adquirido, regra_permanente
from .transicao import pontos, idade_progressiva, pedagio_50, pedagio_100, aposentadoria_idade

logger = logging.getLogger(__name__)


@dataclass
class ResultadoCalculo:
    regra: str
    elegivel: bool
    motivo_inelegibilidade: Optional[str]
    tempo_contributivo: TempoPeriodo
    media_contribuicoes: Decimal
    fator_previdenciario: Optional[Decimal]
    salario_beneficio: Decimal
    coeficiente: Decimal
    rmi: Decimal
    detalhamento: dict


def _dict_to_resultado(d: dict) -> ResultadoCalculo:
    return ResultadoCalculo(
        regra=d["regra"],
        elegivel=d["elegivel"],
        motivo_inelegibilidade=d.get("motivo_inelegibilidade"),
        tempo_contributivo=d["tempo_contributivo"],
        media_contribuicoes=d["media_contribuicoes"],
        fator_previdenciario=d.get("fator_previdenciario"),
        salario_beneficio=d["salario_beneficio"],
        coeficiente=d["coeficiente"],
        rmi=d["rmi"],
        detalhamento=d.get("detalhamento", {}),
    )


# Módulos de regras na ordem de verificação
_REGRAS = [
    direito_adquirido,
    pontos,
    pedagio_50,
    pedagio_100,
    idade_progressiva,
    aposentadoria_idade,
    regra_permanente,
]


def calcular(caso: Caso, competencias: List[Competencia], data_requerimento: date) -> List[ResultadoCalculo]:
    """
    Verifica elegibilidade e calcula RMI para cada regra aplicável.
    Retorna lista ordenada da mais vantajosa (maior RMI) para a menos vantajosa.
    Regras inelegíveis aparecem ao final com elegivel=False.
    """
    resultados: List[ResultadoCalculo] = []

    for modulo in _REGRAS:
        try:
            resultado_dict = modulo.calcular(caso, competencias, data_requerimento)
            resultados.append(_dict_to_resultado(resultado_dict))
        except Exception as exc:
            logger.error("Erro ao calcular regra %s: %s", modulo.__name__, exc)
            resultados.append(ResultadoCalculo(
                regra=getattr(modulo, "__name__", "desconhecida"),
                elegivel=False,
                motivo_inelegibilidade=f"Erro interno: {exc}",
                tempo_contributivo=None,  # type: ignore[arg-type]
                media_contribuicoes=Decimal("0"),
                fator_previdenciario=None,
                salario_beneficio=Decimal("0"),
                coeficiente=Decimal("0"),
                rmi=Decimal("0"),
                detalhamento={},
            ))

    elegiveis = [r for r in resultados if r.elegivel]
    inelegiveis = [r for r in resultados if not r.elegivel]

    elegiveis.sort(key=lambda r: r.rmi, reverse=True)

    return elegiveis + inelegiveis
