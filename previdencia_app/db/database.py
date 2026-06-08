from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, MetaData, Numeric, String,
    Table, Text, create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from ..config import DB_PATH

logger = logging.getLogger(__name__)

_DB_URL = f"sqlite:///{DB_PATH}"

engine: Engine = create_engine(
    _DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)

metadata = MetaData()

casos_table = Table(
    "casos", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nome", String(255), nullable=False),
    Column("cpf", String(14), nullable=False, unique=True),
    Column("sexo", String(1), nullable=False),
    Column("data_nascimento", String(10), nullable=False),
    Column("data_filiacao_rgps", String(10)),
    Column("observacoes", Text),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

documentos_table = Table(
    "documentos", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("caso_id", Integer, nullable=False),
    Column("nome_arquivo", String(512), nullable=False),
    Column("caminho", Text, nullable=False),
    Column("tipo", String(32), nullable=False),
    Column("status", String(32), nullable=False, default="AGUARDANDO"),
    Column("erro_mensagem", Text),
    Column("texto_extraido", Text),
    Column("importado_em", DateTime, nullable=False),
    Column("processado_em", DateTime),
)

competencias_table = Table(
    "competencias", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("caso_id", Integer, nullable=False),
    Column("competencia", String(7), nullable=False),
    Column("tipo_vinculo", String(32), nullable=False),
    Column("empregador_nome", String(512), nullable=False),
    Column("empregador_cnpj_cpf", String(20)),
    Column("remuneracao_bruta", Numeric(14, 2), nullable=False),
    Column("base_contribuicao", Numeric(14, 2), nullable=False),
    Column("aliquota", Numeric(6, 4)),
    Column("valor_contribuicao", Numeric(14, 2)),
    Column("remuneracao_atualizada", Numeric(14, 2)),
    Column("fator_correcao", Numeric(12, 8)),
    Column("data_calculo_correcao", String(10)),
    Column("fonte", String(32), nullable=False),
    Column("documento_id", Integer),
    Column("confianca_extracao", Float, nullable=False, default=1.0),
    Column("editado_manualmente", Boolean, nullable=False, default=False),
    Column("flag_inconsistencia", Boolean, nullable=False, default=False),
    Column("descricao_inconsistencia", Text),
    Column("flag_sobreposicao", Boolean, nullable=False, default=False),
    Column("flag_pendencia_cnis", Boolean, nullable=False, default=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

inpc_cache_table = Table(
    "inpc_cache", metadata,
    Column("competencia", String(7), primary_key=True),
    Column("variacao_percentual", Float, nullable=False),
    Column("data_consulta", String(10), nullable=False),
)

ai_log_table = Table(
    "ai_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, nullable=False),
    Column("modelo", String(64), nullable=False),
    Column("operacao", String(64), nullable=False),
    Column("tokens_input", Integer, nullable=False),
    Column("tokens_output", Integer, nullable=False),
    Column("custo_usd", Float, nullable=False),
    Column("caso_id", Integer),
)


def init_db() -> None:
    """Cria todas as tabelas se ainda não existirem."""
    metadata.create_all(engine)
    logger.info("Banco de dados inicializado em %s", DB_PATH)


@contextmanager
def get_session() -> Generator:
    """Context manager thread-safe para conexões."""
    with engine.connect() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
