#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gof_capacidade.py — capacidade imediata de empenho das 6 OMDS por fontes oficiais, sem depender das SALC (v0.1, 10nov2026).

Fontes (todas públicas, sem login):
  1. API de Dados Abertos do Compras.gov.br, módulo ARP (dadosabertos.compras.gov.br):
       1.2_consultarARP_FimVigencia  atas vigentes de uma UASG gerenciadora
       2.1_consultarARPItem_Id       itens da ata (quantidade homologada, empenhada, valor unitário, fornecedor)
       3_consultarUnidadesItem       por item, cada UASG (gerenciadora, participante, não participante = carona)
                                     com «saldoRemanejamentoEmpenho» (quantidade ainda empenhável pela UASG)
  2. API pública do Contratos.gov.br (contratos.comprasnet.gov.br/api): contratos ativos por UG e empenhos de cada contrato.
  3. Extrato do painel (TG, chave SIASG de cada NE): descobre as compras de outros órgãos já usadas pelas OMDS.

Universo de atas: (a) atas vigentes em que a gerenciadora é uma das 6 UASG; (b) atas vigentes das compras (pregão)
de outros órgãos citadas na chave SIASG de alguma NE de 2026 das 6 OMDS. Limite declarado: carona aprovada em ata
de outro órgão ainda sem nenhuma NE não é descoberta pela API pública (não há consulta por UASG aderente).

Saída: JSON com, por OMDS, atas e itens com saldo empenhável (quantidade × valor unitário), por tipo de participação,
e contratos ativos com valor anual e empenhado em 2026. Nenhum dado de pessoa física (fornecedores são PJ; CPF descartado).

Uso: python motor/gof_capacidade.py --extrato dados/execucao/AAAA-MM-DD/extrato.json --itens-tg itens_sem_pessoa.csv --saida X.json [--cache pasta]

