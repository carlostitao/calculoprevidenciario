import os
from pathlib import Path

# API Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_EXTRACAO = "claude-haiku-4-5-20251001"
MODEL_ANALISE = "claude-sonnet-4-6"

# Banco
DB_PATH = Path.home() / ".previdencia_app" / "dados.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Logs
LOG_PATH = Path.home() / ".previdencia_app" / "logs"
LOG_PATH.mkdir(parents=True, exist_ok=True)

# BCB/SGS
BCB_SERIE_INPC = 188
BCB_SERIE_IPCA = 433
BCB_API_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs"

# Previdenciário
DATA_REFORMA = "13/11/2019"          # EC 103/2019
DATA_INICIO_COMPETENCIAS = "07/1994" # início do período para média de contribuições

# Limites vigentes (atualizar anualmente via portaria)
TETO_RGPS_ATUAL = 7786.02
SALARIO_MINIMO_ATUAL = 1518.00

# Histórico de salários mínimos (MM/YYYY -> valor)
HISTORICO_SALARIO_MINIMO: dict[str, float] = {
    "01/1994": 64.79, "03/1994": 70.57, "07/1994": 70.00,
    "09/1994": 70.00, "04/1995": 100.00, "05/1995": 100.00,
    "05/1996": 112.00, "05/1997": 120.00, "05/1998": 130.00,
    "05/1999": 136.00, "04/2000": 151.00, "04/2001": 180.00,
    "04/2002": 200.00, "04/2003": 240.00, "05/2004": 260.00,
    "05/2005": 300.00, "04/2006": 350.00, "04/2007": 380.00,
    "03/2008": 415.00, "02/2009": 465.00, "01/2010": 510.00,
    "03/2011": 545.00, "01/2012": 622.00, "01/2013": 678.00,
    "01/2014": 724.00, "01/2015": 788.00, "01/2016": 880.00,
    "01/2017": 937.00, "01/2018": 954.00, "01/2019": 998.00,
    "02/2020": 1045.00, "01/2021": 1100.00, "01/2022": 1212.00,
    "05/2023": 1320.00, "01/2024": 1412.00, "01/2025": 1518.00,
}

# Histórico de tetos do RGPS (MM/YYYY -> valor)
HISTORICO_TETO_RGPS: dict[str, float] = {
    "07/1994": 636.00, "08/1994": 636.00,
    "03/1995": 831.29, "08/1995": 857.07,
    "04/1996": 957.87, "06/1997": 1031.87,
    "06/1998": 1081.50, "06/1999": 1255.32,
    "06/2000": 1328.25, "01/2001": 1430.00,
    "06/2001": 1430.00, "01/2002": 1561.56,
    "06/2002": 1561.56, "06/2003": 1869.34,
    "05/2004": 2508.72, "05/2005": 2668.15,
    "04/2006": 2801.82, "04/2007": 2894.28,
    "03/2008": 3038.99, "02/2009": 3218.90,
    "01/2010": 3416.54, "01/2011": 3691.74,
    "01/2012": 3916.20, "01/2013": 4159.00,
    "01/2014": 4390.24, "01/2015": 4663.75,
    "01/2016": 5189.82, "01/2017": 5531.31,
    "01/2018": 5645.80, "01/2019": 5839.45,
    "01/2020": 6101.06, "01/2021": 6433.57,
    "01/2022": 7087.22, "05/2023": 7786.02,
    "01/2024": 7786.02, "01/2025": 7786.02,
}

# Relatório
RESPONSAVEL_RELATORIO = "Carlos Eduardo Pereira Titão — OAB/SC nº 73.659"

# UI
UI_APARENCIA_PADRAO = "dark"
UI_TEMA_COR = "blue"
UI_LARGURA_MIN = 1280
UI_ALTURA_MIN = 720
