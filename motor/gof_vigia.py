# -*- coding: utf-8 -*-
"""
gof_vigia.py (v1, 07nov2026) — vigia do painel (D18, PLANO v2.4).

Lê a última montagem publicada (`dados/painel/ultimo/dados.json`) e responde, em dias ÚTEIS (seg a sex, sem feriados):
  - há quantos dias úteis a montagem não acontece (meta.hoje);
  - há quantos dias úteis o dado do B1 está parado (b1.data_dado).
Sai com código 1 se qualquer um dos dois passou do limite (2 dias úteis), para o workflow semanal abrir uma issue.
Com --outubro, sai com 1 sempre que o mês for outubro: lembrete de recadastrar a subscrição do TG antes de 31/10.
Uso: python gof_vigia.py --dados dados/painel/ultimo/dados.json [--hoje AAAA-MM-DD] [--limite 2] [--outubro] [--json saida.json]
"""
import argparse
import datetime as dt
import json
import sys

from gof_painel import dias_uteis


def avaliar(dados, hoje, limite):
    montagem = dt.date.fromisoformat(dados["meta"]["hoje"])
    b1 = dt.date.fromisoformat(dados["b1"]["data_dado"])
    r = {"hoje": hoje.isoformat(), "limite_dias_uteis": limite,
         "ultima_montagem": montagem.isoformat(), "dias_uteis_sem_montagem": dias_uteis(montagem, hoje),
         "data_b1": b1.isoformat(), "dias_uteis_b1_parado": dias_uteis(b1, hoje), "fonte_b1": dados["meta"].get("fonte_b1", "tg")}
    r["montagem_ok"] = r["dias_uteis_sem_montagem"] <= limite
    r["b1_ok"] = r["dias_uteis_b1_parado"] <= limite
    r["ok"] = r["montagem_ok"] and r["b1_ok"]
    return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", required=True)
    ap.add_argument("--hoje", default=None)
    ap.add_argument("--limite", type=int, default=2)
    ap.add_argument("--outubro", action="store_true")
    ap.add_argument("--json", default=None)
    o = ap.parse_args(argv)
    hoje = dt.date.fromisoformat(o.hoje) if o.hoje else dt.date.today()
    r = avaliar(json.load(open(o.dados, encoding="utf-8")), hoje, o.limite)
    r["lembrete_tg"] = bool(o.outubro and hoje.month == 10)
    if o.json:
        with open(o.json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    print("VIGIA %s: última montagem %s (%d dias úteis), B1 de %s (%d dias úteis, fonte %s)%s"
          % ("ok" if r["ok"] else "ALERTA", r["ultima_montagem"], r["dias_uteis_sem_montagem"], r["data_b1"],
             r["dias_uteis_b1_parado"], r["fonte_b1"], "; LEMBRETE: recadastrar a subscrição do TG antes de 31/10" if r["lembrete_tg"] else ""))
    return 0 if (r["ok"] and not r["lembrete_tg"]) else 1


if __name__ == "__main__":
    sys.exit(main())
