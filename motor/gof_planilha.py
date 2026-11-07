# -*- coding: utf-8 -*-
"""
gof_planilha.py (v1, 07nov2026) — leitura diária da planilha GCALC pela conta de serviço só de leitura (passo 5, PLANO v2.4).

Lê `Controle Processos` (A3:AZ15; só as colunas públicas de COLS — contatos AF-AI e observações ficam fora) e a linha de
KPI do `Painel` (A3:E5), e grava `dados/carteira_processos.json` e `dados/kpis_painel.json` no MESMO formato que as cópias
manuais tinham (valores formatados como na planilha). Nunca escreve na planilha.

Guardas: 12 linhas com processo não vazio, cabeçalhos esperados nas colunas-chave, KPI com 5 campos; se algo falhar,
sai com código 1 e NÃO grava (a montagem segue com o JSON versionado anterior).
Uso: python gof_planilha.py --saida dados [--hoje AAAA-MM-DD]
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import gof_google
import requests

SP = "1XTWMvf47PyWEi5eFg1wk16uOTse8s-wLvSV69pjVQd0"
API = "https://sheets.googleapis.com/v4/spreadsheets/" + SP
# colunas públicas (mesmo mapa de gof_painel.COLS; índice 0 = coluna A)
COLS = {"ordem": 0, "processo": 1, "objeto": 2, "ugg": 3, "uasg": 4, "estimado": 7, "homologado": 29, "link": 30,
        "prazo_meta": 38, "status_prazo": 39, "fase": 40, "etapa": 41, "pct_total": 46, "proxima_acao": 48,
        "ultima_atualizacao": 50, "situacao_pncp": 51}
CABECALHOS = {1: "Processo", 3: "UGG", 4: "UASG"}  # trechos esperados no cabeçalho (L3), sem acento
KPI_CAMPOS = ("processos", "valor_estimado", "score_bsc", "pct_no_prazo", "capacidade_instalada")


def _sem_acento(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn").lower()


def ler(h):
    r = requests.get(API + "/values:batchGet", headers=h, timeout=90, params=[
        ("valueRenderOption", "FORMATTED_VALUE"), ("ranges", "'Controle Processos'!A3:AZ15"), ("ranges", "Painel!A3:E5")])
    r.raise_for_status()
    v = r.json()["valueRanges"]
    return v[0].get("values", []), v[1].get("values", [])


def _cel(lin, i):
    return str(lin[i]).strip() if i < len(lin) and lin[i] is not None else ""


def carteira(linhas):
    cab = linhas[0]
    for i, trecho in CABECALHOS.items():
        if i >= len(cab) or trecho.lower() not in _sem_acento(cab[i]):
            raise RuntimeError("cabeçalho inesperado na coluna %d: %r" % (i, cab[i] if i < len(cab) else ""))
    out = []
    for lin in linhas[1:]:
        if not _cel(lin, 1):
            continue
        out.append({k: _cel(lin, i) for k, i in COLS.items()})
    if len(out) != 12:
        raise RuntimeError("esperava 12 processos, li %d" % len(out))
    return out


def kpis(linhas):
    if len(linhas) < 3 or len(linhas[2]) < 5:
        raise RuntimeError("Painel!A3:E5 incompleto")
    v = linhas[2]
    return {k: str(v[i]).strip() for i, k in enumerate(KPI_CAMPOS)}


def classe(score):
    try:
        s = float(str(score).replace("%", "").replace(",", "."))
    except ValueError:
        return "?"
    return "BOM" if s >= 70 else ("REGULAR" if s >= 50 else "CRÍTICO")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="dados")
    ap.add_argument("--hoje", default=None)
    o = ap.parse_args(argv)
    hoje = o.hoje or dt.date.today().isoformat()
    h = {"Authorization": "Bearer " + gof_google.token()}
    cp, pn = ler(h)
    procs, k = carteira(cp), kpis(pn)
    origem = "Planilha GCALC_BAAPLOG_-_VF, lida em %s pela conta de serviço só de leitura (%s)" % (hoje, gof_google.conta())
    cart = {"versao": 2, "lido_em": hoje, "fonte": origem + "; aba Controle Processos, só colunas públicas (sem contatos nem observações)",
            "atualizar_quando": "todo dia, na montagem (passo 5 do PLANO v2.4)", "processos": procs}
    kp = dict({"lido_em": hoje, "origem": origem + "; aba Painel, linha 5 (A5:E5)"}, **k)
    kp["classe"] = classe(k["score_bsc"])
    kp["regra_classe"] = "BSC v2: 70 ou mais BOM; 50 a 69 REGULAR; abaixo de 50 CRÍTICO (CLAUDE.md do projeto)"
    s = Path(o.saida)
    json.dump(cart, open(s / "carteira_processos.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(kp, open(s / "kpis_painel.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("PLANILHA: %d processos; KPI %s %s %s; lida por %s" % (len(procs), k["score_bsc"], kp["classe"], k["capacidade_instalada"], gof_google.conta()))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, KeyError) as e:
        print("PLANILHA: falha (%s); mantém o JSON versionado" % str(e)[:200])
        sys.exit(1)
