from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TipoDocumento(str, Enum):
    CNIS = "CNIS"
    CTPS = "CTPS"
    CTC = "CTC"
    HOLERITE = "HOLERITE"
    PRO_LABORE = "PRO_LABORE"
    PGDAS_MEI = "PGDAS_MEI"
    DARF = "DARF"
    FGTS = "FGTS"
    DESCONHECIDO = "DESCONHECIDO"


class StatusDocumento(str, Enum):
    AGUARDANDO = "AGUARDANDO"
    PROCESSANDO = "PROCESSANDO"
    CONCLUIDO = "CONCLUIDO"
    ERRO = "ERRO"


@dataclass
class Documento:
    """Documento importado pelo usuário."""

    caso_id: int
    nome_arquivo: str
    caminho: str
    tipo: TipoDocumento
    status: StatusDocumento = StatusDocumento.AGUARDANDO

    id: Optional[int] = None
    erro_mensagem: Optional[str] = None
    texto_extraido: Optional[str] = None
    importado_em: datetime = field(default_factory=datetime.now)
    processado_em: Optional[datetime] = None
