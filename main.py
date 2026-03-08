from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from logs import configure_logging

load_dotenv()
configure_logging(os.getenv("LOG_LEVEL"))

from interface.api import app
from interface.cli import main as cli_main

if __name__ == "__main__":
    cli_main()
