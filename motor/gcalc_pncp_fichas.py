# -*- coding: utf-8 -*-
"""
gcalc_pncp_fichas.py (v1.1, 07nov2026) — recoleta, SOMENTE LEITURA, do conjunto PNCP dos processos da carteira GCALC
(detalhe da compra, itens, resultado por item e atas), no mesmo formato do `pncp_12_processos.json` de 03/11/2026, que
alimenta as fichas do vinculo NE -> pregao (gcalc_transparencia.ficha_de_pncp). Pendencia P-038 do GOF-BaApLog.

Diferencas para a coleta de 03/11 (SCRIPTS_USADOS_2026-11-04/coleta_pncp.py):
- a lista de processos vem da aba Controle Processos: CSV exportado ou, na nuvem, `dados/carteira_processos.json`
  (versionado, so colunas publicas), com o numero vigente (PE 108/2026, PE 90003/2026);
- data da coleta e fonte gravadas dentro do arquivo;
- historico e arquivos do PNCP ficam de fora (o vinculo nao os usa);
- qualquer falha de rede ABORTA a gravacao final (nunca grava conjunto parcial como se fosse completo).
Uso: python gcalc_pncp_fichas.py --carteira carteira_processos.json|carteira.csv --saida pncp_12_processos.json
Roda no GitHub Actions (workflow gof-fichas-pncp.yml), sem depender do PC.
"""
import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gof_painel as gp  # noqa: E402

UA = {"Accept": "application/json", "User-Agent": "GOF-BaApLog fichas-pncp"}
PAUSA = 0.3


class FalhaColeta(RuntimeError):
    pass


def http(url, tentativas=5):
    """GET com pausa e repeticao. 204/404 = sem dado (None). Qualquer outra falha persistente levanta FalhaColeta."""
    erro = ""
    for i in range(tentativas):
        time.sleep(PAUSA)
        try:
            r = requests.get(url, headers=UA, timeout=90)
            if r.status_code in (204, 404):
                return None
            if r.status_code == 200:
                return r.json() if r.content else None
            erro = "HTTP %s" % r.status_code
            if r.status_code == 429:
                time.sleep(20 * (i + 1))
                continue
        except (requests.RequestException, ValueError) as e:
            erro = str(e)[:120]
        time.sleep(2 + 3 * i)
    raise FalhaColeta("%s em %s" % (erro, url))


def coletar_processo(cnpj, ano, seq):
    base_c = "https://pncp.gov.br/api/consulta/v1/orgaos/%s/compras/%s/%s" % (cnpj, ano, seq)
    base_p = "https://pncp.gov.br/api/pncp/v1/orgaos/%s/compras/%s/%s" % (cnpj, ano, seq)
    res = {"detalhe": http(base_c)}
    itens, pg = [], 1
    while pg < 40:
        d = http("%s/itens?pagina=%d&tamanhoPagina=100" % (base_p, pg))
        lst = (d if isinstance(d, list) else (d or {}).get("data", [])) or []
        itens.extend(lst)
        if len(lst) < 100:
            break
        pg += 1
    res["itens"] = itens
    res["resultados"] = {str(it["numeroItem"]): http("%s/itens/%s/resultados" % (base_p, it["numeroItem"]))
                         for it in itens if it.get("temResultado")}
    res["atas"] = http(base_p + "/atas?pagina=1&tamanhoPagina=100") or {"data": []}
    if (res["atas"].get("totalPaginas") or 1) > 1:
        raise FalhaColeta("mais de 100 atas em %s/%s: paginar" % (ano, seq))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Recoleta do conjunto PNCP da carteira GCALC (somente leitura)")
    ap.add_argument("--carteira", required=True)
    ap.add_argument("--saida", required=True)
    o = ap.parse_args(argv)
    procs, dados = [], {}
    if o.carteira.endswith(".json"):
        lista = json.load(open(o.carteira, encoding="utf-8"))["processos"]
    else:
        lista = gp.ler_carteira(o.carteira)
    for p in lista:
        m = gp.RE_LINK.search(p.get("link") or "")
        cnpj, ano, seq = m.groups() if m else (None, None, None)
        procs.append({"ordem": str(p["ordem"]), "no": p["processo"], "objeto": p["objeto"], "ugg": p["ugg"], "uasg": p["uasg"],
                      "cnpj": cnpj, "ano": ano, "seq": seq})
        dados[p["processo"]] = coletar_processo(cnpj, ano, seq) if seq else None
        r = dados[p["processo"]]
        print(p["processo"], "|", ((r or {}).get("detalhe") or {}).get("situacaoCompraNome"),
              "| itens", len((r or {}).get("itens") or []), "| resultados", len((r or {}).get("resultados") or {}),
              "| atas", len(((r or {}).get("atas") or {}).get("data") or []), flush=True)
    out = {"coletado_em": dt.datetime.now().isoformat(timespec="seconds"), "fonte": "PNCP, API de consulta e API pncp/v1",
           "carteira": Path(o.carteira).name, "processos": procs, "dados": dados}
    Path(o.saida).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("gravado:", o.saida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
