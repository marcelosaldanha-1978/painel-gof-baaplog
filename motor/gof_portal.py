# -*- coding: utf-8 -*-
"""
gof_portal.py (v1, 07nov2026) — Portal da Transparência como RESERVA do B1 (D17 revista, PLANO v2.4; P-039).

Coleta os empenhos (fase 1) das 12 UG (160xxx e 167xxx) numa janela de dias úteis, faz o vínculo NE -> pregão com as
fichas PNCP e grava um EXTRATO SEM PESSOA no mesmo formato do extrato do TG (`gof_painel.gerar_extrato`), mesclado ao
extrato anterior: dentro da janela o Portal manda (NE anulada some, NE nova entra); fora da janela fica o que havia.
NE com valor 0,00 no Portal não entram (regra 5 do plano); a contagem das retiradas fica em `meta`.
`data_execucao` = último dia de emissão presente no extrato (é com ela que a D17 escolhe a fonte).
A chave da API vem só de PORTAL_TRANSPARENCIA_API_KEY; nunca é impressa.
Uso: python gof_portal.py --fichas dados/pncp/ultimo.json --saida dados/portal [--dias-uteis 10 | --desde AAAA-MM-DD] [--ate AAAA-MM-DD]
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import gcalc_transparencia as tr
import gof_painel as gp

ARQ = "extrato_portal.json"


def janela(ate, dias_uteis):
    d, n = ate, 0
    while n < dias_uteis:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return d


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fichas", required=True)
    ap.add_argument("--saida", default="dados/portal")
    ap.add_argument("--dias-uteis", type=int, default=10, help="janela recoletada a cada dia (o Portal atrasa ~7 dias)")
    ap.add_argument("--desde", default=None, help="início fixo (carga inicial); ignora --dias-uteis")
    ap.add_argument("--ate", default=None)
    o = ap.parse_args(argv)
    ate = dt.date.fromisoformat(o.ate) if o.ate else dt.date.today()
    desde = dt.date.fromisoformat(o.desde) if o.desde else janela(ate, o.dias_uteis)
    fichas = tr.ficha_de_pncp(json.load(open(o.fichas, encoding="utf-8")))
    regs, falhas = tr.coletar(desde, ate)
    if falhas:
        print("PORTAL: %d falha(s) de coleta; abortado sem gravar (ex.: %s)" % (len(falhas), falhas[0]))
        return 1
    zero = [r for r in regs if round(tr._num(r.get("valor")), 2) == 0.0]
    regs = [r for r in regs if round(tr._num(r.get("valor")), 2) != 0.0]
    novo = gp.gerar_extrato(regs, fichas, None, "Portal da Transparência, API despesas/documentos fase 1, coleta de %s a %s em %s"
                            % (desde.isoformat(), ate.isoformat(), dt.date.today().isoformat()))
    # mescla com o extrato anterior: fora da janela fica o que havia
    s = Path(o.saida)
    s.mkdir(parents=True, exist_ok=True)
    antigo = json.load(open(s / ARQ, encoding="utf-8")) if (s / ARQ).exists() else {"ne": []}
    fora = [x for x in antigo["ne"] if not (desde <= tr._data(x["data"]) <= ate)]
    novo["ne"] = sorted(fora + novo["ne"], key=lambda x: (tr._data(x["data"]) or dt.date.min, x["documento"]))
    datas = [tr._data(x["data"]) for x in novo["ne"] if tr._data(x["data"])]
    novo["data_execucao"] = max(datas).isoformat() if datas else None
    novo["meta"] = {"janela": [desde.isoformat(), ate.isoformat()], "ne_na_janela": len(regs), "ne_zero_retiradas": len(zero),
                    "ne_fora_da_janela_mantidas": len(fora), "coletado_em": dt.datetime.now().isoformat(timespec="seconds")}
    json.dump(novo, open(s / ARQ, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    dia = s / ate.isoformat()
    dia.mkdir(exist_ok=True)
    json.dump(novo, open(dia / ARQ, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("PORTAL: %d NE na janela %s..%s (%d a 0,00 retiradas), %d mantidas de antes; último dia de emissão %s"
          % (len(regs), desde, ate, len(zero), len(fora), novo["data_execucao"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
