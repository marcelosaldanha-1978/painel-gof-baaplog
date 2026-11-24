# -*- coding: utf-8 -*-
"""
gof_ponte_tg.py (v1.0, 23nov2026) — PONTE DO TG (P-041): alimenta o B1 todo dia útil, sem PC, a partir das ASSINATURAS.

Cadeia: assinaturas do TG (e-mail do SERPRO, ~03h) -> Apps Script do GOF `v2PonteTG` (06h e 11h) grava, numa pasta
PRIVADA do Drive compartilhada só com a conta de serviço de leitura, dois CSV UTF-8 com tabulação, SEM favorecido:
    PONTE_TG_SEM_PESSOA/<AAAA-MM-DD>_emissao_sem_pessoa.tsv   (UG, nome da UG, NE, dia, 522920101/102/104, 622920101..104)
    PONTE_TG_SEM_PESSOA/<AAAA-MM-DD>_info_complementar.tsv     (ano, UG, nome, mod. cód., mod. nome, NE, chave, descrição, item 23, total)
(<AAAA-MM-DD> = dia da ENTREGA do e-mail; os dados vão até o dia útil anterior.)
Este script (passo da montagem) lê o par mais recente, agrega por NE (a assinatura traz várias linhas por NE: a do dia de
emissão e as «NAO SE APLICA» de movimentos posteriores), confere líquido 6229201xx = item 23 ao centavo e gera o extrato
com `gof_extrato_tg.gerar` (mesma regra do extrato manual). Só escreve se o par for MAIS NOVO que o extrato vigente.
Falha (sem par, conferência divergente, Drive fora) -> código 2 e nenhuma escrita: a montagem segue com o extrato anterior.
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gcalc_transparencia as tr  # noqa: E402
import gof_config as cfg  # noqa: E402
import gof_extrato_tg as ext  # noqa: E402

PASTA = cfg.PASTA_PONTE_PADRAO  # nome histórico; o vigente vem de cfg.pasta_ponte()
RE_NE = re.compile(r"^\d{6}\d{5}\d{4}NE\d{6}$")
RE_ARQ = re.compile(r"^(\d{4}-\d{2}-\d{2})_(emissao_sem_pessoa|info_complementar)\.tsv$")
RE_DIA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
num = ext.num


def _tsv(texto):
    return list(csv.reader(io.StringIO(texto.lstrip("﻿")), delimiter="\t"))


def agregar_emissao(texto):
    """TSV sem pessoa (11 colunas: UG, nome UG, NE, dia, 522920101, 522920102, 522920104, 622920101..104) -> {NE: linha}."""
    out = {}
    for r in _tsv(texto):
        if len(r) < 11 or not RE_NE.match(r[2].strip()):
            continue
        ne, ug = r[2].strip(), r[0].strip()
        v = out.setdefault(ne, {"ug": ug, "dia": "", "e101": 0.0, "e102": 0.0, "e104": 0.0, "liq": 0.0,
                                "c101": 0.0, "c102": 0.0, "c103": 0.0, "c104": 0.0})
        if v["ug"] != ug:
            raise ValueError("NE com duas UG: %s" % ne)
        dia = r[3].strip()
        if RE_DIA.match(dia):
            if v["dia"] and v["dia"] != dia:
                raise ValueError("NE com dois dias de emissão: %s" % ne)
            v["dia"] = dia
        v["e101"] += num(r[4])
        v["e102"] += num(r[5])
        v["e104"] += num(r[6])
        v["liq"] += sum(num(x) for x in r[7:11])
        for i, k in enumerate(("c101", "c102", "c103", "c104")):
            v[k] += num(r[7 + i])
    for ne, v in out.items():
        if not v["dia"]:
            raise ValueError("NE sem dia de emissão: %s" % ne)
        for k in ("e101", "e102", "e104", "liq", "c101", "c102", "c103", "c104"):
            v[k] = round(v[k], 2)
    return out


OMDS_ROTULO = cfg.rotulo_por_chave()  # config/om.json


def liquidacao(em, data_exec):
    """Liquidação por OMDS (Portaria 399-SEF, item 6.d; evento 27: liquidar até 29/12) a partir das contas 6229201xx.
    a liquidar = 622920101 (a liquidar) + 622920102 (em liquidação); liquidado = 622920103 + 622920104 (pago);
    idade = dias corridos da emissão até a data dos dados. Sem pessoa: só totais por OMDS."""
    ref = dt.date.fromisoformat(data_exec)
    base = {"empenhado": 0.0, "liquidado": 0.0, "a_liquidar": 0.0, "ne_com_saldo": 0, "mais60_valor": 0.0, "mais60_ne": 0,
            "mais90_valor": 0.0, "mais90_ne": 0, "mais60_sem_nenhuma_liq_valor": 0.0, "mais60_sem_nenhuma_liq_ne": 0}
    por = {OMDS_ROTULO[o]: dict(base) for o in OMDS_ROTULO}
    por_ug = {}
    for v in em.values():
        o = OMDS_ROTULO.get(tr.UGS.get(v["ug"], ""))
        if not o:
            continue
        aliq, liqd = round(v["c101"] + v["c102"], 2), round(v["c103"] + v["c104"], 2)
        dias = None
        if aliq > 0.005:
            d, m, a = v["dia"].split("/")
            dias = (ref - dt.date(int(a), int(m), int(d))).days
        for r in (por[o], por_ug.setdefault(o, {}).setdefault(v["ug"], dict(base))):  # OMDS e a UG (160xxx/167xxx)
            r["empenhado"] += v["liq"]
            r["liquidado"] += liqd
            if dias is None:
                continue
            r["a_liquidar"] += aliq
            r["ne_com_saldo"] += 1
            if dias > 60:
                r["mais60_valor"] += aliq
                r["mais60_ne"] += 1
                if liqd <= 0.005:
                    r["mais60_sem_nenhuma_liq_valor"] += aliq
                    r["mais60_sem_nenhuma_liq_ne"] += 1
            if dias > 90:
                r["mais90_valor"] += aliq
                r["mais90_ne"] += 1

    def fecha(r):
        for k in r:
            r[k] = round(r[k], 2) if isinstance(r[k], float) else r[k]
        r["pct_liquidado"] = round(100 * r["liquidado"] / r["empenhado"], 2) if r["empenhado"] else 0.0

    total = dict(base)
    for o, r in por.items():
        fecha(r)
        for k in base:
            total[k] += r[k]
        r["por_ug"] = {}
        for ug, ru in sorted(por_ug.get(o, {}).items()):
            fecha(ru)
            r["por_ug"][ug] = ru
    total = {k: round(v, 2) if isinstance(v, float) else v for k, v in total.items()}
    total["pct_liquidado"] = round(100 * total["liquidado"] / total["empenhado"], 2) if total["empenhado"] else 0.0
    return {"data_dado": data_exec, "fonte": "TG, assinatura «Emissão 5229 x execução 6229 por NE 2026» (contas 6229201xx), pela ponte P-041",
            "regra": "a liquidar = 622920101 + 622920102; liquidado = 622920103 + 622920104; idade em dias corridos desde a emissão",
            "por_omds": por, "total": total}


def ler_info(texto):
    """TSV da informação complementar (mesmas posições do CSV manual) -> {NE: {mod, chave, desc, item23}}."""
    out = {}
    for r in _tsv(texto):
        if len(r) >= 9 and RE_NE.match(r[5].strip()):
            ne = r[5].strip()
            if ne in out:
                raise ValueError("NE repetida na informação complementar: %s" % ne)
            out[ne] = {"mod": r[3].strip(), "chave": r[6].strip(), "desc": r[7].strip(), "item23": num(r[8])}
    return out


def montar_entradas(texto_emissao, texto_info):
    """-> (liquido, chaves) no formato de gof_extrato_tg.gerar. Erro se não conferir."""
    em, info = agregar_emissao(texto_emissao), ler_info(texto_info)
    if not em or not info:
        raise ValueError("arquivo vazio (emissão %d NE, informação %d NE)" % (len(em), len(info)))
    for ne in set(em) - set(info):
        if abs(em[ne]["liq"]) > 0.005:
            raise ValueError("NE com líquido e sem informação complementar: %s" % ne)
    def br(x):  # formato do CSV do TG: gof_extrato_tg.num() trata «.» como milhar e «,» como decimal
        return ("%.2f" % x).replace(".", ",")

    liquido, chaves = {}, {}
    for ne, v in em.items():
        i = info.get(ne, {"mod": "", "chave": "", "desc": "", "item23": 0.0})
        liquido[ne] = {"ug": v["ug"], "dia_emissao": v["dia"], "emissao_522920101": br(v["e101"]),
                       "empenhado_liquido_6229201": br(v["liq"]), "modalidade": i["mod"], "descricao": i["desc"]}
        chaves[ne] = {"chave": i["chave"], "item23": i["item23"]}
    for ne in set(info) - set(em):
        chaves[ne] = {"chave": info[ne]["chave"], "item23": info[ne]["item23"]}  # gerar() acusa se tiver valor
    return liquido, chaves


def dia_util_anterior(d):
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def escolher_par(nomes):
    """Lista de nomes de arquivo -> data (AAAA-MM-DD) do par completo mais recente, ou None."""
    por_dia = {}
    for n in nomes:
        m = RE_ARQ.match(n)
        if m:
            por_dia.setdefault(m.group(1), set()).add(m.group(2))
    completos = sorted(d for d, k in por_dia.items() if k == {"emissao_sem_pessoa", "info_complementar"})
    return completos[-1] if completos else None


# --- Drive (conta de serviço só de leitura) -----------------------------------------------------------------------
def _get(url, tok):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def listar_pasta(tok, nome=None):
    """Arquivos da pasta da ponte. `nome` vem do config (`assinaturas_tg.pasta_drive`); sem ele, o nome histórico."""
    nome = nome or cfg.pasta_ponte()
    q = "name = '%s' and mimeType = 'application/vnd.google-apps.folder' and trashed = false" % nome
    u = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode({"q": q, "fields": "files(id,name)"})
    pastas = json.loads(_get(u, tok))["files"]
    if len(pastas) != 1:
        raise RuntimeError("pasta %s: %d encontradas (esperada 1, compartilhada com a conta de serviço)" % (nome, len(pastas)))
    print("PONTE: pasta do Drive «%s» (1 encontrada)" % nome)
    q = "'%s' in parents and trashed = false" % pastas[0]["id"]
    u = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(
        {"q": q, "fields": "files(id,name)", "pageSize": 1000, "orderBy": "name desc"})
    return {f["name"]: f["id"] for f in json.loads(_get(u, tok))["files"]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fichas", default=None, help="fichas PNCP da carteira GCALC; sem ele (OM sem o bloco), nenhum pregão")
    ap.add_argument("--saida", required=True, help="dados/execucao")
    o = ap.parse_args(argv)
    import gof_google

    saida = Path(o.saida)
    vigente = saida / "ultimo.json"
    data_vigente = json.loads(vigente.read_text(encoding="utf-8"))["data_execucao"] if vigente.exists() else ""
    try:
        tok = gof_google.token()
        arquivos = listar_pasta(tok)
        entrega = escolher_par(arquivos)
        if not entrega:
            print("PONTE: nenhum par completo na pasta %s; extrato vigente %s mantido" % (cfg.pasta_ponte(), data_vigente))
            return 2
        data_exec = dia_util_anterior(dt.date.fromisoformat(entrega)).isoformat()
        if data_exec <= data_vigente:
            print("PONTE: par de %s (dados até %s) não é mais novo que o vigente (%s); nada a fazer" % (entrega, data_exec, data_vigente))
            return 0
        brutos = {k: _get("https://www.googleapis.com/drive/v3/files/%s?alt=media" % arquivos["%s_%s.tsv" % (entrega, k)], tok)
                  for k in ("emissao_sem_pessoa", "info_complementar")}
        liquido, chaves = montar_entradas(brutos["emissao_sem_pessoa"].decode("utf-8"), brutos["info_complementar"].decode("utf-8"))
        liq_omds = liquidacao(agregar_emissao(brutos["emissao_sem_pessoa"].decode("utf-8")), data_exec)
        fichas = tr.ficha_de_pncp(json.load(open(o.fichas, encoding="utf-8"))) if o.fichas else []
        origem = [{"arquivo": "%s_%s.tsv (assinatura do TG via ponte)" % (entrega, k), "sha256": hashlib.sha256(b).hexdigest()}
                  for k, b in brutos.items()]
        extrato = ext.gerar(liquido, chaves, fichas, data_exec, origem)
    except (OSError, ValueError, RuntimeError, KeyError) as e:  # rede/Drive, conferência, pasta, par: segue o anterior
        print("PONTE: falhou (%s: %s); extrato vigente %s mantido" % (type(e).__name__, e, data_vigente))
        return 2
    pasta = saida / data_exec
    pasta.mkdir(parents=True, exist_ok=True)
    corpo = json.dumps(extrato, ensure_ascii=False, indent=0)
    (pasta / "extrato.json").write_text(corpo, encoding="utf-8")
    (pasta / "SHA256SUMS").write_text(hashlib.sha256(corpo.encode("utf-8")).hexdigest() + "  extrato.json\n", encoding="utf-8")
    vigente.write_text(corpo, encoding="utf-8")
    pl = saida.parent / "liquidacao"
    pl.mkdir(parents=True, exist_ok=True)
    (pl / "ultimo.json").write_text(json.dumps(liq_omds, ensure_ascii=False, indent=1), encoding="utf-8")
    print("PONTE: extrato de %s (entrega %s): %d NE, líquido R$ %.2f = item 23" % (data_exec, entrega, len(extrato["ne"]), extrato["total_item23"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
