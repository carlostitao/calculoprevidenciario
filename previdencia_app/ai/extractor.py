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
from .client import get_client, limpar_json, parse_json_robusto

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


def _get(d: dict, *chaves, default=None):
    """Busca o primeiro campo presente no dict entre os nomes alternativos fornecidos."""
    for k in chaves:
        v = d.get(k)
        if v is not None and v != "" and v != 0:
            return v
    return default


def _get_vinculos(dados: dict) -> list:
    """Retorna a lista de vínculos independente do nome usado pelo modelo."""
    return (
        dados.get("vinculos")
        or dados.get("contratos")
        or dados.get("periodos")
        or dados.get("empregos")
        or []
    )


def _get_competencias(vinculo: dict) -> list:
    """Retorna a lista de competências de um vínculo."""
    return (
        vinculo.get("competencias")
        or vinculo.get("meses")
        or vinculo.get("periodos_mensais")
        or vinculo.get("remuneracoes")
        or []
    )


def _get_competencia_str(comp: dict) -> str:
    """Extrai a string MM/YYYY da competência."""
    return (
        comp.get("competencia")
        or comp.get("mes")
        or comp.get("mes_ano")
        or comp.get("periodo")
        or ""
    )


def _get_remuneracao(comp: dict) -> float:
    """Extrai o valor de remuneração/salário da competência com múltiplos nomes."""
    return _get(
        comp,
        "remuneracao", "salario", "valor", "remuneracao_bruta",
        "salario_contribuicao", "base_contribuicao", "vencimento",
        "salario_bruto", "rendimento",
        default=0,
    )


def _get_empregador(vinculo: dict) -> str:
    return _get(
        vinculo,
        "empregador", "empresa", "nome_empresa", "razao_social",
        "orgao", "tomador", "contratante",
        default="Não identificado",
    )


