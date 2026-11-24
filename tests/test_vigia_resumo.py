# -*- coding: utf-8 -*-
"""Testes do vigia v2 (régua e disparo por evento) e do resumo da execução (23/11/2026)."""
import datetime as dt

import gof_vigia as v
import resumo_execucao as r

DADOS = {"meta": {"hoje": "2026-11-23", "fonte_b1": "tg"}, "b1": {"data_dado": "2026-11-19"},
         "regua": {"data_dado": "2026-11-20"}}
HOJE = dt.date(2026, 11, 24)


def run(evento, data, conclusao="success"):
    return {"event": evento, "conclusion": conclusao, "created_at": data + "T09:11:06Z"}


def test_sem_runs_mantem_comportamento_e_mede_regua():
    x = v.avaliar(DADOS, HOJE, 2)
    assert x["disparo"] is None and x["disparo_ok"]
    assert x["data_regua"] == "2026-11-20" and x["dias_uteis_regua_parada"] == 2 and x["regua_ok"]


def test_regua_parada_alerta():
    x = v.avaliar(DADOS, dt.date(2026, 11, 26), 2)
    assert not x["regua_ok"] and not x["ok"]


def test_regua_ausente_nao_alerta():
    d = {k: x for k, x in DADOS.items() if k != "regua"}
    x = v.avaliar(d, HOJE, 2)
    assert x["regua_ok"] and x["data_regua"] is None


def test_dado_novo_sem_evento_alerta():
    runs = [run("schedule", "2026-11-23"), run("repository_dispatch", "2026-11-10")]
    x = v.avaliar(DADOS, HOJE, 2, runs)
    assert x["disparo"]["dado_novo_na_janela"] and not x["disparo_ok"] and not x["ok"]


def test_dado_novo_com_evento_ok():
    x = v.avaliar(DADOS, HOJE, 2, [run("repository_dispatch", "2026-11-24")])
    assert x["disparo_ok"]


def test_evento_que_falhou_nao_conta():
    x = v.avaliar(DADOS, HOJE, 2, [run("repository_dispatch", "2026-11-24", "failure")])
    assert not x["disparo_ok"]


def test_sem_dado_novo_nao_cobra_evento():
    d = {"meta": {"hoje": "2026-11-23"}, "b1": {"data_dado": "2026-11-10"}, "regua": {"data_dado": "2026-11-10"}}
    x = v.avaliar(d, HOJE, 2, [])
    assert x["disparo_ok"] and not x["disparo"]["dado_novo_na_janela"]


def test_resumo_tabela():
    log = "2026-11-24T02:11:28.1Z PONTE: par de 2026-11-20 nada a fazer\nREGUA: dados até 2026-11-20 — em tela R$ 1 | x\n"
    md = r.montar([log], DADOS, "repository_dispatch", "success")
    assert "✅" in md and "evento (ponte do TG)" in md and "até 2026-11-19" in md
    assert "| Ponte | par de 2026-11-20 nada a fazer |" in md
    assert "em tela R$ 1 / x" in md  # barra vertical não quebra a tabela
    assert "| Navegador | — |" in md


def test_resumo_falha_e_sem_dados():
    md = r.montar([], None, "schedule", "failure")
    assert "⛔" in md and "agenda (reserva)" in md and "não publicada" in md
