from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class TipoVinculo(str, Enum):
    CLT = "CLT"
    AUTONOMO = "AUTONOMO"
    MEI = "MEI"
    PRO_LABORE = "PRO_LABORE"
    FACULTATIVO = "FACULTATIVO"
    RPPS = "RPPS"
    RURAL = "RURAL"


class FonteDocumento(str, Enum):
    CNIS = "CNIS"
    CTPS = "CTPS"
    CTC = "CTC"
    HOLERITE = "HOLERITE"
    PRO_LABORE = "PRO_LABORE"
    PGDAS = "PGDAS"
    DARF = "DARF"
    FGTS = "FGTS"
    MANUAL = "MANUAL"


@dataclass
class Competencia:
    """Schema central unificado. Todo dado extraído de qualquer fonte é normalizado aqui."""

    caso_id: int
    competencia: str  # "MM/YYYY"
    tipo_vinculo: TipoVinculo
    empregador_nome: str
    remuneracao_bruta: Decimal
    base_contribuicao: Decimal
    fonte: FonteDocumento
    confianca_extracao: float  # 0.0 a 1.0

    id: Optional[int] = None
    empregador_cnpj_cpf: Optional[str] = None
    aliquota: Optional[Decimal] = None
    valor_contribuicao: Optional[Decimal] = None

    # Atualização monetária (calculada pelo engine)
    remuneracao_atualizada: Optional[Decimal] = None
    fator_correcao: Optional[Decimal] = None
    data_calculo_correcao: Optional[date] = None

    # Rastreabilidade
    documento_id: Optional[int] = None
    editado_manualmente: bool = False

    # Flags de análise
    flag_inconsistencia: bool = False
    descricao_inconsistencia: Optional[str] = None
    flag_sobreposicao: bool = False
    # Pendência do CNIS — NUNCA impede cálculo, apenas informativo
    flag_pendencia_cnis: bool = False

    # Metadados
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