def _parse_cnis(dados: dict, caso_id: int, documento_id: Optional[int]) -> List[Competencia]:
    competencias: List[Competencia] = []
    for vinculo in _get_vinculos(dados):
        tipo_str = _get(vinculo, "tipo", "tipo_vinculo", "categoria", default="CLT")
        if isinstance(tipo_str, str):
            tipo_str = tipo_str.upper()
        tipo_vinculo = _TIPO_PARA_VINCULO.get(tipo_str, TipoVinculo.CLT)
        empregador = _get_empregador(vinculo)
        cnpj = _get(vinculo, "cnpj", "cpf_cnpj", "cnpj_cpf")

        for comp in _get_competencias(vinculo):
            remuneracao = _get_remuneracao(comp)
            base = _get(comp, "base_contribuicao", "base", default=remuneracao)
            valor_contrib = _get(comp, "valor_contribuicao", "contribuicao", "valor_inss", "inss")
            pendencia = bool(_get(comp, "pendencia", "tem_pendencia", "flag_pendencia", default=False))
            indicadores = comp.get("indicadores") or comp.get("flags") or []
            if indicadores and not pendencia:
                pendencia = True

            c = Competencia(
                caso_id=caso_id,
                competencia=_get_competencia_str(comp),
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
    for vinculo in _get_vinculos(dados):
        empregador = _get_empregador(vinculo)
        cnpj = _get(vinculo, "cnpj", "cpf_cnpj")

        for comp in _get_competencias(vinculo):
            salario = _get_remuneracao(comp)
            c = Competencia(
                caso_id=caso_id,
                competencia=_get_competencia_str(comp),
                tipo_vinculo=TipoVinculo.CLT,
                empregador_nome=empregador,
                empregador_cnpj_cpf=cnpj,
                remuneracao_bruta=_decimal_safe(salario),
                base_contribuicao=_decimal_safe(salario),
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
    empregador = _get(dados, "empregador", "empresa", "nome_mei", "nome", default="Não identificado")
    cnpj = _get(dados, "cnpj", "cpf", "cpf_cnpj")

    lista = dados.get("competencias") or dados.get("meses") or dados.get("periodos") or []
    for comp in lista:
        rem = _get_remuneracao(comp)
        base = _get(comp, "base_contribuicao", "base", default=rem)
        contrib = _get(comp, "valor_inss", "valor_contribuicao", "contribuicao", "inss")
        c = Competencia(
            caso_id=caso_id,
            competencia=_get_competencia_str(comp),
            tipo_vinculo=tipo_vinculo,
            empregador_nome=empregador,
            empregador_cnpj_cpf=cnpj,
            remuneracao_bruta=_decimal_safe(rem),
            base_contribuicao=_decimal_safe(base),
            valor_contribuicao=_decimal_safe(contrib) if contrib else None,
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
    for vinculo in _get_vinculos(dados):
        empregador = _get_empregador(vinculo)
        cnpj = _get(vinculo, "cnpj", "cpf_cnpj")
        for comp in _get_competencias(vinculo):
            salario = _get(comp, "salario", "remuneracao", "salario_calculado", default=0)
            if not salario:
                dep = _get(comp, "valor_deposito", "deposito", "valor", default=0)
                salario = float(dep) / 0.08 if dep else 0
            c = Competencia(
                caso_id=caso_id,
                competencia=_get_competencia_str(comp),
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
    empregador = _get(dados, "empregador", "orgao_emissor", "orgao", "nome_orgao", default="Não identificado")
    cnpj = _get(dados, "cnpj", "cpf_cnpj")
    regime = dados.get("regime") or dados.get("tipo_regime") or ""
    indicadores = dados.get("indicadores_vinculo") or dados.get("indicadores") or []
    tipo_vinculo = TipoVinculo.RPPS if ("RPPS" in str(regime) or "PRPPS" in indicadores) else TipoVinculo.CLT

    lista = dados.get("competencias") or dados.get("remuneracoes") or dados.get("meses") or []
    for comp in lista:
        remuneracao = _get_remuneracao(comp)
        base = _get(comp, "base_contribuicao", "base", default=remuneracao)
        c = Competencia(
            caso_id=caso_id,
            competencia=_get_competencia_str(comp),
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
        logger.warning("[EXTRATOR] Tipo desconhecido — extração ignorada")
        return []

    try:
        system = _prompt_para_tipo(tipo)
    except ValueError as exc:
        logger.error("[EXTRATOR] Sem prompt para %s: %s", tipo, exc)
        return []

    from ..config import MODEL_ANALISE
    _SONNET_TIPOS = {TipoDocumento.CNIS, TipoDocumento.CTPS, TipoDocumento.CTC, TipoDocumento.FGTS}

    # C) Usa Haiku quando o texto veio de pdfplumber (estruturado, sem ruído de OCR).
    # Documentos de imagem (CTPS manuscrita, FGTS escaneado) ficam com Sonnet pela
    # variabilidade do OCR. Heurística: texto pdfplumber tem densidade alta e sem
    # marcas de OCR ("  " espaços duplos, linhas com só traços).
    _e_texto_nativo = len(texto) >= 500 and texto.count("\n") > 10 and "\x0c" not in texto
    if tipo in _SONNET_TIPOS and not _e_texto_nativo:
        modelo = MODEL_ANALISE   # Sonnet para OCR (imagens)
    else:
        modelo = MODEL_EXTRACAO  # Haiku para texto nativo (rápido)

    limite_texto = 30000 if tipo in _SONNET_TIPOS else 8000
    max_tokens = 16000 if tipo in _SONNET_TIPOS else 4096

    logger.info("[EXTRATOR] Modelo selecionado: %s (texto_nativo=%s)", modelo, _e_texto_nativo)

    texto_truncado = texto[:limite_texto]
    logger.info(
        "[EXTRATOR] Iniciando extração: tipo=%s modelo=%s max_tokens=%d "
        "texto_original=%d chars texto_enviado=%d chars",
        tipo.value, modelo, max_tokens, len(texto), len(texto_truncado),
    )

    result = get_client().chamar(
        system=system,
        user=f"Extraia os dados do seguinte documento:\n\n{texto_truncado}",
        modelo=modelo,
        operacao=f"extracao_{tipo.value.lower()}",
        caso_id=caso_id,
        max_tokens=max_tokens,
    )

    if not result.success or not result.data:
        logger.error("[EXTRATOR] Chamada API falhou para %s: %s", tipo, result.error)
        return []

    resposta_bruta = result.data.get("texto", "")
    logger.debug("[EXTRATOR] Resposta bruta (%d chars):\n%s", len(resposta_bruta), resposta_bruta[:2000])

    try:
        dados = parse_json_robusto(resposta_bruta)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error(
            "[EXTRATOR] JSON irrecuperável para %s: %s\n"
            "--- Primeiros 1000 chars da resposta ---\n%s\n"
            "--- Últimos 500 chars ---\n%s",
            tipo, exc,
            resposta_bruta[:1000],
            resposta_bruta[-500:],
        )
        return []

    # Log do que o modelo entendeu
    vinculos = dados.get("vinculos", [])
    n_comps_raw = sum(len(v.get("competencias", [])) for v in vinculos)
    logger.info(
        "[EXTRATOR] JSON parseado OK: %d vínculos, %d competências raw (segurado=%s)",
        len(vinculos), n_comps_raw,
        dados.get("segurado", {}).get("nome", "?"),
    )
    if not vinculos:
        logger.warning(
            "[EXTRATOR] Nenhum vínculo encontrado. Chaves raiz presentes: %s",
            list(dados.keys()),
        )

    fonte = _TIPO_PARA_FONTE.get(tipo.value, FonteDocumento.MANUAL)

    try:
        if tipo == TipoDocumento.CNIS:
            resultado = _parse_cnis(dados, caso_id, documento_id)
        elif tipo == TipoDocumento.CTPS:
            resultado = _parse_ctps(dados, caso_id, documento_id)
        elif tipo == TipoDocumento.CTC:
            resultado = _parse_ctc(dados, caso_id, documento_id)
        elif tipo == TipoDocumento.HOLERITE:
            resultado = _parse_generico(dados, caso_id, documento_id, fonte, TipoVinculo.CLT)
        elif tipo == TipoDocumento.PRO_LABORE:
            resultado = _parse_generico(dados, caso_id, documento_id, fonte, TipoVinculo.PRO_LABORE)
        elif tipo == TipoDocumento.PGDAS_MEI:
            resultado = _parse_generico(dados, caso_id, documento_id, fonte, TipoVinculo.MEI)
        elif tipo == TipoDocumento.DARF:
            resultado = _parse_generico(dados, caso_id, documento_id, fonte, TipoVinculo.AUTONOMO)
        elif tipo == TipoDocumento.FGTS:
            resultado = _parse_fgts(dados, caso_id, documento_id)
        else:
            logger.warning("[EXTRATOR] Tipo sem parser: %s", tipo)
            return []

        n_pendentes = sum(1 for c in resultado if c.flag_pendencia_cnis)
        n_pre_real = sum(1 for c in resultado if c.flag_inconsistencia)
        logger.info(
            "[EXTRATOR] Parser concluído: %d competências geradas "
            "(%d com pendência CNIS, %d pré-Plano Real)",
            len(resultado), n_pendentes, n_pre_real,
        )
        return resultado

    except Exception as exc:
        logger.error("[EXTRATOR] Erro no parser de %s: %s", tipo, exc, exc_info=True)

    return []
