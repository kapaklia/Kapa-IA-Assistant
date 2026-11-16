#!/usr/bin/env python3
"""Comando di servizio di Kapa, eseguibile da qualsiasi cartella."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == '__main__':
    from kapa.configura_scorciatoia import main
    raise SystemExit(main())
