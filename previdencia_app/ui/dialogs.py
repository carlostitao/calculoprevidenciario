"""Diálogos modais da aplicação."""
from __future__ import annotations

from datetime import date
from typing import Optional

import customtkinter as ctk

from ..db import CasoRepository
from ..models import Caso
from ..models.caso import Sexo


class NovoCasoDialog(ctk.CTkToplevel):

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title("Novo Caso")
        self.geometry("420x380")
        self.resizable(False, False)
        self.grab_set()

        self.resultado: Optional[Caso] = None
        self._build()

    def _build(self) -> None:
        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        frame.grid_columnconfigure(1, weight=1)

        campos = [
            ("Nome completo:", "entry_nome"),
            ("CPF (apenas números):", "entry_cpf"),
            ("Data nascimento (DD/MM/YYYY):", "entry_nasc"),
            ("Data filiação RGPS (DD/MM/YYYY):", "entry_fil"),
        ]
        self._entries: dict = {}
        for i, (label, key) in enumerate(campos):
            ctk.CTkLabel(frame, text=label, anchor="w").grid(row=i, column=0, sticky="w", pady=4, padx=4)
            entry = ctk.CTkEntry(frame, width=220)
            entry.grid(row=i, column=1, sticky="ew", pady=4, padx=4)
            self._entries[key] = entry

        ctk.CTkLabel(frame, text="Sexo:", anchor="w").grid(row=4, column=0, sticky="w", pady=4, padx=4)
        self._sexo_var = ctk.StringVar(value="M")
        frame_sexo = ctk.CTkFrame(frame, fg_color="transparent")
        frame_sexo.grid(row=4, column=1, sticky="w")
        ctk.CTkRadioButton(frame_sexo, text="Masculino", variable=self._sexo_var, value="M").pack(side="left", padx=4)
        ctk.CTkRadioButton(frame_sexo, text="Feminino", variable=self._sexo_var, value="F").pack(side="left", padx=4)

        self._lbl_erro = ctk.CTkLabel(frame, text="", text_color="red", wraplength=380)
        self._lbl_erro.grid(row=5, column=0, columnspan=2, pady=4)

        frame_btn = ctk.CTkFrame(frame, fg_color="transparent")
        frame_btn.grid(row=6, column=0, columnspan=2, pady=8)
        ctk.CTkButton(frame_btn, text="Salvar", command=self._salvar).pack(side="left", padx=8)
        ctk.CTkButton(frame_btn, text="Cancelar", command=self.destroy, fg_color="gray").pack(side="left", padx=8)

    def _salvar(self) -> None:
        nome = self._entries["entry_nome"].get().strip()
        cpf = self._entries["entry_cpf"].get().strip().replace(".", "").replace("-", "")
        nasc_str = self._entries["entry_nasc"].get().strip()
        fil_str = self._entries["entry_fil"].get().strip()

        if not nome or not cpf or not nasc_str:
            self._lbl_erro.configure(text="Nome, CPF e data de nascimento são obrigatórios.")
            return

        try:
            d, m, a = nasc_str.split("/")
            data_nasc = date(int(a), int(m), int(d))
        except ValueError:
            self._lbl_erro.configure(text="Data de nascimento inválida. Use DD/MM/YYYY.")
            return

        data_fil: Optional[date] = None
        if fil_str:
            try:
                d, m, a = fil_str.split("/")
                data_fil = date(int(a), int(m), int(d))
            except ValueError:
                self._lbl_erro.configure(text="Data de filiação inválida. Use DD/MM/YYYY.")
                return

        caso = Caso(
            nome=nome,
            cpf=cpf,
            sexo=Sexo(self._sexo_var.get()),
            data_nascimento=data_nasc,
            data_filiacao_rgps=data_fil,
        )
        try:
            caso_id = CasoRepository.criar(caso)
            caso.id = caso_id
            self.resultado = caso
            self.destroy()
        except Exception as exc:
            self._lbl_erro.configure(text=f"Erro ao salvar: {exc}")


class AdicionarCompetenciaDialog(ctk.CTkToplevel):
    """Formulário modal para inserção manual de competência."""

    def __init__(self, parent, caso_id: int) -> None:
        super().__init__(parent)
        self.title("Adicionar Competência")
        self.geometry("460x480")
        self.resizable(False, False)
        self.grab_set()
        self.resultado = None
        self._caso_id = caso_id
        self._build()

    def _build(self) -> None:
        from ..models import TipoVinculo, FonteDocumento
        from decimal import Decimal
        from datetime import datetime

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        frame.grid_columnconfigure(1, weight=1)

        campos = [
            ("Competência (MM/YYYY):", "comp"),
            ("Empregador:", "emp"),
            ("CNPJ/CPF:", "cnpj"),
            ("Remuneração bruta (R$):", "rem"),
            ("Base contribuição (R$):", "base"),
            ("Valor INSS (R$):", "inss"),
        ]
        self._entries: dict = {}
        for i, (lbl, key) in enumerate(campos):
            ctk.CTkLabel(frame, text=lbl, anchor="w").grid(row=i, column=0, sticky="w", pady=3, padx=4)
            e = ctk.CTkEntry(frame, width=220)
            e.grid(row=i, column=1, sticky="ew", pady=3, padx=4)
            self._entries[key] = e

        row = len(campos)
        ctk.CTkLabel(frame, text="Tipo vínculo:", anchor="w").grid(row=row, column=0, sticky="w", pady=3, padx=4)
        self._tipo_var = ctk.StringVar(value="CLT")
        tipos = [t.value for t in TipoVinculo]
        ctk.CTkComboBox(frame, variable=self._tipo_var, values=tipos, width=220).grid(row=row, column=1, sticky="ew", pady=3, padx=4)

        self._lbl_erro = ctk.CTkLabel(frame, text="", text_color="red", wraplength=420)
        self._lbl_erro.grid(row=row + 1, column=0, columnspan=2, pady=4)

        frame_btn = ctk.CTkFrame(frame, fg_color="transparent")
        frame_btn.grid(row=row + 2, column=0, columnspan=2, pady=8)
        ctk.CTkButton(frame_btn, text="Adicionar", command=self._salvar).pack(side="left", padx=8)
        ctk.CTkButton(frame_btn, text="Cancelar", command=self.destroy, fg_color="gray").pack(side="left", padx=8)

    def _salvar(self) -> None:
        from ..models import Competencia, TipoVinculo, FonteDocumento
        from decimal import Decimal
        from datetime import datetime

        comp = self._entries["comp"].get().strip()
        emp = self._entries["emp"].get().strip()
        if not comp or not emp:
            self._lbl_erro.configure(text="Competência e Empregador são obrigatórios.")
            return

        try:
            Decimal(self._entries["rem"].get() or "0")
        except Exception:
            self._lbl_erro.configure(text="Remuneração inválida.")
            return

        rem = Decimal(self._entries["rem"].get() or "0")
        base = Decimal(self._entries["base"].get() or str(rem))
        inss_str = self._entries["inss"].get().strip()
        inss = Decimal(inss_str) if inss_str else None

        self.resultado = Competencia(
            caso_id=self._caso_id,
            competencia=comp,
            tipo_vinculo=TipoVinculo(self._tipo_var.get()),
            empregador_nome=emp,
            empregador_cnpj_cpf=self._entries["cnpj"].get().strip() or None,
            remuneracao_bruta=rem,
            base_contribuicao=base,
            valor_contribuicao=inss,
            fonte=FonteDocumento.MANUAL,
            confianca_extracao=1.0,
            editado_manualmente=True,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.destroy()
