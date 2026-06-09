"""Atualização monetária pelo INPC via API BCB/SGS, com cache SQLite."""
from __future__ import annotations

import calendar
import logging
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

import requests
from sqlalchemy import insert, select, text

from ..config import BCB_API_BASE, BCB_SERIE_INPC
from ..db.database import get_session, inpc_cache_table

logger = logging.getLogger(__name__)

_BCB_DATE_FMT = "%d/%m/%Y"
_MAX_ANOS_REQUEST = 10


def _competencia_to_date(competencia: str) -> date:
    """'MM/YYYY' → date no primeiro dia do mês."""
    mes, ano = competencia.split("/")
    return date(int(ano), int(mes), 1)


def _date_to_competencia(d: date) -> str:
    return d.strftime("%m/%Y")


def _parse_lista_bcb(dados) -> Dict[str, float]:
    """Converte lista de itens BCB em {MM/YYYY: variacao_decimal}."""
    if not isinstance(dados, list):
        return {}
    resultado: Dict[str, float] = {}
    for item in dados:
        try:
            partes = item["data"].split("/")
            comp = f"{partes[1]}/{partes[2]}"
            resultado[comp] = float(item["valor"]) / 100.0
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            logger.debug("Item BCB ignorado (%s): %s", exc, item)
    return resultado


def _buscar_fatores_bcb(data_ini: date, data_fim: date) -> Dict[str, float]:
    """Consulta a API BCB/SGS e retorna {MM/YYYY: variacao_decimal}."""
    url = (
        f"{BCB_API_BASE}.{BCB_SERIE_INPC}/dados"
        f"?formato=json"
        f"&dataInicial={data_ini.strftime(_BCB_DATE_FMT)}"
        f"&dataFinal={data_fim.strftime(_BCB_DATE_FMT)}"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        dados = resp.json()
    except Exception as exc:
        logger.error("Erro ao consultar BCB: %s", exc)
        return {}

    if not isinstance(dados, list):
        # API retornou erro em JSON (HTTP 200 com corpo de erro)
        logger.warning("BCB sem dados para %s-%s: %s",
                       data_ini.strftime(_BCB_DATE_FMT),
                       data_fim.strftime(_BCB_DATE_FMT),
                       str(dados.get("erro", dados))[:120])
        return {}

    resultado = _parse_lista_bcb(dados)
    logger.debug("BCB retornou %d fatores para %s-%s",
                 len(resultado), data_ini.strftime(_BCB_DATE_FMT), data_fim.strftime(_BCB_DATE_FMT))
    return resultado


def _salvar_cache(fatores: Dict[str, float]) -> None:
    hoje = date.today().isoformat()
    with get_session() as conn:
        for comp, var in fatores.items():
            conn.execute(
                text(
                    "INSERT OR REPLACE INTO inpc_cache(competencia, variacao_percentual, data_consulta)"
                    " VALUES(:c, :v, :d)"
                ),
                {"c": comp, "v": var, "d": hoje},
            )


def _carregar_cache(competencias: List[str]) -> Dict[str, float]:
    if not competencias:
        return {}
    with get_session() as conn:
        rows = conn.execute(
            select(inpc_cache_table).where(
                inpc_cache_table.c.competencia.in_(competencias)
            )
        ).fetchall()
    return {r.competencia: r.variacao_percentual for r in rows}


def _obter_fatores(comp_ini: str, comp_fim: str) -> Dict[str, float]:
    """
    Obtém fatores mensais INPC entre duas competências (inclusive).
    Usa cache SQLite e só consulta BCB para meses faltantes.
    Respeita o limite de 10 anos por request da API.
    """
    d_ini = _competencia_to_date(comp_ini)
    d_fim = _competencia_to_date(comp_fim)

    # INPC é publicado pelo IBGE entre os dias 8-11 do mês seguinte.
    # Usar mês atual como limite é inseguro; limite seguro = 2 meses atrás.
    hoje = date.today()
    if hoje.month <= 2:
        limite_seguro = date(hoje.year - 1, 10 + hoje.month, 1)
    else:
        limite_seguro = date(hoje.year, hoje.month - 2, 1)
    if d_fim > limite_seguro:
        logger.debug("INPC: data_fim %s além do disponível, limitando a %s", comp_fim, _date_to_competencia(limite_seguro))
        d_fim = limite_seguro

    # Gera lista de todas as competências necessárias
    competencias: List[str] = []
    cur = d_ini
    while cur <= d_fim:
        competencias.append(_date_to_competencia(cur))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)

    cache = _carregar_cache(competencias)
    faltando = [c for c in competencias if c not in cache]

    if faltando:
        # Divide em janelas de 10 anos para respeitar limite da API
        def chunk_por_anos(lista: List[str], anos: int) -> List[List[str]]:
            meses = anos * 12
            return [lista[i:i + meses] for i in range(0, len(lista), meses)]

        for grupo in chunk_por_anos(faltando, _MAX_ANOS_REQUEST):
            d1 = _competencia_to_date(grupo[0])
            d2 = _competencia_to_date(grupo[-1])
            ultimo_dia = calendar.monthrange(d2.year, d2.month)[1]
            d2_fim = date(d2.year, d2.month, ultimo_dia)

            novos = _buscar_fatores_bcb(d1, d2_fim)
            if novos:
                _salvar_cache(novos)
                cache.update(novos)

    return {c: cache[c] for c in competencias if c in cache}


def calcular_fator_acumulado(comp_ini: str, comp_fim: str) -> Decimal:
    """
    Produto dos fatores INPC mensais de comp_ini até comp_fim (inclusive).
    Retorna fator acumulado (ex: 1.3524 para +35,24%).
    """
    fatores = _obter_fatores(comp_ini, comp_fim)
    acumulado = Decimal("1")
    for var in fatores.values():
        acumulado *= Decimal(str(1 + var))
    return acumulado.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def atualizar_inpc(valor: Decimal, competencia_origem: str, competencia_destino: str) -> Decimal:
    """
    Atualiza valor pelo INPC entre competencia_origem e competencia_destino.
    Competências no formato MM/YYYY.
    """
    if competencia_origem == competencia_destino:
        return valor
    fator = calcular_fator_acumulado(competencia_origem, competencia_destino)
    return (valor * fator).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def atualizar_lote(competencias, data_referencia: str) -> list:
    """
    Atualiza remuneracao_atualizada e fator_correcao para todas as
    competências da lista, usando data_referencia como destino.
    """
    from ..models import Competencia

    hoje = date.today()
    atualizadas = []
    for c in competencias:
        try:
            fator = calcular_fator_acumulado(c.competencia, data_referencia)
            c.remuneracao_atualizada = (c.base_contribuicao * fator).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            c.fator_correcao = fator
            c.data_calculo_correcao = hoje
        except Exception as exc:
            logger.warning("Não foi possível atualizar %s: %s", c.competencia, exc)
        atualizadas.append(c)
    return atualizadas
