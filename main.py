from __future__ import annotations

import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from interface.api import app
from interface.cli import main as cli_main

if __name__ == "__main__":
    cli_main()
