"""Extrai competências estruturadas de documentos previdenciários."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional

from ..config import MODEL_EXTRACAO
from ..models import Competencia, FonteDocumento, TipoVinculo
from ..models.documento import TipoDocumento
from .client import get_client, limpar_json

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

_TIPO_PARA_FONTE: dict[str, FonteDocumento] = {
    "CNIS": FonteDocumento.CNIS,
    "CTPS": FonteDocumento.CTPS,
    "CTC": FonteDocumento.CTC,
    "HOLERITE": FonteDocumento.HOLERITE,
    "PRO_LABORE": FonteDocumento.PRO_LABORE,
    "PGDAS_MEI": FonteDocumento.PGDAS,
    "DARF": FonteDocumento.DARF,
    "FGTS": FonteDocumento.FGTS,
}

_TIPO_PARA_VINCULO: dict[str, TipoVinculo] = {
    "CLT": TipoVinculo.CLT,
    "AUTONOMO": TipoVinculo.AUTONOMO,
    "MEI": TipoVinculo.MEI,
    "PRO_LABORE": TipoVinculo.PRO_LABORE,
    "FACULTATIVO": TipoVinculo.FACULTATIVO,
    "RPPS": TipoVinculo.RPPS,
    "RURAL": TipoVinculo.RURAL,
}


def _prompt_para_tipo(tipo: TipoDocumento) -> str:
    nome_arquivo = {
        TipoDocumento.CNIS: "cnis.txt",
        TipoDocumento.CTPS: "ctps.txt",
        TipoDocumento.CTC: "ctc.txt",
        TipoDocumento.HOLERITE: "holerite.txt",
        TipoDocumento.PRO_LABORE: "pro_labore.txt",
        TipoDocumento.PGDAS_MEI: "pgdas_mei.txt",
        TipoDocumento.DARF: "darf.txt",
        TipoDocumento.FGTS: "fgts.txt",
    }.get(tipo)

    if not nome_arquivo:
        raise ValueError(f"Sem prompt para tipo: {tipo}")
    return (_PROMPTS_DIR / nome_arquivo).read_text(encoding="utf-8")


_PLANO_REAL_YYYYMM = 199407  # julho de 1994


def _decimal_safe(valor) -> Decimal:
    try:
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _comp_to_yyyymm(competencia: str) -> int:
    try:
        mes, ano = competencia.split("/")
        return int(ano) * 100 + int(mes)
    except (ValueError, AttributeError):
        return 0


def _e_pre_real(competencia: str) -> bool:
    return _comp_to_yyyymm(competencia) < _PLANO_REAL_YYYYMM


def _aplicar_regra_pre_real(c: Competencia) -> Competencia:
    """
    Competências anteriores a jul/1994 (Plano Real):
    - Contam tempo de contribuição normalmente
    - Valores monetários zerados (não entram na média — UI exibe aviso)
    - descricao_inconsistencia explica o motivo
    """
    if _e_pre_real(c.competencia):
        c.remuneracao_bruta = Decimal("0")
        c.base_contribuicao = Decimal("0")
        c.valor_contribuicao = None
        c.flag_inconsistencia = True
        c.descricao_inconsistencia = (
            "Período anterior ao Plano Real (jul/1994): "
            "conta tempo de contribuição, valor não entra na média salarial."
        )
    return c


def _calcular_confianca(comp: dict) -> float:
    campos_esperados = ["competencia", "remuneracao", "empregador"]
    preenchidos = sum(1 for c in campos_esperados if comp.get(c))
    return preenchidos / len(campos_esperados)


def _parse_cnis(dados: dict, caso_id: int, documento_id: Optional[int]) -> List[Competencia]:
    competencias: List[Competencia] = []
    for vinculo in dados.get("vinculos", []):
        tipo_str = vinculo.get("tipo", "CLT").upper()
        tipo_vinculo = _TIPO_PARA_VINCULO.get(tipo_str, TipoVinculo.CLT)
        empregador = vinculo.get("empregador", "Não identificado")
        cnpj = vinculo.get("cnpj")

        for comp in vinculo.get("competencias", []):
            # Formato C: remuneracao vem de salario_contribuicao
            remuneracao = (
                comp.get("remuneracao")
                or comp.get("salario_contribuicao")
                or comp.get("base_contribuicao")
                or 0
            )
            base = comp.get("base_contribuicao") or remuneracao
            valor_contrib = comp.get("valor_contribuicao") or comp.get("contribuicao")
            pendencia = bool(comp.get("pendencia", False))
            indicadores = comp.get("indicadores", [])
            # Qualquer indicador que não seja puramente informativo → pendência
            if indicadores and not pendencia:
                pendencia = True

            c = Competencia(
                caso_id=caso_id,
                competencia=comp.get("competencia", ""),
                tipo_vinculo=tipo_vinculo,
                empregador_nome=empregador,
                empregador_cnpj_cpf=cnpj,
                remuneracao_bruta=_decimal_safe(remuneracao),
                base_contribuicao=_decimal_safe(base),
                valor_contribuicao=_decimal_safe(valor_contrib) if valor_contrib else None,
                fonte=FonteDocumento.CNIS,
                documento_id=documento_id,
                flag_pendencia_cnis=pendencia,
                confianca_extracao=_calcular_confianca(comp),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            competencias.append(_aplicar_regra_pre_real(c))
    # beneficios are intentionally ignored — not contributive periods
    return competencias


def _parse_ctps(dados: dict, caso_id: int, documento_id: Optional[int]) -> List[Competencia]:
    competencias: List[Competencia] = []
    for vinculo in dados.get("vinculos", []):
        empregador = vinculo.get("empregador", "Não identificado")
        cnpj = vinculo.get("cnpj")
        inicio = vinculo.get("data_admissao", "")
        fim = vinculo.get("data_demissao")

        for comp in vinculo.get("competencias", []):
            c = Competencia(
                caso_id=caso_id,
                competencia=comp.get("competencia", ""),
                tipo_vinculo=TipoVinculo.CLT,
                empregador_nome=empregador,
                empregador_cnpj_cpf=cnpj,
                remuneracao_bruta=_decimal_safe(comp.get("salario", 0)),
                base_contribuicao=_decimal_safe(comp.get("salario", 0)),
                fonte=FonteDocumento.CTPS,
                documento_id=documento_id,
                confianca_extracao=_calcular_confianca(comp),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            competencias.append(_aplicar_regra_pre_real(c))
    return competencias


def _parse_generico(dados: dict, caso_id: int, documento_id: Optional[int], fonte: FonteDocumento, tipo_vinculo: TipoVinculo) -> List[Competencia]:
    competencias: List[Competencia] = []
    empregador = dados.get("empregador") or dados.get("empresa") or dados.get("nome_mei") or "Não identificado"
    cnpj = dados.get("cnpj") or dados.get("cpf")

    for comp in dados.get("competencias", []):
        c = Competencia(
            caso_id=caso_id,
            competencia=comp.get("competencia", ""),
            tipo_vinculo=tipo_vinculo,
            empregador_nome=empregador,
            empregador_cnpj_cpf=cnpj,
            remuneracao_bruta=_decimal_safe(comp.get("remuneracao") or comp.get("salario") or comp.get("valor", 0)),
            base_contribuicao=_decimal_safe(comp.get("base_contribuicao") or comp.get("remuneracao") or comp.get("valor", 0)),
            valor_contribuicao=_decimal_safe(comp.get("valor_inss") or comp.get("valor_contribuicao")) if comp.get("valor_inss") or comp.get("valor_contribuicao") else None,
            fonte=fonte,
            documento_id=documento_id,
            confianca_extracao=_calcular_confianca(comp),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        competencias.append(_aplicar_regra_pre_real(c))
    return competencias


def _parse_fgts(dados: dict, caso_id: int, documento_id: Optional[int]) -> List[Competencia]:
    competencias: List[Competencia] = []
    for vinculo in dados.get("vinculos", []):
        empregador = vinculo.get("empregador", "Não identificado")
        cnpj = vinculo.get("cnpj")
        for comp in vinculo.get("competencias", []):
            salario = comp.get("salario") or comp.get("remuneracao") or 0
            if not salario:
                dep = comp.get("valor_deposito") or 0
                salario = float(dep) / 0.08 if dep else 0
            c = Competencia(
                caso_id=caso_id,
                competencia=comp.get("competencia", ""),
                tipo_vinculo=TipoVinculo.CLT,
                empregador_nome=empregador,
                empregador_cnpj_cpf=cnpj,
                remuneracao_bruta=_decimal_safe(salario),
                base_contribuicao=_decimal_safe(salario),
                fonte=FonteDocumento.FGTS,
                documento_id=documento_id,
                confianca_extracao=_calcular_confianca(comp),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            competencias.append(_aplicar_regra_pre_real(c))
    return competencias


def _parse_ctc(dados: dict, caso_id: int, documento_id: Optional[int]) -> List[Competencia]:
    competencias: List[Competencia] = []
    empregador = dados.get("empregador") or dados.get("orgao_emissor") or "Não identificado"
    cnpj = dados.get("cnpj")
    # Detect RPPS from regime or indicadores
    regime = dados.get("regime", "")
    indicadores = dados.get("indicadores_vinculo", [])
    tipo_vinculo = TipoVinculo.RPPS if ("RPPS" in regime or "PRPPS" in indicadores) else TipoVinculo.CLT

    for comp in dados.get("competencias", []):
        remuneracao = comp.get("remuneracao") or comp.get("base_contribuicao") or 0
        base = comp.get("base_contribuicao") or remuneracao
        c = Competencia(
            caso_id=caso_id,
            competencia=comp.get("competencia", ""),
            tipo_vinculo=tipo_vinculo,
            empregador_nome=empregador,
            empregador_cnpj_cpf=cnpj,
            remuneracao_bruta=_decimal_safe(remuneracao),
            base_contribuicao=_decimal_safe(base),
            fonte=FonteDocumento.CTC,
            documento_id=documento_id,
            confianca_extracao=_calcular_confianca(comp),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        competencias.append(_aplicar_regra_pre_real(c))
    return competencias


def extrair(texto: str, tipo: TipoDocumento, caso_id: int, documento_id: Optional[int] = None) -> List[Competencia]:
    """
    Extrai competências estruturadas do texto de um documento.
    Retorna lista vazia em caso de falha (nunca lança exceção).
    """
    if tipo == TipoDocumento.DESCONHECIDO:
        logger.warning("Tipo de documento desconhecido — extração ignorada")
        return []

    try:
        system = _prompt_para_tipo(tipo)
    except ValueError as exc:
        logger.error("Sem prompt para %s: %s", tipo, exc)
        return []

    from ..config import MODEL_ANALISE
    _SONNET_TIPOS = {TipoDocumento.CNIS, TipoDocumento.CTPS, TipoDocumento.CTC, TipoDocumento.FGTS}
    modelo = MODEL_ANALISE if tipo in _SONNET_TIPOS else MODEL_EXTRACAO
    limite_texto = 30000 if tipo in _SONNET_TIPOS else 8000
    max_tokens = 16000 if tipo in _SONNET_TIPOS else 4096

    result = get_client().chamar(
        system=system,
        user=f"Extraia os dados do seguinte documento:\n\n{texto[:limite_texto]}",
        modelo=modelo,
        operacao=f"extracao_{tipo.value.lower()}",
        caso_id=caso_id,
        max_tokens=max_tokens,
    )

    if not result.success or not result.data:
        logger.error("Extração falhou para %s: %s", tipo, result.error)
        return []

    try:
        texto_resp = limpar_json(result.data["texto"])
        dados = json.loads(texto_resp)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("JSON inválido na extração %s: %s | resp: %s", tipo, exc, result.data.get("texto", "")[:200])
        return []

    fonte = _TIPO_PARA_FONTE.get(tipo.value, FonteDocumento.MANUAL)

    try:
        if tipo == TipoDocumento.CNIS:
            return _parse_cnis(dados, caso_id, documento_id)
        if tipo == TipoDocumento.CTPS:
            return _parse_ctps(dados, caso_id, documento_id)
        if tipo == TipoDocumento.CTC:
            return _parse_ctc(dados, caso_id, documento_id)
        if tipo == TipoDocumento.HOLERITE:
            return _parse_generico(dados, caso_id, documento_id, fonte, TipoVinculo.CLT)
        if tipo == TipoDocumento.PRO_LABORE:
            return _parse_generico(dados, caso_id, documento_id, fonte, TipoVinculo.PRO_LABORE)
        if tipo == TipoDocumento.PGDAS_MEI:
            return _parse_generico(dados, caso_id, documento_id, fonte, TipoVinculo.MEI)
        if tipo == TipoDocumento.DARF:
            return _parse_generico(dados, caso_id, documento_id, fonte, TipoVinculo.AUTONOMO)
        if tipo == TipoDocumento.FGTS:
            return _parse_fgts(dados, caso_id, documento_id)
    except Exception as exc:
        logger.error("Erro ao parsear resposta de %s: %s", tipo, exc)

    return []
