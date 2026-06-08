"""Análise de inconsistências entre competências — usa Sonnet para raciocínio."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from ..config import MODEL_ANALISE
from ..models import Competencia, FonteDocumento
from .client import get_client, limpar_json

logger = logging.getLogger(__name__)


class TipoInconsistencia(str, Enum):
    SALARIO_ABAIXO_MINIMO = "SALARIO_ABAIXO_MINIMO"
    COMPETENCIA_SEM_VINCULO = "COMPETENCIA_SEM_VINCULO"
    DIVERGENCIA_VALOR = "DIVERGENCIA_VALOR"
    DIVERGENCIA_EMPREGADOR = "DIVERGENCIA_EMPREGADOR"
    PERIODO_SEM_CNIS = "PERIODO_SEM_CNIS"
    SOBREPOSICAO = "SOBREPOSICAO"
    GAP_INEXPLICADO = "GAP_INEXPLICADO"
    CONTRIBUICAO_ACIMA_TETO = "CONTRIBUICAO_ACIMA_TETO"


@dataclass
class Inconsistencia:
    tipo: TipoInconsistencia
    competencia: Optional[str]
    fonte_a: FonteDocumento
    fonte_b: Optional[FonteDocumento]
    descricao: str
    severidade: str  # "ALTA" | "MEDIA" | "BAIXA"
    sugestao: Optional[str]


_SYSTEM_PROMPT = """Você é um especialista em análise previdenciária brasileira.
Receberá uma lista de competências contributivas de um segurado e deve identificar inconsistências.

Retorne SOMENTE um JSON válido com a estrutura:
{
  "inconsistencias": [
    {
      "tipo": "TIPO_ENUM",
      "competencia": "MM/YYYY ou null",
      "fonte_a": "CNIS|CTPS|CTC|HOLERITE|PRO_LABORE|PGDAS|DARF|FGTS|MANUAL",
      "fonte_b": "idem ou null",
      "descricao": "descrição clara",
      "severidade": "ALTA|MEDIA|BAIXA",
      "sugestao": "sugestão de ação ou null"
    }
  ]
}

Tipos de inconsistência a verificar:
- SALARIO_ABAIXO_MINIMO: remuneração menor que salário mínimo da época
- COMPETENCIA_SEM_VINCULO: contribuição sem vínculo ativo no período
- DIVERGENCIA_VALOR: mesma competência com valores diferentes em fontes distintas (>5%)
- DIVERGENCIA_EMPREGADOR: mesmo período com empregadores diferentes entre fontes
- PERIODO_SEM_CNIS: competência em fonte secundária ausente no CNIS
- SOBREPOSICAO: dois vínculos ativos simultaneamente (verificar se permitido pelo RGPS)
- GAP_INEXPLICADO: período sem contribuição >3 meses sem afastamento registrado
- CONTRIBUICAO_ACIMA_TETO: base de contribuição acima do teto do RGPS na época

Pendências do CNIS (flag_pendencia_cnis=true) NÃO são inconsistências — ignore-as.
Seja objetivo e preciso. Não inclua inconsistências óbvias ou sem relevância prática."""


def analisar_inconsistencias(competencias: List[Competencia]) -> List[Inconsistencia]:
    """
    Analisa inconsistências entre competências usando Claude Sonnet.
    Retorna lista vazia em caso de falha.
    """
    if not competencias:
        return []

    dados = [
        {
            "competencia": c.competencia,
            "empregador": c.empregador_nome,
            "tipo_vinculo": c.tipo_vinculo.value,
            "remuneracao_bruta": float(c.remuneracao_bruta),
            "base_contribuicao": float(c.base_contribuicao),
            "fonte": c.fonte.value,
            "flag_pendencia_cnis": c.flag_pendencia_cnis,
        }
        for c in competencias
    ]

    result = get_client().chamar(
        system=_SYSTEM_PROMPT,
        user=f"Analise as seguintes {len(dados)} competências:\n\n{json.dumps(dados, ensure_ascii=False)}",
        modelo=MODEL_ANALISE,
        operacao="analise_inconsistencias",
    )

    if not result.success or not result.data:
        logger.error("Análise de inconsistências falhou: %s", result.error)
        return []

    try:
        texto_resp = limpar_json(result.data["texto"])
        dados_resp = json.loads(texto_resp)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("JSON inválido na análise: %s", exc)
        return []

    inconsistencias: List[Inconsistencia] = []
    for item in dados_resp.get("inconsistencias", []):
        try:
            inconsistencias.append(Inconsistencia(
                tipo=TipoInconsistencia(item["tipo"]),
                competencia=item.get("competencia"),
                fonte_a=FonteDocumento(item["fonte_a"]),
                fonte_b=FonteDocumento(item["fonte_b"]) if item.get("fonte_b") else None,
                descricao=item["descricao"],
                severidade=item.get("severidade", "MEDIA"),
                sugestao=item.get("sugestao"),
            ))
        except (KeyError, ValueError) as exc:
            logger.warning("Item de inconsistência inválido: %s | %s", item, exc)

    return inconsistencias
