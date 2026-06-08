"""Wrapper do SDK Anthropic com retry, cache e log de custos."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import anthropic

from ..config import ANTHROPIC_API_KEY, MODEL_ANALISE, MODEL_EXTRACAO

logger = logging.getLogger(__name__)

# Preços por 1M tokens (MTok) — atualizar conforme tabela Anthropic
_PRECOS: dict[str, dict] = {
    MODEL_EXTRACAO: {"input": 0.80, "output": 4.00},   # Haiku 4.5
    MODEL_ANALISE: {"input": 3.00, "output": 15.00},   # Sonnet 4.6
}

_MAX_RETRIES = 3
_TIMEOUT = 120


@dataclass
class AIResult:
    success: bool
    data: Optional[dict]
    error: Optional[str]
    tokens_input: int
    tokens_output: int
    custo_usd: float
    modelo: str


class AIClient:
    """Singleton thread-safe para interações com a API Claude."""

    def __init__(self) -> None:
        if not ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY não definida — chamadas AI falharão")
        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY or "")
        self._custo_total: float = 0.0

    @property
    def custo_total_usd(self) -> float:
        return self._custo_total

    def _calcular_custo(self, modelo: str, tokens_in: int, tokens_out: int) -> float:
        precos = _PRECOS.get(modelo, {"input": 3.0, "output": 15.0})
        return (tokens_in / 1_000_000) * precos["input"] + (tokens_out / 1_000_000) * precos["output"]

    def _log_uso(self, modelo: str, operacao: str, tokens_in: int, tokens_out: int, custo: float, caso_id: Optional[int] = None) -> None:
        try:
            from ..db.database import get_session, ai_log_table
            from sqlalchemy import insert
            with get_session() as conn:
                conn.execute(insert(ai_log_table).values(
                    timestamp=datetime.now(),
                    modelo=modelo,
                    operacao=operacao,
                    tokens_input=tokens_in,
                    tokens_output=tokens_out,
                    custo_usd=custo,
                    caso_id=caso_id,
                ))
        except Exception as exc:
            logger.warning("Não foi possível registrar uso AI: %s", exc)

    def chamar(
        self,
        system: str,
        user: str,
        modelo: str,
        operacao: str = "generica",
        caso_id: Optional[int] = None,
        cache_system: bool = True,
    ) -> AIResult:
        """
        Realiza chamada à API com retry exponencial.
        Nunca lança exceção — retorna AIResult(success=False) em caso de erro.
        """
        for tentativa in range(_MAX_RETRIES):
            try:
                system_content = [
                    {
                        "type": "text",
                        "text": system,
                        **({"cache_control": {"type": "ephemeral"}} if cache_system else {}),
                    }
                ]

                response = self._client.messages.create(
                    model=modelo,
                    max_tokens=4096,
                    system=system_content,
                    messages=[{"role": "user", "content": user}],
                    timeout=_TIMEOUT,
                )

                tokens_in = response.usage.input_tokens
                tokens_out = response.usage.output_tokens
                custo = self._calcular_custo(modelo, tokens_in, tokens_out)
                self._custo_total += custo
                self._log_uso(modelo, operacao, tokens_in, tokens_out, custo, caso_id)

                texto = response.content[0].text if response.content else ""
                return AIResult(
                    success=True,
                    data={"texto": texto},
                    error=None,
                    tokens_input=tokens_in,
                    tokens_output=tokens_out,
                    custo_usd=custo,
                    modelo=modelo,
                )

            except anthropic.RateLimitError as exc:
                espera = 2 ** tentativa
                logger.warning("Rate limit — tentativa %d/%d, aguardando %ds: %s", tentativa + 1, _MAX_RETRIES, espera, exc)
                time.sleep(espera)
            except anthropic.APIConnectionError as exc:
                espera = 2 ** tentativa
                logger.warning("Erro de conexão — tentativa %d/%d, aguardando %ds: %s", tentativa + 1, _MAX_RETRIES, espera, exc)
                time.sleep(espera)
            except Exception as exc:
                logger.error("Erro não recuperável na API: %s", exc)
                return AIResult(success=False, data=None, error=str(exc), tokens_input=0, tokens_output=0, custo_usd=0.0, modelo=modelo)

        return AIResult(success=False, data=None, error="Máximo de tentativas atingido", tokens_input=0, tokens_output=0, custo_usd=0.0, modelo=modelo)


# Instância global (inicializada sob demanda)
_instancia: Optional[AIClient] = None


def get_client() -> AIClient:
    global _instancia
    if _instancia is None:
        _instancia = AIClient()
    return _instancia
