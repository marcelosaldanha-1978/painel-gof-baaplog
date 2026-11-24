# -*- coding: utf-8 -*-
"""
gof_vigia.py (v1, 07nov2026) — vigia do painel (D18, PLANO v2.4).

Lê a última montagem publicada (`dados/painel/ultimo/dados.json`) e responde, em dias ÚTEIS (seg a sex, sem feriados):
  - há quantos dias úteis a montagem não acontece (meta.hoje);
  - há quantos dias úteis o dado do B1 está parado (b1.data_dado).
  - (v2, 23nov2026) há quantos dias úteis a régua do encerramento está parada (regua.data_dado);
  - (v2) com --runs: se dado novo chegou nos últimos 5 dias úteis e nenhuma montagem por evento (repository_dispatch,
    acionada pela ponte do TG) teve sucesso — a cadeia nova quebrou em silêncio e a página sai só pela agenda.
Sai com código 1 se qualquer verificação passou do limite (2 dias úteis), para o workflow abrir uma issue.
Com --outubro, sai com 1 sempre que o mês for outubro: lembrete de recadastrar a subscrição do TG antes de 31/10.
Uso: python gof_vigia.py --dados dados/painel/ultimo/dados.json [--hoje AAAA-MM-DD] [--limite 2] [--outubro] [--json saida.json]
"""
import argparse
import datetime as dt
import json
import sys
from zoneinfo import ZoneInfo

from gof_painel import dias_uteis


def inicio_janela(hoje, n):
    """Data a partir da qual há `n` dias úteis até `hoje` (exclusivo o início)."""
    d = hoje
    while dias_uteis(d, hoje) < n:
        d -= dt.timedelta(days=1)
    return d


def avaliar_disparo(runs, hoje, ultimo_dado, janela=5):
    """v2 (23nov2026): a ponte do TG aciona a montagem por evento (repository_dispatch). Se dado novo chegou na janela
    de `janela` dias úteis e NENHUMA montagem por evento teve sucesso nela, a cadeia nova quebrou em silêncio (token
    vencido, Apps Script sem autorização) e a publicação está saindo só pela agenda, horas depois.
    runs: [{"event", "conclusion", "created_at"}] da API de execuções do workflow de montagem."""
    ini = inicio_janela(hoje, janela)
    ok_evento = [x for x in runs if x.get("event") == "repository_dispatch" and x.get("conclusion") == "success"
                 and dt.date.fromisoformat(str(x.get("created_at", ""))[:10]) > ini]
    dado_novo = ultimo_dado is not None and ultimo_dado >= ini
    return {"janela_desde": ini.isoformat(), "montagens_por_evento_ok": len(ok_evento), "dado_novo_na_janela": dado_novo,
            "disparo_ok": bool(ok_evento) or not dado_novo}


def avaliar(dados, hoje, limite, runs=None):
    montagem = dt.date.fromisoformat(dados["meta"]["hoje"])
    b1 = dt.date.fromisoformat(dados["b1"]["data_dado"])
    r = {"hoje": hoje.isoformat(), "limite_dias_uteis": limite,
         "ultima_montagem": montagem.isoformat(), "dias_uteis_sem_montagem": dias_uteis(montagem, hoje),
         "data_b1": b1.isoformat(), "dias_uteis_b1_parado": dias_uteis(b1, hoje), "fonte_b1": dados["meta"].get("fonte_b1", "tg")}
    r["montagem_ok"] = r["dias_uteis_sem_montagem"] <= limite
    r["b1_ok"] = r["dias_uteis_b1_parado"] <= limite
    # v2: régua do encerramento (crédito em tela, vencido, RPNP) também não pode parar
    rg = (dados.get("regua") or {}).get("data_dado")
    regua = dt.date.fromisoformat(rg) if rg else None
    r["data_regua"] = regua.isoformat() if regua else None
    r["dias_uteis_regua_parada"] = dias_uteis(regua, hoje) if regua else None
    r["regua_ok"] = regua is None or r["dias_uteis_regua_parada"] <= limite
    r["disparo"] = None
    if runs is not None:
        r["disparo"] = avaliar_disparo(runs, hoje, max(x for x in (b1, regua) if x is not None))
    r["disparo_ok"] = r["disparo"] is None or r["disparo"]["disparo_ok"]
    r["ok"] = r["montagem_ok"] and r["b1_ok"] and r["regua_ok"] and r["disparo_ok"]
    return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", required=True)
    ap.add_argument("--hoje", default=None)
    ap.add_argument("--limite", type=int, default=2)
    ap.add_argument("--outubro", action="store_true")
    ap.add_argument("--json", default=None)
    ap.add_argument("--runs", default=None, help="JSON com as execuções do workflow de montagem (event, conclusion, created_at)")
    o = ap.parse_args(argv)
    # data de Brasília: o runner do GitHub está em UTC e, à noite, já estaria no dia seguinte
    hoje = dt.date.fromisoformat(o.hoje) if o.hoje else dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    runs = None
    if o.runs:
        try:
            with open(o.runs, encoding="utf-8") as f:
                runs = json.load(f)
        except (OSError, ValueError):
            runs = None
    r = avaliar(json.load(open(o.dados, encoding="utf-8")), hoje, o.limite, runs)
    r["lembrete_tg"] = bool(o.outubro and hoje.month == 10)
    if o.json:
        with open(o.json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    rg = ("régua de %s (%d dias úteis)" % (r["data_regua"], r["dias_uteis_regua_parada"])) if r["data_regua"] else "régua ausente"
    dp = r["disparo"]
    dtxt = ("; disparo por evento: %d montagem(ns) ok desde %s%s" % (dp["montagens_por_evento_ok"], dp["janela_desde"],
            "" if dp["disparo_ok"] else " — ALERTA: dado novo chegou e a ponte não acionou a montagem (token vencido? Apps Script sem autorização?)")
            ) if dp else ""
    print("VIGIA %s: última montagem %s (%d dias úteis), B1 de %s (%d dias úteis, fonte %s), %s%s%s"
          % ("ok" if r["ok"] else "ALERTA", r["ultima_montagem"], r["dias_uteis_sem_montagem"], r["data_b1"],
             r["dias_uteis_b1_parado"], r["fonte_b1"], rg, dtxt,
             "; LEMBRETE: recadastrar a subscrição do TG antes de 31/10" if r["lembrete_tg"] else ""))
    return 0 if (r["ok"] and not r["lembrete_tg"]) else 1


if __name__ == "__main__":
    sys.exit(main())
