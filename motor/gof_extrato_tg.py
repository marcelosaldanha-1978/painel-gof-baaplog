# -*- coding: utf-8 -*-
"""
gof_extrato_tg.py (v1, 09nov2026) — extrato SEM PESSOA da execucao, versao 2: EMPENHADO LIQUIDO (P-063) e vinculo pela
chave SIASG (P-064). LOG-181.

Por que versao 2: a conta 522920101 (versao 1) e a EMISSAO BRUTA. Medido em 09/11/2026 nas 12 UG:
    522920101 (emissao) 64.053.671,89 + 522920102 (reforco) 4.204.930,97 - 522920104 (anulacao) 18.358.367,00
    = 49.900.235,86 = 6229201xx (empenhos a liquidar, em liquidacao, liquidados a pagar, pagos) = item 23 «despesas
    empenhadas» do TG, ao centavo. O B1 passa a somar o liquido; a emissao bruta fica como apoio, com rotulo proprio.

Entradas (so onde os CSV do TG estao; nunca vao ao repositorio):
  --liquido  CSV «Empenho por NE com NC de origem (v1.2)_sem_pessoa» (uma linha por NE: emissao, reforco, anulacao,
             liquido 6229201, modalidade, data de emissao e descricao). A descricao so e usada aqui, para o nivel
             SEM_CHAVE_CITA; nao sai no extrato.
  --chaves   CSV do TG «NE Informacao Complementar» (item 23 por NE + chave SIASG). Confere: soma do item 23 = soma do liquido.
  --fichas   dados/pncp/ultimo.json
Saida: JSON com {"versao": 2, "data_execucao", "origem", "regra_vinculo": "2.0", "base": "liquido_6229201", "ne": [...]}
       cada NE: documento, ug, data, valor (LIQUIDO), valor_emitido (522920101), modalidade, nivel, pregao, candidatos, chave.
Sem favorecido, sem texto da NE (D6/D7).
"""
import argparse
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gcalc_transparencia as tr  # noqa: E402
import vinculo_siasg as vs  # noqa: E402

RE_NE = re.compile(r"^(\d{6})\d{5}\d{4}NE\d{6}$")
CAMPOS = ("documento", "ug", "data", "valor", "valor_emitido", "modalidade", "nivel", "pregao", "candidatos", "chave")


def num(s):
    t = str(s or "").strip().replace('"', "")
    neg = t.startswith("(") or t.startswith("-")
    t = t.strip("()-").replace(".", "").replace(",", ".")
    v = float(t) if t else 0.0
    return -v if neg else v


def ler_liquido(caminho):
    linhas = list(csv.DictReader(open(caminho, encoding="utf-8-sig", newline=""), delimiter=";"))
    out = {}
    for r in linhas:
        doc = r["ne"].strip()
        if doc in out:
            raise ValueError("NE repetida no CSV do liquido: %s" % doc)
        out[doc] = r
    return out


def ler_chaves(caminho):
    """CSV do TG (cp1252, tab): colunas Ano, UG, nome, modalidade cod, modalidade nome, NE, Inf. Complementar, Descricao, item23."""
    texto = Path(caminho).read_bytes().decode("cp1252")
    out = {}
    for r in csv.reader(io.StringIO(texto), delimiter="\t"):
        if len(r) >= 9 and RE_NE.match(r[5].strip()):
            doc = r[5].strip()
            if doc in out:
                raise ValueError("NE repetida no CSV das chaves: %s" % doc)
            out[doc] = {"chave": r[6].strip(), "item23": num(r[8])}
    return out


def gerar(liquido, chaves, fichas, data_execucao, origem):
    idx = vs.indice_carteira(fichas)
    so_liq = sorted(set(liquido) - set(chaves))
    so_cha = sorted(d for d in set(chaves) - set(liquido) if abs(chaves[d]["item23"]) > 0.005)
    if so_liq or so_cha:
        raise ValueError("NE sem par entre os dois CSV (liquido %d, chaves %d com valor): %s" % (len(so_liq), len(so_cha), (so_liq + so_cha)[:5]))
    t_liq = round(sum(num(r["empenhado_liquido_6229201"]) for r in liquido.values()), 2)
    t_23 = round(sum(c["item23"] for c in chaves.values()), 2)
    if abs(t_liq - t_23) > 0.01:
        raise ValueError("liquido 6229201 (%.2f) diferente do item 23 (%.2f)" % (t_liq, t_23))
    ne = []
    for doc in sorted(liquido):
        r = liquido[doc]
        ug = r["ug"].strip()
        if ug not in tr.UGS:
            raise ValueError("UG fora das 12: %s (%s)" % (ug, doc))
        v = vs.vincular_ne(chaves[doc]["chave"], r.get("descricao"), fichas, idx=idx, cita=tr._cita_pregao)
        ne.append({"documento": doc, "ug": ug, "data": r["dia_emissao"].strip(), "valor": round(num(r["empenhado_liquido_6229201"]), 2),
                   "valor_emitido": round(num(r["emissao_522920101"]), 2), "modalidade": r["modalidade"].strip(),
                   "nivel": v["nivel"], "pregao": v["pregao"], "candidatos": v["candidatos"], "chave": v["chave"]})
    return {"versao": 2, "data_execucao": data_execucao, "origem": origem, "regra_vinculo": vs.VERSAO_REGRA,
            "base": "liquido_6229201", "total_item23": t_23, "campos": list(CAMPOS), "ne": ne}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--liquido", required=True)
    ap.add_argument("--chaves", required=True)
    ap.add_argument("--fichas", required=True)
    ap.add_argument("--data-execucao", required=True)
    ap.add_argument("--saida", required=True)
    o = ap.parse_args(argv)
    fichas = tr.ficha_de_pncp(json.load(open(o.fichas, encoding="utf-8")))
    origem = [{"arquivo": Path(c).name, "sha256": hashlib.sha256(Path(c).read_bytes()).hexdigest()} for c in (o.liquido, o.chaves)]
    ext = gerar(ler_liquido(o.liquido), ler_chaves(o.chaves), fichas, o.data_execucao, origem)
    Path(o.saida).write_text(json.dumps(ext, ensure_ascii=False, indent=0), encoding="utf-8")
    n_siasg = sum(1 for x in ext["ne"] if x["nivel"] == "SIASG")
    print("extrato v2: %d NE, liquido R$ %.2f, emitido R$ %.2f; SIASG %d NE R$ %.2f; SEM_CHAVE_CITA %d -> %s"
          % (len(ext["ne"]), sum(x["valor"] for x in ext["ne"]), sum(x["valor_emitido"] for x in ext["ne"]), n_siasg,
             sum(x["valor"] for x in ext["ne"] if x["nivel"] == "SIASG"),
             sum(1 for x in ext["ne"] if x["nivel"] == "SEM_CHAVE_CITA"), o.saida))
    return 0


if __name__ == "__main__":
    sys.exit(main())
