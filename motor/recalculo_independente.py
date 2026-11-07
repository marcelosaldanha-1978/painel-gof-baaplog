# -*- coding: utf-8 -*-
"""
recalculo_independente.py (v1, 07nov2026) — portão 3 do PLANO v2.4 (D12 revista).

Recalcula, SEM importar o motor, os números que o `dados.json` publica, a partir das mesmas fontes brutas
(extrato sem pessoa, carteira em JSON e atas), e compara com tolerância de R$ 0,01. Se um número não bater,
sai com código 1 e a publicação não acontece (CI do `painel-gof-baaplog`).

O que se recalcula:
  B1  total e nº de NE das 6 OMDS; por OMDS, UG 160 e 167; soma dos meses = total da OMDS.
  B3  nº de processos, estimado e homologado somados da carteira.
  B4  contagem de NE a verificar por nível; atas a vencer (<= limite) contra o JSON de atas.
Uso: python recalculo_independente.py --dados saida/dados.json --extrato dados/execucao/ultimo.json \
        --carteira dados/carteira_processos.json --atas saida/atas_pncp_AAAA-MM-DD.json [--hoje AAAA-MM-DD]
"""
import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict

TOL = 0.01
# UG -> OMDS: mesma tabela do projeto (sempre as duas UG de cada OMDS, D3)
UGS = {"160238": "BaApLog", "167238": "BaApLog", "160329": "BCMS", "167329": "BCMS", "160304": "BMSA", "167304": "BMSA",
       "160321": "ECT", "167321": "ECT", "160246": "DCMun", "167246": "DCMun", "160307": "1oDSup", "167307": "1oDSup"}


def _num_br(s):
    t = re.sub(r"[^\d,\-]", "", str(s or ""))
    return float(t.replace(",", ".")) if t else 0.0


def _data(s):
    s = str(s or "").strip()
    for f in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s[:10], f).date()
        except ValueError:
            pass
    return None


def igual(a, b):
    return abs(float(a) - float(b)) <= TOL


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", required=True)
    ap.add_argument("--extrato", required=True)
    ap.add_argument("--carteira", required=True)
    ap.add_argument("--atas", required=True)
    ap.add_argument("--hoje", default=None)
    o = ap.parse_args(argv)
    D = json.load(open(o.dados, encoding="utf-8"))
    ext = json.load(open(o.extrato, encoding="utf-8"))
    cart = json.load(open(o.carteira, encoding="utf-8"))
    atas = json.load(open(o.atas, encoding="utf-8"))["atas"]
    hoje = dt.date.fromisoformat(o.hoje or D["meta"]["hoje"])
    falhas = []

    def chk(nome, esperado, obtido, numerico=True):
        ok = igual(esperado, obtido) if numerico else esperado == obtido
        if not ok:
            falhas.append("%s: recalculado %s, publicado %s" % (nome, esperado, obtido))

    # ---- B1 a partir do extrato
    por = defaultdict(lambda: {"160": 0.0, "167": 0.0, "n160": 0, "n167": 0, "meses": [0.0] * 12})
    docs = set()
    for x in ext["ne"]:
        if x["documento"] in docs:
            falhas.append("NE repetida no extrato: " + x["documento"])
        docs.add(x["documento"])
        omds = UGS[x["ug"]]
        lado = "160" if x["ug"].startswith("160") else "167"
        por[omds][lado] += float(x["valor"])
        por[omds]["n" + lado] += 1
        d = _data(x.get("data"))
        if d and d.year == 2026:
            por[omds]["meses"][d.month - 1] += float(x["valor"])
    total = round(sum(v["160"] + v["167"] for v in por.values()), 2)
    chk("B1 total", total, D["b1"]["total"])
    chk("B1 ne", len(docs), D["b1"]["ne"])
    chk("B1 data_dado", ext["data_execucao"], D["b1"]["data_dado"], numerico=False)
    for linha in D["b1"]["omds"]:
        v = por[linha["omds"]]
        chk("B1 %s UG160" % linha["omds"], round(v["160"], 2), linha["valor160"])
        chk("B1 %s UG167" % linha["omds"], round(v["167"], 2), linha["valor167"])
        chk("B1 %s total" % linha["omds"], round(v["160"] + v["167"], 2), linha["total"])
        chk("B1 %s ne" % linha["omds"], v["n160"] + v["n167"], linha["ne"])
        chk("B1 %s soma dos meses" % linha["omds"], round(sum(v["meses"]), 2), round(sum(linha["por_mes"]), 2))
    # ---- B3 a partir da carteira
    procs = cart["processos"]
    r = D["b3"]["resumo"]
    chk("B3 processos", len(procs), r["processos"])
    chk("B3 estimado", round(sum(_num_br(p.get("estimado")) for p in procs), 2), r["estimado"])
    chk("B3 homologado", round(sum(_num_br(p.get("homologado")) for p in procs), 2), r["homologado"])
    chk("B3 atrasados", sum(1 for p in procs if str(p.get("status_prazo", "")).strip() == "Atrasado"), r["atrasados"])
    # ---- B4: NE a verificar e atas a vencer
    niveis = Counter(x["nivel"] for x in ext["ne"] if x.get("nivel") in ("ALERTA", "AMBIGUO", "CITADO_SEM_ATA"))
    pub = D["b4"]["ne_verificar"]["contagem"]
    for n in ("ALERTA", "AMBIGUO", "CITADO_SEM_ATA"):
        chk("B4 %s" % n, niveis.get(n, 0), sum(pub[n].values()))
    chk("B4 lista a verificar", sum(niveis.values()), len(D["b4"]["ne_verificar"]["lista"]))
    lim = D["b4"]["atas"]["limite_dias"]
    vig = [a for a in atas if not a.get("cancelado") and not a.get("cancelada") and (a.get("vigencia_fim") or a.get("dataVigenciaFim"))]
    venc = [a for a in vig if 0 <= (dt.date.fromisoformat(str(a.get("vigencia_fim") or a.get("dataVigenciaFim"))[:10]) - hoje).days <= lim]
    chk("B4 atas vigentes", len(vig), D["b4"]["atas"]["n_vigentes"])
    chk("B4 atas a vencer", len(venc), len(D["b4"]["atas"]["a_vencer"]))
    # ---- saida
    if falhas:
        print("RECALCULO: %d divergencia(s)" % len(falhas))
        for f in falhas:
            print("  - " + f)
        return 1
    print("RECALCULO: confere ao centavo (B1 R$ %.2f, %d NE; B3 %d processos; B4 %d NE a verificar, %d atas a vencer)"
          % (total, len(docs), len(procs), sum(niveis.values()), len(venc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
