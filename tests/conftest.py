# -*- coding: utf-8 -*-
"""Torna motor/ importavel pelos testes (CI do painel-gof-baaplog)."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MOTOR = str(RAIZ / "motor")
if MOTOR not in sys.path:
    sys.path.insert(0, MOTOR)
