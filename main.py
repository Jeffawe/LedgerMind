from __future__ import annotations

import os
from dotenv import load_dotenv
from logs import configure_logging

load_dotenv()
configure_logging(os.getenv("LOG_LEVEL"))

from interface.api import app
from interface.cli import main as cli_main

if __name__ == "__main__":
    cli_main()
