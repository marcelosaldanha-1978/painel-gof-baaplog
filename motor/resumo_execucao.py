# -*- coding: utf-8 -*-
"""
resumo_execucao.py (v1, 23nov2026) — resumo da montagem na página da execução do GitHub Actions (job summary).

Lê as linhas-chave que as etapas da montagem gravaram em arquivos de log (PONTE, REGUA, RECALCULO, VERIFICACAO,
NAVEGADOR) e o `dados.json` montado, e imprime uma tabela em Markdown para `$GITHUB_STEP_SUMMARY`. Não decide nada:
só mostra. Falha de leitura vira «—» (o resumo nunca derruba a montagem).
Uso: python resumo_execucao.py --logs a.log b.log --dados saida/dados.json --evento schedule --resultado success
"""
import argparse
import json
import os
import re

CHAVES = ("PONTE", "REGUA", "RECALCULO", "VERIFICACAO", "NAVEGADOR")
ORIGEM = {"repository_dispatch": "evento (ponte do TG)", "schedule": "agenda (reserva)",
          "workflow_dispatch": "disparo manual", "push": "push"}


def linhas_chave(textos):
    """Última linha de cada chave encontrada nos textos de log (sem prefixo de horário)."""
    achado = {}
    for t in textos:
        for ln in t.splitlines():
            m = re.match(r"^\s*(?:\S+Z\s+)?(%s):\s*(.*)$" % "|".join(CHAVES), ln)
            if m:
                achado[m.group(1)] = m.group(2).strip()
    return achado


def montar(textos, dados, evento, resultado):
    k = linhas_chave(textos)
    meta = (dados or {}).get("meta", {})
    b1 = (dados or {}).get("b1", {}) or {}
    rg = (dados or {}).get("regua", {}) or {}
    ok = resultado == "success"
    out = ["### %s Montagem do painel GOF-BaApLog" % ("✅" if ok else "⛔"), "",
           "| Item | Resultado |", "|---|---|",
           "| Origem | %s |" % ORIGEM.get(evento or "", evento or "—"),
           "| Publicação | %s |" % ("liberada (todos os portões passaram)" if ok else "não publicada; fica a versão anterior"),
           "| Dados do B1 (empenho) | até %s · fonte %s |" % (b1.get("data_dado", "—"), meta.get("fonte_b1", "—")),
           "| Régua (crédito em tela, RPNP) | até %s |" % rg.get("data_dado", "—")]
    for c in CHAVES:
        out.append("| %s | %s |" % (c.capitalize(), k.get(c, "—").replace("|", "/")))
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", nargs="*", default=[])
    ap.add_argument("--dados", default=None)
    ap.add_argument("--evento", default=os.environ.get("EVENTO", ""))
    ap.add_argument("--resultado", default=os.environ.get("RESULTADO", ""))
    o = ap.parse_args(argv)
    textos = []
    for f in o.logs:
        try:
            with open(f, encoding="utf-8", errors="replace") as h:
                textos.append(h.read())
        except OSError:
            pass
    dados = None
    if o.dados:
        try:
            with open(o.dados, encoding="utf-8") as h:
                dados = json.load(h)
        except (OSError, ValueError):
            dados = None
    print(montar(textos, dados, o.evento, o.resultado))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
