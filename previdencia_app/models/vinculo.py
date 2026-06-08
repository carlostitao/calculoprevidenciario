from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .competencia import TipoVinculo


@dataclass
class Vinculo:
    """Período de vínculo empregatício ou contributivo."""

    caso_id: int
    empregador_nome: str
    tipo_vinculo: TipoVinculo
    data_inicio: str   # "MM/YYYY"
    data_fim: Optional[str]  # "MM/YYYY" ou None se em aberto

    id: Optional[int] = None
    empregador_cnpj_cpf: Optional[str] = None
    documento_id: Optional[int] = None
