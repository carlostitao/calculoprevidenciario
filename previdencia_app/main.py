"""Entrypoint do Sistema de Análise Previdenciária."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path para imports absolutos
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path.home() / ".previdencia_app" / "logs" / "app.log", encoding="utf-8"),
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
