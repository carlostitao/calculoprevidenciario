from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import delete, insert, select, update

from ..models import Caso, Competencia, Documento, FonteDocumento, StatusDocumento, TipoDocumento, TipoVinculo
from ..models.caso import Sexo
from .database import (
    casos_table, competencias_table, documentos_table, get_session,
)

logger = logging.getLogger(__name__)


class CasoRepository:

    @staticmethod
    def criar(caso: Caso) -> int:
        """Persiste um novo caso e retorna o ID gerado."""
        with get_session() as conn:
            result = conn.execute(
                insert(casos_table).values(
                    nome=caso.nome,
                    cpf=caso.cpf,
                    sexo=caso.sexo.value,
                    data_nascimento=caso.data_nascimento.isoformat(),
                    data_filiacao_rgps=caso.data_filiacao_rgps.isoformat() if caso.data_filiacao_rgps else None,
                    observacoes=caso.observacoes,
                    created_at=caso.created_at,
                    updated_at=caso.updated_at,
                )
            )
            return result.lastrowid

    @staticmethod
    def buscar(caso_id: int) -> Optional[Caso]:
        """Retorna um caso pelo ID ou None."""
        with get_session() as conn:
            row = conn.execute(
                select(casos_table).where(casos_table.c.id == caso_id)
            ).fetchone()
        if row is None:
            return None
        return _row_to_caso(row)

    @staticmethod
    def listar_todos() -> List[Caso]:
        """Retorna todos os casos cadastrados."""
        with get_session() as conn:
            rows = conn.execute(select(casos_table).order_by(casos_table.c.nome)).fetchall()
        return [_row_to_caso(r) for r in rows]

    @staticmethod
    def atualizar(caso: Caso) -> None:
        """Atualiza os dados de um caso existente."""
        caso.updated_at = datetime.now()
        with get_session() as conn:
            conn.execute(
                update(casos_table)
                .where(casos_table.c.id == caso.id)
                .values(
                    nome=caso.nome,
                    cpf=caso.cpf,
                    sexo=caso.sexo.value,
                    data_nascimento=caso.data_nascimento.isoformat(),
                    data_filiacao_rgps=caso.data_filiacao_rgps.isoformat() if caso.data_filiacao_rgps else None,
                    observacoes=caso.observacoes,
                    updated_at=caso.updated_at,
                )
            )

    @staticmethod
    def deletar(caso_id: int) -> None:
        """Remove um caso e todas as suas competências e documentos."""
        with get_session() as conn:
            conn.execute(delete(competencias_table).where(competencias_table.c.caso_id == caso_id))
            conn.execute(delete(documentos_table).where(documentos_table.c.caso_id == caso_id))
            conn.execute(delete(casos_table).where(casos_table.c.id == caso_id))


class CompetenciaRepository:

    @staticmethod
    def salvar(competencia: Competencia) -> int:
        """Persiste uma competência e retorna o ID gerado."""
        with get_session() as conn:
            result = conn.execute(insert(competencias_table).values(_comp_to_dict(competencia)))
            return result.lastrowid

    @staticmethod
    def salvar_lote(competencias: List[Competencia]) -> List[int]:
        """Persiste múltiplas competências em lote."""
        if not competencias:
            return []
        with get_session() as conn:
            ids: List[int] = []
            for c in competencias:
                r = conn.execute(insert(competencias_table).values(_comp_to_dict(c)))
                ids.append(r.lastrowid)
        return ids

    @staticmethod
    def buscar_por_caso(caso_id: int) -> List[Competencia]:
        """Retorna todas as competências de um caso."""
        with get_session() as conn:
            rows = conn.execute(
                select(competencias_table)
                .where(competencias_table.c.caso_id == caso_id)
                .order_by(competencias_table.c.competencia)
            ).fetchall()
        return [_row_to_comp(r) for r in rows]

    @staticmethod
    def buscar_por_fonte(caso_id: int, fonte: FonteDocumento) -> List[Competencia]:
        """Retorna competências de um caso filtradas por fonte."""
        with get_session() as conn:
            rows = conn.execute(
                select(competencias_table)
                .where(
                    competencias_table.c.caso_id == caso_id,
                    competencias_table.c.fonte == fonte.value,
                )
                .order_by(competencias_table.c.competencia)
            ).fetchall()
        return [_row_to_comp(r) for r in rows]

    @staticmethod
    def atualizar(competencia: Competencia) -> None:
        """Atualiza uma competência existente."""
        competencia.updated_at = datetime.now()
        d = _comp_to_dict(competencia)
        with get_session() as conn:
            conn.execute(
                update(competencias_table)
                .where(competencias_table.c.id == competencia.id)
                .values(**d)
            )

    @staticmethod
    def deletar(competencia_id: int) -> None:
        """Remove uma competência pelo ID."""
        with get_session() as conn:
            conn.execute(delete(competencias_table).where(competencias_table.c.id == competencia_id))


