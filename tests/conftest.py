# -*- coding: utf-8 -*-
"""Torna motor/ importavel pelos testes (CI do painel-gof-baaplog)."""
import json
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
MOTOR = str(RAIZ / "motor")
if MOTOR not in sys.path:
    sys.path.insert(0, MOTOR)

# v2.3 (replicavel): a suite testa o MOTOR com a configuracao de referencia da BaApLog, fixada aqui, e nao com o
# config/om.json da OM que usa o repositorio. Assim uma copia para outra OM (ex.: a DF) troca o config/om.json e a suite
# continua valendo. Os modulos leem o config na importacao: isto precisa rodar antes de qualquer import do motor.
CONFIG_REFERENCIA = RAIZ / "tests" / "dados" / "baaplog" / "om.json"
os.environ["GOF_CONFIG"] = str(CONFIG_REFERENCIA)


def _repositorio_da_baaplog():
    try:
        return json.loads((RAIZ / "config" / "om.json").read_text(encoding="utf-8")).get("id") == "baaplog"
    except (OSError, ValueError):
        return False


REPOSITORIO_BAAPLOG = _repositorio_da_baaplog()


def pytest_configure(config):
    config.addinivalue_line("markers", "dados_baaplog: le dados/ reais da BaApLog; pulado em copia para outra OM")


def pytest_collection_modifyitems(config, items):
    # no repositorio da BaApLog nada e pulado (dado ausente reprova); numa copia para outra OM, os testes que conferem
    # numeros reais da BaApLog (LOG-120, LOG-131, capacidade, dispensa) nao se aplicam e sao pulados com motivo
    if REPOSITORIO_BAAPLOG:
        return
    pula = pytest.mark.skip(reason="dados reais da BaApLog: so no repositorio da BaApLog (config/om.json com id baaplog)")
    for item in items:
        if "dados_baaplog" in item.keywords:
            item.add_marker(pula)
