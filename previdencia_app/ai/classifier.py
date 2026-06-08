"""Classifica o tipo de documento previdenciário."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import MODEL_EXTRACAO
from ..models.documento import TipoDocumento
from .client import get_client

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "classifier.txt"


def _carregar_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def classificar_documento(texto: str) -> TipoDocumento:
    """
    Identifica o tipo do documento a partir do texto extraído.
    Retorna TipoDocumento.DESCONHECIDO em caso de falha.
    """
    if not texto or len(texto.strip()) < 20:
        return TipoDocumento.DESCONHECIDO

    system = _carregar_prompt()
    user = f"Texto do documento:\n\n{texto[:3000]}"

    result = get_client().chamar(
        system=system,
        user=user,
        modelo=MODEL_EXTRACAO,
        operacao="classificacao",
    )

    if not result.success or not result.data:
        logger.warning("Classificação falhou: %s", result.error)
        return TipoDocumento.DESCONHECIDO

    try:
        dados = json.loads(result.data["texto"])
        tipo_str = dados.get("tipo", "DESCONHECIDO").upper()
        return TipoDocumento(tipo_str)
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning("Resposta inválida do classificador: %s | %s", result.data.get("texto", ""), exc)
        return TipoDocumento.DESCONHECIDO