class DocumentoRepository:

    @staticmethod
    def salvar(documento: Documento) -> int:
        """Persiste um documento e retorna o ID gerado."""
        with get_session() as conn:
            result = conn.execute(
                insert(documentos_table).values(
                    caso_id=documento.caso_id,
                    nome_arquivo=documento.nome_arquivo,
                    caminho=documento.caminho,
                    tipo=documento.tipo.value,
                    status=documento.status.value,
                    erro_mensagem=documento.erro_mensagem,
                    texto_extraido=documento.texto_extraido,
                    importado_em=documento.importado_em,
                    processado_em=documento.processado_em,
                )
            )
            return result.lastrowid

    @staticmethod
    def buscar_por_caso(caso_id: int) -> List[Documento]:
        """Retorna todos os documentos de um caso."""
        with get_session() as conn:
            rows = conn.execute(
                select(documentos_table)
                .where(documentos_table.c.caso_id == caso_id)
                .order_by(documentos_table.c.importado_em)
            ).fetchall()
        return [_row_to_doc(r) for r in rows]

    @staticmethod
    def atualizar_status(documento_id: int, status: str, erro: Optional[str] = None) -> None:
        """Atualiza o status de processamento de um documento."""
        with get_session() as conn:
            conn.execute(
                update(documentos_table)
                .where(documentos_table.c.id == documento_id)
                .values(
                    status=status,
                    erro_mensagem=erro,
                    processado_em=datetime.now() if status in ("CONCLUIDO", "ERRO") else None,
                )
            )

    @staticmethod
    def atualizar_texto(documento_id: int, texto: str) -> None:
        """Salva o texto extraído do documento."""
        with get_session() as conn:
            conn.execute(
                update(documentos_table)
                .where(documentos_table.c.id == documento_id)
                .values(texto_extraido=texto)
            )


# ── helpers de conversão ────────────────────────────────────────────────────

def _row_to_caso(row) -> Caso:
    from datetime import date
    return Caso(
        id=row.id,
        nome=row.nome,
        cpf=row.cpf,
        sexo=Sexo(row.sexo),
        data_nascimento=date.fromisoformat(row.data_nascimento),
        data_filiacao_rgps=date.fromisoformat(row.data_filiacao_rgps) if row.data_filiacao_rgps else None,
        observacoes=row.observacoes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _comp_to_dict(c: Competencia) -> dict:
    return dict(
        caso_id=c.caso_id,
        competencia=c.competencia,
        tipo_vinculo=c.tipo_vinculo.value,
        empregador_nome=c.empregador_nome,
        empregador_cnpj_cpf=c.empregador_cnpj_cpf,
        remuneracao_bruta=str(c.remuneracao_bruta),
        base_contribuicao=str(c.base_contribuicao),
        aliquota=str(c.aliquota) if c.aliquota else None,
        valor_contribuicao=str(c.valor_contribuicao) if c.valor_contribuicao else None,
        remuneracao_atualizada=str(c.remuneracao_atualizada) if c.remuneracao_atualizada else None,
        fator_correcao=str(c.fator_correcao) if c.fator_correcao else None,
        data_calculo_correcao=c.data_calculo_correcao.isoformat() if c.data_calculo_correcao else None,
        fonte=c.fonte.value,
        documento_id=c.documento_id,
        confianca_extracao=c.confianca_extracao,
        editado_manualmente=c.editado_manualmente,
        flag_inconsistencia=c.flag_inconsistencia,
        descricao_inconsistencia=c.descricao_inconsistencia,
        flag_sobreposicao=c.flag_sobreposicao,
        flag_pendencia_cnis=c.flag_pendencia_cnis,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _row_to_comp(row) -> Competencia:
    from datetime import date
    return Competencia(
        id=row.id,
        caso_id=row.caso_id,
        competencia=row.competencia,
        tipo_vinculo=TipoVinculo(row.tipo_vinculo),
        empregador_nome=row.empregador_nome,
        empregador_cnpj_cpf=row.empregador_cnpj_cpf,
        remuneracao_bruta=Decimal(str(row.remuneracao_bruta)),
        base_contribuicao=Decimal(str(row.base_contribuicao)),
        aliquota=Decimal(str(row.aliquota)) if row.aliquota else None,
        valor_contribuicao=Decimal(str(row.valor_contribuicao)) if row.valor_contribuicao else None,
        remuneracao_atualizada=Decimal(str(row.remuneracao_atualizada)) if row.remuneracao_atualizada else None,
        fator_correcao=Decimal(str(row.fator_correcao)) if row.fator_correcao else None,
        data_calculo_correcao=date.fromisoformat(row.data_calculo_correcao) if row.data_calculo_correcao else None,
        fonte=FonteDocumento(row.fonte),
        documento_id=row.documento_id,
        confianca_extracao=row.confianca_extracao,
        editado_manualmente=bool(row.editado_manualmente),
        flag_inconsistencia=bool(row.flag_inconsistencia),
        descricao_inconsistencia=row.descricao_inconsistencia,
        flag_sobreposicao=bool(row.flag_sobreposicao),
        flag_pendencia_cnis=bool(row.flag_pendencia_cnis),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_doc(row) -> Documento:
    return Documento(
        id=row.id,
        caso_id=row.caso_id,
        nome_arquivo=row.nome_arquivo,
        caminho=row.caminho,
        tipo=TipoDocumento(row.tipo),
        status=StatusDocumento(row.status),
        erro_mensagem=row.erro_mensagem,
        texto_extraido=row.texto_extraido,
        importado_em=row.importado_em,
        processado_em=row.processado_em,
    )
