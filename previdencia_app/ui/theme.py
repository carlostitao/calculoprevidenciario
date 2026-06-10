"""Design tokens e helpers de estilo — usados em todos os painéis."""
from __future__ import annotations
import customtkinter as ctk

# ── Paleta principal ─────────────────────────────────────────────────────────
AZUL_PRIMARIO   = "#1a6fad"
AZUL_CLARO      = "#4a9eff"
VERDE_OK        = "#2ecc71"
VERDE_ESCURO    = "#27ae60"
AMARELO         = "#f0a500"
VERMELHO        = "#e74c3c"
VERMELHO_ESCURO = "#c0392b"
ROXO            = "#9b59b6"
CINZA_TEXTO     = "#888888"

# Fundos adaptativos (dark / light)
BG_CARD    = ("#ffffff", "#1e1e2e")   # card principal
BG_CARD2   = ("#f5f7fa", "#252535")   # card secundário / alt
BG_HEADER  = ("#1a3a6b", "#0d1b35")   # cabeçalho azul escuro
BG_SEP     = ("#d0d5dd", "#2a2a3e")   # separadores

# ── Fontes ───────────────────────────────────────────────────────────────────
def font_titulo() -> ctk.CTkFont:
    return ctk.CTkFont(family="Segoe UI", size=20, weight="bold")

def font_secao() -> ctk.CTkFont:
    return ctk.CTkFont(family="Segoe UI", size=13, weight="bold")

def font_label() -> ctk.CTkFont:
    return ctk.CTkFont(family="Segoe UI", size=11)

def font_valor() -> ctk.CTkFont:
    return ctk.CTkFont(family="Segoe UI", size=11, weight="bold")

def font_destaque() -> ctk.CTkFont:
    return ctk.CTkFont(family="Segoe UI", size=18, weight="bold")

def font_pequeno() -> ctk.CTkFont:
    return ctk.CTkFont(family="Segoe UI", size=10)


# ── Widgets helpers ──────────────────────────────────────────────────────────

def secao_header(parent, texto: str, cor_texto: str = AZUL_CLARO) -> ctk.CTkFrame:
    """Cria um cabeçalho de seção com linha horizontal."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(frame, text=texto, font=font_secao(), text_color=cor_texto).pack(side="left")
    ctk.CTkFrame(frame, height=2, fg_color=cor_texto).pack(side="left", fill="x", expand=True, padx=(8, 0), pady=6)
    return frame


def card(parent, **kwargs) -> ctk.CTkFrame:
    """Frame com aparência de card."""
    defaults = dict(corner_radius=10, fg_color=BG_CARD, border_width=1, border_color=BG_SEP)
    defaults.update(kwargs)
    return ctk.CTkFrame(parent, **defaults)


def badge(parent, texto: str, cor: str, largura: int = 80) -> ctk.CTkLabel:
    """Label com aparência de badge/pill."""
    return ctk.CTkLabel(
        parent,
        text=texto,
        width=largura,
        height=24,
        corner_radius=12,
        fg_color=cor,
        text_color="#ffffff",
        font=font_pequeno(),
    )


def stat_box(parent, titulo: str, valor: str, cor_valor: str = AZUL_CLARO) -> ctk.CTkFrame:
    """Caixa de estatística com título + valor destacado."""
    box = ctk.CTkFrame(parent, corner_radius=8, fg_color=BG_CARD2, border_width=1, border_color=BG_SEP)
    ctk.CTkLabel(box, text=titulo, font=font_pequeno(), text_color=CINZA_TEXTO).pack(padx=12, pady=(8, 0))
    ctk.CTkLabel(box, text=valor, font=font_destaque(), text_color=cor_valor).pack(padx=12, pady=(0, 8))
    return box