Itens de atas de outros órgãos: só os que alguma OMDS já empenhou (TG); os demais itens dessas atas não são consultados (custo).
"""
import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ARP = "https://dadosabertos.compras.gov.br/modulo-arp"
CTR = "https://contratos.comprasnet.gov.br/api"
OMDS = {"160238": "Cmdo BaApLog", "160246": "DC Mun", "160304": "BMSA", "160307": "1º D Sup", "160321": "ECT", "160329": "BCMS"}


CACHE = None  # pasta de cache (opcional): cada URL respondida uma vez por coleta


def http(url, tentativas=5):
    if CACHE:
        arq = os.path.join(CACHE, hashlib.sha256(url.encode()).hexdigest() + ".json")
        if os.path.exists(arq):
            return json.load(open(arq, encoding="utf-8"))
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "painel-gof-baaplog"})
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read().decode("utf-8"))
            if CACHE:
                with open(arq, "w", encoding="utf-8") as fo:
                    json.dump(d, fo, ensure_ascii=False)
            return d
        except Exception as e:  # noqa: BLE001 (rede pública instável; repete com espera)
            if i == tentativas - 1:
                raise RuntimeError("falha em %s: %s" % (url, e)) from e
            time.sleep(2 * (i + 1))


def paginado(base, params):
    pag, out = 1, []
    while True:
        p = dict(params, pagina=pag, tamanhoPagina=params.get("tamanhoPagina", 500))
        d = http(base + "?" + urllib.parse.urlencode(p))
        out += d.get("resultado") or []
        if not d.get("paginasRestantes"):
            return out
        pag += 1


def num(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    neg = s.startswith("-")
    s = s.lstrip("-").replace(".", "").replace(",", ".")
    return -float(s) if neg else float(s)


def atas_vigentes(uasg, hoje):
    """Atas com vigência final de hoje a hoje + 2 anos (duas janelas de 365 dias, limite da API)."""
    out = []
    for k in (0, 1):
        ini = hoje + dt.timedelta(days=365 * k)
        fim = ini + dt.timedelta(days=364)
        out += paginado(ARP + "/1.2_consultarARP_FimVigencia", {
            "codigoUnidadeGerenciadora": uasg, "dataVigenciaFinalMin": ini.isoformat(),
            "dataVigenciaFinalMax": fim.isoformat(), "tamanhoPagina": 500})
    return [a for a in out if not a.get("ataExcluido")]


def itens_da_ata(ctrl):
    d = http(ARP + "/2.1_consultarARPItem_Id?" + urllib.parse.urlencode({"numeroControlePncpAta": ctrl}))
    return [i for i in (d.get("resultado") or []) if not i.get("itemExcluido")]


def unidades_do_item(numero_ata, gerenciadora, item):
    """None quando a API não responde depois das tentativas: o item fica marcado «não lido», a coleta segue."""
    try:
        return paginado(ARP + "/3_consultarUnidadesItem", {
            "numeroAta": numero_ata, "unidadeGerenciadora": gerenciadora, "numeroItem": item, "tamanhoPagina": 100})
    except RuntimeError:
        return None


def itens_com_empenho(itens_csv, extrato):
    """(gerenciadora, número, ano, item, CNPJ) de outros órgãos em que alguma OMDS já empenhou (TG: itens + chave SIASG)."""
    ch = {}
    for x in json.load(open(extrato, encoding="utf-8"))["ne"]:
        m = re.match(r"^(\d{6})-05-(\d{5})/(\d{4})$", x.get("chave") or "")
        if m:
            ch[x["documento"]] = (m.group(1), m.group(2), m.group(3))
    out = set()
    for r in csv.DictReader(open(itens_csv, encoding="utf-8"), delimiter=";"):
        m = re.match(r"Item compra: (\d{5})", r.get("item_descricao") or "")
        if m and r["ne"] in ch and ch[r["ne"]][0] not in OMDS:
            out.add(ch[r["ne"]] + (m.group(1), r.get("cnpj_favorecido") or ""))
    return out


def compras_do_extrato(caminho):
    """Compras (UASG, modalidade 05, número, ano) citadas na chave SIASG das NE; valor líquido e NE por compra."""
    d = json.load(open(caminho, encoding="utf-8"))
    comp = {}
    for x in d["ne"]:
        m = re.match(r"^(\d{6})-(\d{2})-(\d{5})/(\d{4})$", x.get("chave") or "")
        if not m or m.group(2) != "05":
            continue
        k = (m.group(1), m.group(3), m.group(4))
        c = comp.setdefault(k, {"ne": 0, "valor": 0.0, "ug": set()})
        c["ne"] += 1
        c["valor"] += x["valor"]
        c["ug"].add(x["ug"][:6])
    return comp, d.get("data_execucao")


def contratos(ug, ano):
    out = []
    for c in http(CTR + "/contrato/ug/%s" % ug):
        if c.get("receita_despesa") != "Despesa" or c.get("situacao") != "Ativo":
            continue
        emp = http(c["links"]["empenhos"]) if c.get("links", {}).get("empenhos") else []
        emp_ano = [e for e in emp if (e.get("numero") or "").startswith(str(ano)) and e.get("unidade_gestora") == ug]
        empenhado = round(sum(num(e.get("empenhado")) for e in emp_ano), 2)
        forn = (c.get("fornecedor") or {})
        tipo_forn = "PJ" if len(re.sub(r"\D", "", forn.get("cnpj_cpf_idgener", ""))) == 14 else "PF"
        out.append({
            "id": c["id"], "numero": c["numero"], "tipo": c["tipo"], "categoria": c.get("categoria"),
            "modalidade": c.get("modalidade"), "unidade_compra": c.get("unidade_compra"),
            "licitacao": c.get("licitacao_numero"), "objeto": (c.get("objeto") or "")[:200],
            "fornecedor": forn.get("nome") if tipo_forn == "PJ" else None,
            "cnpj": forn.get("cnpj_cpf_idgener") if tipo_forn == "PJ" else None,
            "vigencia_inicio": c.get("vigencia_inicio"), "vigencia_fim": c.get("vigencia_fim"),
            "valor_global": num(c.get("valor_global")), "valor_parcela": num(c.get("valor_parcela")),
            "num_parcelas": c.get("num_parcelas"), "empenhado_ano": empenhado, "ne_ano": len(emp_ano),
        })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--extrato", required=True)
    ap.add_argument("--saida", required=True)
    ap.add_argument("--hoje", default=dt.date.today().isoformat())
    ap.add_argument("--paralelo", type=int, default=6)
    ap.add_argument("--itens-tg", help="CSV sem pessoa do relatório de itens de NE do TG")
    ap.add_argument("--alvos", help="JSON [[gerenciadora, numero, ano, item, cnpj], ...] (alternativa ao --itens-tg, para o runner)")
    ap.add_argument("--cache", default=None)
    a = ap.parse_args(argv)
    global CACHE
    CACHE = a.cache
    if CACHE:
        os.makedirs(CACHE, exist_ok=True)
    if a.alvos:
        alvo_terc = {tuple(x) for x in json.load(open(a.alvos, encoding="utf-8"))["alvos"]}
    elif a.itens_tg:
        alvo_terc = itens_com_empenho(a.itens_tg, a.extrato)
    else:
        ap.error("informe --alvos ou --itens-tg")
    hoje = dt.date.fromisoformat(a.hoje)
    compras, data_extrato = compras_do_extrato(a.extrato)
    gerenciadoras = sorted(set(OMDS) | {k[0] for k in compras})
    log = {"gerenciadoras_consultadas": len(gerenciadoras), "compras_no_extrato": len(compras)}

    # 1. atas vigentes das gerenciadoras; ficam as das 6 OMDS e as das compras usadas
    with cf.ThreadPoolExecutor(a.paralelo) as ex:
        res = dict(zip(gerenciadoras, ex.map(lambda u: atas_vigentes(u, hoje), gerenciadoras), strict=True))
    print("gerenciadoras", len(gerenciadoras), dt.datetime.now().strftime("%H:%M:%S"), flush=True)
    atas = []
    for u, lst in res.items():
        for at in lst:
            k = (u, at.get("numeroCompra"), at.get("anoCompra"))
            if u in OMDS or k in compras:
                atas.append(at)
    log["atas_vigentes_no_universo"] = len(atas)

    # 2. itens de cada ata
    with cf.ThreadPoolExecutor(a.paralelo) as ex:
        itens = dict(zip([x["numeroControlePncpAta"] for x in atas], ex.map(lambda x: itens_da_ata(x["numeroControlePncpAta"]), atas), strict=True))

    # 3. unidades de cada item: saldo empenhável por UASG
    tarefas = []
    for at in atas:
        ger = at["codigoUnidadeGerenciadora"]
        for it in itens[at["numeroControlePncpAta"]]:
            k = (ger, at.get("numeroCompra"), at.get("anoCompra"), it["numeroItem"], it.get("niFornecedor") or "")
            if ger in OMDS or k in alvo_terc:
                tarefas.append((at, it))
    log["itens_consultados"] = len(tarefas)
    log["itens_terceiros_alvo"] = len(alvo_terc)
    print("atas", len(atas), "itens a consultar", len(tarefas), flush=True)

    feitos = [0]

    def um(t):
        at, it = t
        r = unidades_do_item(at["numeroAtaRegistroPreco"], at["codigoUnidadeGerenciadora"], it["numeroItem"])
        feitos[0] += 1
        if feitos[0] % 100 == 0:
            print("unidades:", feitos[0], "de", len(tarefas), dt.datetime.now().strftime("%H:%M:%S"), flush=True)
        return r
    with cf.ThreadPoolExecutor(a.paralelo) as ex:
        unid = list(ex.map(um, tarefas))

    linhas = []
    vistos = set()
    nao_lidos = []
    for (at, it), us in zip(tarefas, unid, strict=True):
        if us is None:
            nao_lidos.append({"ata": at["numeroAtaRegistroPreco"], "gerenciadora": at["codigoUnidadeGerenciadora"],
                              "item": it["numeroItem"], "valor_total_item": it.get("valorTotal")})
            continue
        for u in us:
            cod = str(u.get("codigoUnidade"))
            if cod not in OMDS:
                continue
            chave = (at["numeroControlePncpAta"], it["numeroItem"], it.get("niFornecedor"), cod)
            if chave in vistos:
                continue
            vistos.add(chave)
            forn_ok = it.get("niFornecedor") and len(re.sub(r"\D", "", it["niFornecedor"])) == 14
            if not forn_ok or str(u.get("fornecedor", "")).split(" - ")[0] not in ("", it["niFornecedor"]):
                continue
            saldo_q = num(u.get("saldoRemanejamentoEmpenho"))
            vu = num(it.get("valorUnitario"))
            linhas.append({
                "omds": OMDS[cod], "uasg": cod, "tipo_unidade": u.get("tipoUnidade"),
                "ata": at["numeroAtaRegistroPreco"], "gerenciadora": at["codigoUnidadeGerenciadora"],
                "nome_gerenciadora": at.get("nomeUnidadeGerenciadora"), "compra": "%s/%s" % (at.get("numeroCompra"), at.get("anoCompra")),
                "vigencia_fim": at.get("dataVigenciaFinal"), "controle_pncp": at["numeroControlePncpAta"],
                "item": it["numeroItem"], "descricao": (it.get("descricaoItem") or "")[:160], "tipo_item": it.get("tipoItem"),
                "fornecedor": it.get("nomeRazaoSocialFornecedor"), "cnpj": it.get("niFornecedor"),
                "valor_unitario": vu, "quantidade_registrada_unidade": num(u.get("quantidadeRegistrada")),
                "saldo_quantidade": saldo_q, "saldo_valor": round(saldo_q * vu, 2),
                "aceita_adesao": u.get("aceitaAdesao"), "atualizado": u.get("dataHoraAtualizacao"),
            })

    # 4. contratos ativos
    with cf.ThreadPoolExecutor(a.paralelo) as ex:
        ctr = dict(zip(OMDS, ex.map(lambda ug: contratos(ug, hoje.year), OMDS), strict=True))

    resumo = {}
    for cod, nome in OMDS.items():
        ls = [x for x in linhas if x["uasg"] == cod]
        por_tipo = {}
        for x in ls:
            por_tipo[x["tipo_unidade"]] = round(por_tipo.get(x["tipo_unidade"], 0) + x["saldo_valor"], 2)
        cs = ctr[cod]
        resumo[nome] = {
            "uasg": cod,
            "atas_saldo_valor": round(sum(x["saldo_valor"] for x in ls), 2),
            "atas_por_tipo": por_tipo,
            "atas_com_saldo": len({x["controle_pncp"] for x in ls if x["saldo_valor"] > 0}),
            "itens_com_saldo": sum(1 for x in ls if x["saldo_valor"] > 0),
            "atas_vencendo_ate_31dez": round(sum(x["saldo_valor"] for x in ls if (x["vigencia_fim"] or "9") <= "%d-12-31" % hoje.year), 2),
            "contratos_ativos": len(cs),
            "contratos_valor_global": round(sum(c["valor_global"] for c in cs), 2),
            "contratos_empenhado_ano": round(sum(c["empenhado_ano"] for c in cs), 2),
        }
    saida = {"versao": "0.1", "data_coleta": dt.datetime.now().isoformat(timespec="seconds"), "hoje": hoje.isoformat(),
             "extrato_tg": data_extrato, "fontes": [ARP, CTR, "extrato TG (chave SIASG)"], "coleta": log,
             "limite": "carona aprovada em ata de outro órgão sem nenhuma NE não aparece (API pública não consulta por UASG aderente)",
             "resumo": resumo, "itens": linhas, "itens_nao_lidos": nao_lidos, "contratos": ctr}
    log["itens_nao_lidos"] = len(nao_lidos)
    with open(a.saida, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    print(json.dumps({"coleta": log, "resumo": resumo}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
