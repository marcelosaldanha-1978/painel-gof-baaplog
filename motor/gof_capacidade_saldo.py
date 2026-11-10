#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gof_capacidade_saldo.py — saldo de ata por item calculado por nós (v0.1, 10nov2026).

Por que: o campo «saldoRemanejamentoEmpenho» da API do Compras.gov.br não cai com os empenhos (medido em 10/11/2026:
compra 90005/2025 do 1º D Sup com 53 NE e saldo igual ao registrado; LOG-146 já vira quantidadeEmpenhada = 0 em todos
os itens). O saldo usado no painel é, por UASG, item e fornecedor:

    saldo = quantidade registrada para a UASG (API) × valor unitário − empenhado líquido pela UASG naquele item (TG)

O empenhado vem do relatório de itens de NE do TG (inclusão + reforço − anulação por item), ligado à ata pela chave
SIASG da NE (UASG gerenciadora, modalidade 05, número e ano da compra), pelo número do item («Item compra: NNNNN») e
pelo CNPJ do fornecedor. A UASG empenha nas UG 160xxx e 167xxx de mesmo final; as duas contam.

Uso: python motor/gof_capacidade_saldo.py --capacidade X.json --itens itens_sem_pessoa.csv --extrato extrato.json --saida Y.json
"""
import argparse
import collections
import csv
import json
import re
import sys

SINAL = {"INCLUSAO": 1, "REFORCO": 1, "ANULACAO": -1}


def empenhado_por_item(itens_csv, extrato):
    ch = {}
    for x in json.load(open(extrato, encoding="utf-8"))["ne"]:
        m = re.match(r"^(\d{6})-05-(\d{5})/(\d{4})$", x.get("chave") or "")
        if m:
            ch[x["documento"]] = (m.group(1), "%s/%s" % (m.group(2), m.group(3)))
    emp = collections.defaultdict(float)
    sem_chave = 0
    for r in csv.DictReader(open(itens_csv, encoding="utf-8"), delimiter=";"):
        m = re.match(r"Item compra: (\d{5})", r.get("item_descricao") or "")
        if not m or r["operacao"] not in SINAL:
            continue
        if r["ne"] not in ch:
            sem_chave += 1
            continue
        ger, compra = ch[r["ne"]]
        uasg = "160" + r["ug"][3:6]
        emp[(uasg, ger, compra, m.group(1), r.get("cnpj_favorecido") or "")] += SINAL[r["operacao"]] * float(r["valor_operacao"] or 0)
    return emp, sem_chave


def exportar(itens_csv, extrato, saida, data_tg):
    """Agregado sem pessoa para o runner: empenhado por (UASG, gerenciadora, compra, item, CNPJ) e alvos de terceiros."""
    emp, sem_chave = empenhado_por_item(itens_csv, extrato)
    omds = {"160238", "160246", "160304", "160307", "160321", "160329"}
    alvos = sorted({(k[1], k[2].split("/")[0], k[2].split("/")[1], k[3], k[4]) for k in emp if k[1] not in omds})
    json.dump({"fonte": "TG, relatório de itens de NE (sem pessoa) + chave SIASG do extrato", "data_tg": data_tg,
               "itens_tg_sem_chave": sem_chave, "empenhado": sorted([[list(k), round(v, 2)] for k, v in emp.items()]),
               "alvos": [list(x) for x in alvos]}, open(saida, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return len(emp), len(alvos)


LIMITE_POR_VALOR = 1.00  # preço unitário até R$ 1,00: a «quantidade» registrada é um teto em reais (ex.: peças por tabela)

LEGENDA_FORA = {
    "CONTRATO_ATIVO": "NE em compra que tem contrato ativo da UASG no Contratos.gov.br (execução de contrato, não de ata)",
    "MESMA_COMPRA_ITEM_FORA": "a compra tem ata vigente colhida para a UASG, mas este item ou fornecedor não está nela",
    "COMPRA_PROPRIA_SEM_ATA_VIGENTE": "compra da própria UASG sem ata vigente (ata vencida, compra sem SRP ou contrato não lido)",
    "COMPRA_DE_OMDS_SEM_ATA_VIGENTE": "compra de outra OMDS da BaApLog sem ata vigente para a UASG",
    "COMPRA_DE_TERCEIRO_SEM_ATA_VIGENTE": "compra de órgão de fora sem ata vigente para a UASG (ata vencida ou carona)",
}


def natureza(x):
    """POR_VALOR quando o preço unitário é até R$ 1,00 (o registrado é teto financeiro, não quantidade de bens)."""
    return "POR_VALOR" if 0 < (x.get("valor_unitario") or 0) <= LIMITE_POR_VALOR else "POR_QUANTIDADE"


def classificar_fora(fora, cap):
    """Classifica o empenhado em itens que a coleta não trouxe, só com o que já está no arquivo (sem nova consulta)."""
    uasg_omds = {r.get("uasg"): o for o, r in (cap.get("resumo") or {}).items() if isinstance(r, dict)}
    for x in cap["itens"]:
        uasg_omds.setdefault(x["uasg"], x["omds"])
    compras_colhidas = {(x["uasg"], x["gerenciadora"], x["compra"]) for x in cap["itens"]}
    contratos = set()
    for uasg, lista in (cap.get("contratos") or {}).items():
        for c in lista or []:
            contratos.add((uasg, str(c.get("unidade_compra") or ""), str(c.get("licitacao") or "")))
    por_classe, por_omds = {}, {}
    for (uasg, ger, compra, _item, _cnpj), v in fora.items():
        if (uasg, ger, compra) in contratos:
            cl = "CONTRATO_ATIVO"
        elif (uasg, ger, compra) in compras_colhidas:
            cl = "MESMA_COMPRA_ITEM_FORA"
        elif ger == uasg:
            cl = "COMPRA_PROPRIA_SEM_ATA_VIGENTE"
        elif ger in uasg_omds:
            cl = "COMPRA_DE_OMDS_SEM_ATA_VIGENTE"
        else:
            cl = "COMPRA_DE_TERCEIRO_SEM_ATA_VIGENTE"
        c = por_classe.setdefault(cl, {"itens": 0, "valor": 0.0})
        c["itens"] += 1
        c["valor"] += v
        o = por_omds.setdefault(uasg_omds.get(uasg, uasg), {})
        o[cl] = o.get(cl, 0.0) + v
    for c in por_classe.values():
        c["valor"] = round(c["valor"], 2)
    por_omds = {o: {k: round(v, 2) for k, v in d.items()} for o, d in por_omds.items()}
    return {"por_classe": por_classe, "por_omds": por_omds}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--capacidade", required=True)
    ap.add_argument("--itens", help="CSV sem pessoa dos itens de NE do TG (com --extrato)")
    ap.add_argument("--extrato")
    ap.add_argument("--empenhado", help="JSON agregado {chaves, valores} (alternativa para o runner)")
    ap.add_argument("--saida", required=True)
    a = ap.parse_args(argv)
    cap = json.load(open(a.capacidade, encoding="utf-8"))
    if a.empenhado:
        d = json.load(open(a.empenhado, encoding="utf-8"))
        emp = {tuple(k): v for k, v in d["empenhado"]}
        sem_chave = d.get("itens_tg_sem_chave", 0)
    else:
        emp, sem_chave = empenhado_por_item(a.itens, a.extrato)
    usados = set()
    excesso = []
    for x in cap["itens"]:
        k = (x["uasg"], x["gerenciadora"], x["compra"], x["item"], x["cnpj"])
        e = round(emp.get(k, 0.0), 2)
        usados.add(k)
        reg = round(x["quantidade_registrada_unidade"] * x["valor_unitario"], 2)
        x["registrado_valor"] = reg
        x["empenhado_tg"] = e
        x["saldo_proprio"] = round(max(0.0, reg - e), 2)
        x["natureza_registro"] = natureza(x)
        if e > reg + 0.01:
            excesso.append({"chave": list(k), "registrado": reg, "empenhado": e})
    # empenhos em itens de ata que a coleta não trouxe (ata vencida, item fora do universo, UASG fora da lista da ata)
    fora = {k: round(v, 2) for k, v in emp.items() if k not in usados and v > 0.01}
    resumo = {}
    for x in cap["itens"]:
        r = resumo.setdefault(x["omds"], {"registrado": 0.0, "empenhado_tg": 0.0, "saldo_proprio": 0.0, "saldo_api": 0.0,
                                          "saldo_por_tipo": collections.Counter(), "vence_ate_31dez": 0.0})
        r["registrado"] += x["registrado_valor"]
        r["empenhado_tg"] += x["empenhado_tg"]
        r["saldo_proprio"] += x["saldo_proprio"]
        r["saldo_api"] += x["saldo_valor"]
        r["saldo_por_tipo"][x["tipo_unidade"]] += x["saldo_proprio"]
        r.setdefault("saldo_por_natureza", collections.Counter())[x["natureza_registro"]] += x["saldo_proprio"]
        if (x["vigencia_fim"] or "9") <= cap["hoje"][:4] + "-12-31":
            r["vence_ate_31dez"] += x["saldo_proprio"]
    for r in resumo.values():
        for k in ("registrado", "empenhado_tg", "saldo_proprio", "saldo_api", "vence_ate_31dez"):
            r[k] = round(r[k], 2)
        r["saldo_por_tipo"] = {k: round(v, 2) for k, v in r["saldo_por_tipo"].items()}
        r["saldo_por_natureza"] = {k: round(v, 2) for k, v in r["saldo_por_natureza"].items()}
    for omds, r in resumo.items():
        seus = sorted((x for x in cap["itens"] if x["omds"] == omds and x["saldo_proprio"] > 0),
                      key=lambda x: -x["saldo_proprio"])[:5]
        r["maiores_itens"] = [{"ata": x.get("ata"), "gerenciadora": x["gerenciadora"], "compra": x["compra"],
                               "item": x["item"], "descricao": (x.get("descricao") or "")[:80],
                               "natureza": x["natureza_registro"], "saldo_proprio": x["saldo_proprio"]} for x in seus]
        r["concentracao_5_maiores"] = round(sum(x["saldo_proprio"] for x in seus), 2)
    fora_classes = classificar_fora(fora, cap)
    cap["saldo"] = {"versao": "0.2", "regra": __doc__.split("Uso:")[0].strip(), "resumo": resumo,
                    "itens_tg_sem_chave": sem_chave, "empenho_acima_do_registrado": excesso,
                    "empenhado_fora_da_coleta": {"itens": len(fora), "valor": round(sum(fora.values()), 2),
                                                 "por_classe": fora_classes["por_classe"],
                                                 "por_omds": fora_classes["por_omds"],
                                                 "legenda": LEGENDA_FORA}}
    with open(a.saida, "w", encoding="utf-8") as f:
        json.dump(cap, f, ensure_ascii=False, indent=1)
    print(json.dumps(cap["saldo"]["resumo"], ensure_ascii=False, indent=1))
    print("acima do registrado:", len(excesso), "| fora da coleta:", cap["saldo"]["empenhado_fora_da_coleta"], "| sem chave:", sem_chave)


if __name__ == "__main__":
    sys.exit(main())
