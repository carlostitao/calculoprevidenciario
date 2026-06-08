"""Entrypoint do Sistema de Análise Previdenciária."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# Adiciona o diretório raiz ao path para imports absolutos
sys.path.insert(0, str(Path(__file__).parent.parent))

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# --- CORREÇÃO DO ERRO DE DIRETÓRIO ---
# Define e garante a existência da pasta de logs antes de inicializar o logging
log_dir = Path.home() / ".previdencia_app" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
# --------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Iniciando Sistema de Análise Previdenciária")

    from .db import init_db
    init_db()

    from .ui.app import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()