# -*- coding: utf-8 -*-
"""
recalculo_independente.py (v2, 09nov2026; v1 de 07nov2026) — portão 3 do PLANO v2.4 (D12 revista).

Recalcula, SEM importar o motor, os números que o `dados.json` publica, a partir das mesmas fontes brutas
(extrato sem pessoa, carteira em JSON e atas), e compara com tolerância de R$ 0,01. Se um número não bater,
sai com código 1 e a publicação não acontece (CI do `painel-gof-baaplog`).

O que se recalcula:
  B1  total e nº de NE das 6 OMDS; por OMDS, UG 160 e 167; soma dos meses = total da OMDS.
      v2 (LOG-181): extrato versao 2 = base LIQUIDA; NE com valor 0,00 (anulada por inteiro) fora da contagem; emissao
      bruta de apoio; total liquido = total_item23 declarado no extrato; vinculo pela chave SIASG por pregao.
  B3  nº de processos, estimado e homologado somados da carteira.
  B4  contagem de NE a verificar por nível; atas a vencer (<= limite) contra o JSON de atas.
  v2.4 (P-RP-2) blocos rp_por_ano e contratos, quando presentes: somas por OMDS/ano, índice, a liquidar = item 43 da régua,
      recontagem dos contratos e ausência de fornecedor/CNPJ.
Uso: python recalculo_independente.py --dados saida/dados.json --extrato dados/execucao/ultimo.json \
        --carteira dados/carteira_processos.json --atas saida/atas_pncp_AAAA-MM-DD.json [--hoje AAAA-MM-DD]
"""
import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))
import gof_config as cfg  # noqa: E402

TOL = 0.01
# UG -> OMDS: mesma tabela do projeto (sempre as duas UG de cada OMDS, D3)
UGS = cfg.ug_para_chave_intercalado()  # config/om.json


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


