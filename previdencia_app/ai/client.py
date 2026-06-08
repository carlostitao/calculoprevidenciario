"""Wrapper do SDK Anthropic com retry, cache, log de custos e OCR via visão."""
from __future__ import annotations

import base64
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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

# Extensões de imagem suportadas pela API de visão
_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@dataclass
class AIResult:
    success: bool
    data: Optional[dict]
    error: Optional[str]
    tokens_input: int
    tokens_output: int
    custo_usd: float
    modelo: str


def limpar_json(texto: str) -> str:
    """Remove markdown fences e texto fora do bloco JSON principal."""
    texto = re.sub(r"```[a-zA-Z]*\n?", "", texto)
    texto = texto.replace("```", "").strip()

    match = re.search(r"[\[{]", texto)
    if match:
        texto = texto[match.start():]

    last_close = max(texto.rfind("}"), texto.rfind("]"))
    if last_close != -1:
        texto = texto[: last_close + 1]

    return texto.strip()


def _corrigir_json(texto: str) -> str:
    """Aplica correções heurísticas em JSON malformado retornado pelo modelo."""
    # Remove comentários de linha (// ...) fora de strings
    texto = re.sub(r'(?<!["\w])//[^\n]*', '', texto)

    # Remove trailing commas antes de } ou ]
    texto = re.sub(r',\s*([}\]])', r'\1', texto)

    # Números com vírgula decimal fora de strings: 1.234,56 → 1234.56
    # Detecta padrão: dígito(s).dígito(s),dígito(s) (formato BR com separador de milhar)
    def _fix_numero_br(m: re.Match) -> str:
        s = m.group(0)
        # Remove pontos de milhar, troca vírgula decimal por ponto
        s = s.replace(".", "").replace(",", ".")
        return s

    texto = re.sub(r'\b\d{1,3}(?:\.\d{3})+,\d+\b', _fix_numero_br, texto)
    # Também trata vírgula decimal simples: 1234,56 → 1234.56 (sem ponto de milhar)
    texto = re.sub(r'(?<!\d)(\d+),(\d{2})(?!\d)', r'\1.\2', texto)

    return texto


def parse_json_robusto(texto: str) -> dict:
    """
    Tenta parsear JSON com múltiplas estratégias de correção progressiva.
    Lança json.JSONDecodeError se todas falharem.
    """
    import json

    candidato = limpar_json(texto)

    # Tentativa 1: JSON padrão
    try:
        return json.loads(candidato)
    except json.JSONDecodeError:
        pass

    # Tentativa 2: após correções heurísticas
    corrigido = _corrigir_json(candidato)
    try:
        return json.loads(corrigido)
    except json.JSONDecodeError:
        pass

    # Tentativa 3: truncamento — encontra o último objeto/array fechado de forma válida
    # Reduz progressivamente pelo último ',' até encontrar JSON válido
    for separador in ['\n  },\n', '\n    },\n', '},\n', '}']:
        idx = corrigido.rfind(separador)
        if idx == -1:
            continue
        # Fecha o array e objeto raiz
        tentativa = corrigido[: idx + separador.rstrip(',\n').__len__()]
        # Conta chaves/colchetes não fechados e fecha
        tentativa = _fechar_json_truncado(tentativa)
        try:
            return json.loads(tentativa)
        except json.JSONDecodeError:
            continue

    # Última tentativa: fecha automaticamente qualquer truncamento
    fechado = _fechar_json_truncado(corrigido)
    return json.loads(fechado)


def _fechar_json_truncado(texto: str) -> str:
    """Fecha chaves e colchetes abertos para recuperar JSON truncado."""
    pilha = []
    dentro_string = False
    escape = False

    for ch in texto:
        if escape:
            escape = False
            continue
        if ch == '\\' and dentro_string:
            escape = True
            continue
        if ch == '"':
            dentro_string = not dentro_string
            continue
        if not dentro_string:
            if ch in ('{', '['):
                pilha.append('}' if ch == '{' else ']')
            elif ch in ('}', ']') and pilha:
                pilha.pop()

    fechamento = ''.join(reversed(pilha))
    return texto.rstrip().rstrip(',') + fechamento


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
        max_tokens: int = 4096,
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
                    max_tokens=max_tokens,
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

    def chamar_com_imagem(
        self,
        system: str,
        instrucao: str,
        imagem_bytes: bytes,
        mime_type: str,
        modelo: str,
        operacao: str = "ocr",
        caso_id: Optional[int] = None,
        max_tokens: int = 4096,
    ) -> AIResult:
        """
        Envia imagem diretamente para a API de visão do Claude.
        Usado como OCR sem depender do Tesseract local.
        """
        b64 = base64.standard_b64encode(imagem_bytes).decode("utf-8")

        for tentativa in range(_MAX_RETRIES):
            try:
                response = self._client.messages.create(
                    model=modelo,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": b64,
                                    },
                                },
                                {"type": "text", "text": instrucao},
                            ],
                        }
                    ],
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
                logger.warning("Rate limit (visão) — tentativa %d/%d, aguardando %ds", tentativa + 1, _MAX_RETRIES, espera)
                time.sleep(espera)
            except anthropic.APIConnectionError as exc:
                espera = 2 ** tentativa
                logger.warning("Erro conexão (visão) — tentativa %d/%d, aguardando %ds", tentativa + 1, _MAX_RETRIES, espera)
                time.sleep(espera)
            except Exception as exc:
                logger.error("Erro não recuperável na API de visão: %s", exc)
                return AIResult(success=False, data=None, error=str(exc), tokens_input=0, tokens_output=0, custo_usd=0.0, modelo=modelo)

        return AIResult(success=False, data=None, error="Máximo de tentativas atingido", tokens_input=0, tokens_output=0, custo_usd=0.0, modelo=modelo)


# Instância global (inicializada sob demanda)
_instancia: Optional[AIClient] = None


def get_client() -> AIClient:
    global _instancia
    if _instancia is None:
        _instancia = AIClient()
    return _instancia
