from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class Sexo(str, Enum):
    MASCULINO = "M"
    FEMININO = "F"


@dataclass
class Caso:
    """Dados do segurado / cliente."""

    nome: str
    cpf: str
    sexo: Sexo
    data_nascimento: date

    id: Optional[int] = None
    data_filiacao_rgps: Optional[date] = None
    observacoes: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