def conferir_v24(D):
    """v2.4 (P-RP-2): recalcula, SEM o motor, as somas dos blocos rp_por_ano e contratos publicados no dados.json.

    RP: por OMDS e ano = soma das UG; total da OMDS = soma dos anos; índice = (liquidado + cancelado) ÷ inscrito; a liquidar
    por UG = RPNP a liquidar (item 43) da régua publicada na mesma página, quando a régua for do mesmo dia.
    Contratos: quantidade, teto e contagens de vencimento = recontagem da lista; nenhum fornecedor nem CNPJ."""
    falhas = []
    rp = D.get("rp_por_ano")
    if rp and not rp.get("ausente"):
        campos = ("inscrito", "liquidado", "cancelado", "a_liquidar", "em_liquidacao", "bloqueado", "excetuado")
        soma = defaultdict(lambda: defaultdict(float))
        for x in rp["por_ug"]:
            for k in (x["ano"], "total"):
                for c in campos:
                    soma[(x["omds"], k)][c] += x[c]
        for x in rp["por_omds"]:
            for c in campos:
                if not igual(soma[(x["omds"], x["ano"])][c], x[c]):
                    falhas.append("RP %s %s %s: recalculado %.2f, publicado %.2f" % (x["omds"], x["ano"], c, soma[(x["omds"], x["ano"])][c], x[c]))
            ind = round(100 * (x["liquidado"] + x["cancelado"]) / x["inscrito"], 2) if abs(x["inscrito"]) > 0.005 else None
            if (ind is None) != (x["indice"] is None) or (ind is not None and abs(ind - x["indice"]) > 0.01):
                falhas.append("RP %s %s índice: recalculado %s, publicado %s" % (x["omds"], x["ano"], ind, x["indice"]))
        g = D.get("regua") or {}
        if g.get("data_dado") == rp.get("data_dado"):
            item43 = {u: v["rpnp_a_liquidar"] for o in (g.get("por_omds") or {}).values() for u, v in o["por_ug"].items()}
            aliq = defaultdict(float)
            for x in rp["por_ug"]:
                aliq[x["ug"]] += x["a_liquidar"]
            for u in sorted(set(item43) | set(aliq)):
                if not igual(item43.get(u, 0.0), aliq.get(u, 0.0)):
                    falhas.append("RP UG %s a liquidar: régua %.2f, por NE %.2f" % (u, item43.get(u, 0.0), aliq.get(u, 0.0)))
        if rp.get("por_ne") is not None:
            dp = cfg.dados_pessoais()
            if not dp["favorecido"]:
                falhas.append("RP: detalhe por NE publicado sem permissão do config")
            soma_ne = defaultdict(float)
            for x in rp["por_ne"]:
                soma_ne[x["ug"]] += x["a_liquidar"]
            al_ug = defaultdict(float)
            for x in rp["por_ug"]:
                al_ug[x["ug"]] += x["a_liquidar"]
            for u in sorted(set(soma_ne) | set(al_ug)):
                if abs(soma_ne.get(u, 0.0) - al_ug.get(u, 0.0)) > 0.01 + 0.005 * len(rp["por_ne"]):
                    falhas.append("RP UG %s: detalhe por NE %.2f, por ano %.2f" % (u, soma_ne.get(u, 0.0), al_ug.get(u, 0.0)))
            if any(cfg._RE_CPF.search(str(x.get("favorecido") or "")) for x in rp["por_ne"]):
                falhas.append("RP: CPF inteiro no favorecido do detalhe por NE")
    lq = D.get("liquidacao") or {}
    if lq.get("por_ne") is not None:
        dp = cfg.dados_pessoais()
        if not dp["favorecido"]:
            falhas.append("Liquidação: detalhe por NE publicado sem permissão do config")
        soma_ne = defaultdict(float)
        for x in lq["por_ne"]:
            soma_ne[x["ug"]] += x["a_liquidar"]
        pub = {u: r["a_liquidar"] for o in (lq.get("por_omds") or {}).values() for u, r in (o.get("por_ug") or {}).items()}
        for u in sorted(set(soma_ne) | set(pub)):
            if abs(soma_ne.get(u, 0.0) - pub.get(u, 0.0)) > 0.01 + 0.005 * len(lq["por_ne"]):
                falhas.append("Liquidação UG %s: detalhe por NE %.2f, por UG %.2f" % (u, soma_ne.get(u, 0.0), pub.get(u, 0.0)))
        cpf = cfg._RE_CPF
        if any(cpf.search(str(x.get(k) or "")) for x in lq["por_ne"] for k in ("favorecido", "documento")):
            falhas.append("Liquidação: CPF inteiro no detalhe por NE")
    ct = D.get("contratos")
    if ct and not ct.get("ausente"):
        for o in ct["por_omds"]:
            if o.get("indisponivel"):
                continue
            cs = o["contratos"]
            for nome, esp, pub in (("quantidade", len(cs), o["quantidade"]),
                                   ("teto", round(sum(c["valor_global_teto"] for c in cs), 2), o["teto_total"]),
                                   ("vencem_90", sum(c["dias_para_vencer"] <= 90 for c in cs), o["vencem_90"]),
                                   ("vencem_180", sum(c["dias_para_vencer"] <= 180 for c in cs), o["vencem_180"]),
                                   ("vencem_365", sum(c["dias_para_vencer"] <= 365 for c in cs), o["vencem_365"])):
                if not igual(esp, pub):
                    falhas.append("Contratos %s %s: recalculado %s, publicado %s" % (o["omds"], nome, esp, pub))
            dp = cfg.dados_pessoais()
            vetadas = ("cnpj_cpf_idgener", "empenhado", "empenhado_ano") + (() if dp["favorecido"] else ("fornecedor", "cnpj", "documento"))
            if any(k in c for c in cs for k in vetadas):
                falhas.append("Contratos %s: campo vetado pelo config na saída (fornecedor/CNPJ/empenhado)" % o["omds"])
            if dp["favorecido"]:
                doc = cfg._RE_CPF
                campos = ("objeto", "documento", "fornecedor")
            else:
                doc = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b|\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
                campos = ("objeto",)
            if doc and any(doc.search(str(c.get(k) or "")) for c in cs for k in campos):
                falhas.append("Contratos %s: CPF/CNPJ indevido no texto" % o["omds"])
    return falhas


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", required=True)
    ap.add_argument("--extrato", required=True)
    ap.add_argument("--carteira", help="obrigatório quando o dados.json tem B3 (carteira GCALC ligada)")
    ap.add_argument("--atas", help="obrigatório quando o dados.json tem B4")
    ap.add_argument("--hoje", default=None)
    o = ap.parse_args(argv)
    D = json.load(open(o.dados, encoding="utf-8"))
    ext = json.load(open(o.extrato, encoding="utf-8"))
    gcalc = D.get("b3") is not None
    if gcalc and not (o.carteira and o.atas):
        raise SystemExit("--carteira e --atas sao obrigatorios quando o dados.json tem B3/B4")
    cart = json.load(open(o.carteira, encoding="utf-8")) if gcalc else {"processos": []}
    atas = json.load(open(o.atas, encoding="utf-8"))["atas"] if gcalc else []
    hoje = dt.date.fromisoformat(o.hoje or D["meta"]["hoje"])
    falhas = []

    def chk(nome, esperado, obtido, numerico=True):
        ok = igual(esperado, obtido) if numerico else esperado == obtido
        if not ok:
            falhas.append("%s: recalculado %s, publicado %s" % (nome, esperado, obtido))

    # ---- B1 a partir do extrato
    liquido = ext.get("versao") == 2 and ext.get("base") == "liquido_6229201"
    if liquido:
        base_esperada = "liquido"
    elif D["meta"].get("fonte_b1") == "portal":
        base_esperada = "portal"
    else:
        base_esperada = "emissao"
    chk("B1 base", base_esperada, D["b1"].get("base", "emissao"), numerico=False)
    por = defaultdict(lambda: {"160": 0.0, "167": 0.0, "n160": 0, "n167": 0, "meses": [0.0] * 12})
    docs, n_contadas, emitido, anuladas = set(), 0, 0.0, 0
    siasg = defaultdict(lambda: [0, 0.0])
    for x in ext["ne"]:
        if x["documento"] in docs:
            falhas.append("NE repetida no extrato: " + x["documento"])
        docs.add(x["documento"])
        omds = UGS[x["ug"]]
        if liquido:
            emitido += float(x["valor_emitido"])
            if x.get("nivel") == "SIASG" and float(x["valor"]) != 0.0:
                siasg[x["pregao"]][0] += 1
                siasg[x["pregao"]][1] += float(x["valor"])
            if float(x["valor"]) == 0.0:
                anuladas += 1
                continue
        n_contadas += 1
        lado = "160" if x["ug"].startswith("160") else "167"
        por[omds][lado] += float(x["valor"])
        por[omds]["n" + lado] += 1
        d = _data(x.get("data"))
        if d and d.year == cfg.exercicio():
            por[omds]["meses"][d.month - 1] += float(x["valor"])
    total = round(sum(v["160"] + v["167"] for v in por.values()), 2)
    chk("B1 total", total, D["b1"]["total"])
    chk("B1 ne", n_contadas, D["b1"]["ne"])
    if liquido:
        chk("B1 liquido = item 23 declarado", round(float(ext["total_item23"]), 2), total)
        chk("B1 emissao bruta", round(emitido, 2), D["b1"]["apoio"]["emissao_bruta"])
        chk("B1 NE anuladas", anuladas, D["b1"]["apoio"]["ne_anuladas"])
        chk("B1 NE emitidas", len(docs), D["b1"]["apoio"]["ne_emitidas"])
        pub = {x["pregao"]: x for x in (D["b1"].get("vinculo_gcalc") or {}).get("pregoes", [])}
        chk("B1 vinculo pregoes", sorted(siasg), sorted(pub), numerico=False)
        for p_, (n_, v_) in siasg.items():
            if p_ in pub:
                chk("B1 vinculo %s ne" % p_, n_, pub[p_]["ne"])
                chk("B1 vinculo %s valor" % p_, round(v_, 2), pub[p_]["valor"])
    chk("B1 data_dado", ext["data_execucao"], D["b1"]["data_dado"], numerico=False)
    for linha in D["b1"]["omds"]:
        v = por[linha["omds"]]
        chk("B1 %s UG160" % linha["omds"], round(v["160"], 2), linha["valor160"])
        chk("B1 %s UG167" % linha["omds"], round(v["167"], 2), linha["valor167"])
        chk("B1 %s total" % linha["omds"], round(v["160"] + v["167"], 2), linha["total"])
        chk("B1 %s ne" % linha["omds"], v["n160"] + v["n167"], linha["ne"])
        chk("B1 %s soma dos meses" % linha["omds"], round(sum(v["meses"]), 2), round(sum(linha["por_mes"]), 2))
    falhas += conferir_v24(D)  # v2.4: só age se o dados.json tiver os blocos (OM sem eles: nada muda)
    procs = cart["processos"]
    if not gcalc:  # OM sem carteira GCALC: B3 e B4 desligados no config
        for f in falhas:
            print("  - " + f)
        print("RECALCULO: %s (B1 R$ %.2f, %d NE; B3 e B4 desligados)"
              % ("%d divergencia(s)" % len(falhas) if falhas else "confere ao centavo", total, n_contadas))
        return 1 if falhas else 0
    # ---- B3 a partir da carteira
    r = D["b3"]["resumo"]
    chk("B3 processos", len(procs), r["processos"])
    chk("B3 estimado", round(sum(_num_br(p.get("estimado")) for p in procs), 2), r["estimado"])
    chk("B3 homologado", round(sum(_num_br(p.get("homologado")) for p in procs), 2), r["homologado"])
    chk("B3 atrasados", sum(1 for p in procs if str(p.get("status_prazo", "")).strip() == "Atrasado"), r["atrasados"])
    # ---- B4: NE a verificar e atas a vencer
    A_VERIFICAR = ("ALERTA", "AMBIGUO", "CITADO_SEM_ATA", "SEM_CHAVE_CITA")
    niveis = Counter(x["nivel"] for x in ext["ne"] if x.get("nivel") in A_VERIFICAR)
    pub = D["b4"]["ne_verificar"]["contagem"]
    for n in A_VERIFICAR:
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
          % (total, n_contadas, len(procs), sum(niveis.values()), len(venc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
