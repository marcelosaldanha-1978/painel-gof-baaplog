# -*- coding: utf-8 -*-
"""
gof_contratos.py (v0.1, 24nov2026) — CONTRATOS VIGENTES por OMDS (bloco `contratos`, mínimo, release v2.4).

Fonte: API pública do Contratos.gov.br, `/contrato/ug/{ug}` (sem login), pela UG 160 de cada OMDS do config.
Reusa `http()` (repetição e espera em HTTP 429, cache opcional) e `num()` de gof_capacidade.py, sem alterá-lo.

Regras da v2.4 (especificação P-003 v0.1):
  - vigente = `vigencia_fim` >= hoje (não `situacao == "Ativo"`: «ativo» não é «vigente»);
  - só despesa; campos exibidos: número, tipo, objeto (200 car.), vigência, dias para vencer, faixa, valor global
    «como teto» (o valor do instrumento, não o que foi executado);
  - SEM fornecedor e SEM CNPJ (aguarda decisão do Diretor/OD sobre a página pública); nenhum dado de pessoa;
  - o empenhado que a API informa NÃO é exibido (indício; diverge do TG). Contratos × execução virá do TG.
Falha da API numa OMDS -> a OMDS sai com `indisponivel` e ressalva; as demais seguem. Falha em todas -> nada escrito.
"""
import datetime as dt
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import gof_capacidade as cap  # noqa: E402  (http com 429 e num pt-BR)
import gof_config as cfg  # noqa: E402

FAIXAS = ((90, "até 90 dias"), (180, "91 a 180 dias"), (365, "181 a 365 dias"))


def faixa(dias):
    return next((r for lim, r in FAIXAS if dias <= lim), "mais de 365 dias")


def vigentes(lista, hoje):
    """Registros da API -> contratos de despesa vigentes em `hoje`, só com os campos da v2.4, por fim de vigência."""
    out = []
    for c in lista or []:
        if c.get("receita_despesa") != "Despesa":
            continue
        try:
            fim = dt.date.fromisoformat((c.get("vigencia_fim") or "")[:10])
        except ValueError:
            continue  # sem data de fim legível: não se afirma vigência
        if fim < hoje:
            continue
        dias = (fim - hoje).days
        out.append({
            "numero": c.get("numero"), "tipo": c.get("tipo"), "objeto": (c.get("objeto") or "").strip()[:200],
            "vigencia_inicio": (c.get("vigencia_inicio") or "")[:10] or None, "vigencia_fim": fim.isoformat(),
            "dias_para_vencer": dias, "faixa": faixa(dias), "valor_global_teto": round(cap.num(c.get("valor_global")), 2),
            "situacao_api": c.get("situacao"),
        })
    return sorted(out, key=lambda x: (x["vigencia_fim"], x["numero"] or ""))


def coletar(ug):
    return cap.http(cap.CTR + "/contrato/ug/%s" % ug)


def montar(hoje, ler=coletar, config=None):
    """-> dict de contratos.json; `ler(ug)` devolve a lista da API (trocável nos testes)."""
    por_omds, ressalvas = [], []
    for o in cfg.omds(config):
        base = {"omds": o["chave"], "rotulo": o["rotulo"], "ug": o["ug160"]}
        try:
            cs = vigentes(ler(o["ug160"]), hoje)
        except (RuntimeError, OSError, ValueError) as e:
            por_omds.append(dict(base, indisponivel=True, contratos=[]))
            ressalvas.append("%s: API do Contratos.gov.br não respondeu (%s)" % (o["rotulo"], str(e)[-80:]))
            continue
        por_omds.append(dict(base, indisponivel=False, contratos=cs, quantidade=len(cs),
                             teto_total=round(sum(c["valor_global_teto"] for c in cs), 2),
                             vencem_90=sum(c["dias_para_vencer"] <= 90 for c in cs),
                             vencem_180=sum(c["dias_para_vencer"] <= 180 for c in cs),
                             vencem_365=sum(c["dias_para_vencer"] <= 365 for c in cs)))
    if por_omds and all(x["indisponivel"] for x in por_omds):
        raise RuntimeError("API do Contratos.gov.br indisponível para todas as OMDS")
    return {"data_coleta": hoje.isoformat(), "por_omds": por_omds, "ressalvas": ressalvas,
            "fonte": "API pública do Contratos.gov.br (/contrato/ug/{ug}), UG 160 de cada OMDS",
            "regra": "vigente = fim da vigência na data da coleta ou depois; valor global como teto do instrumento; "
                     "sem fornecedor nem CNPJ; empenhado da API não exibido (a execução vem do TG)"}


def main(argv=None):
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(description="bloco contratos (mínimo): contratos vigentes por OMDS")
    ap.add_argument("--saida", default="../dados/contratos/contratos.json")
    ap.add_argument("--cache", default=None)
    ap.add_argument("--hoje", default=None, help="AAAA-MM-DD (padrão: hoje)")
    o = ap.parse_args(argv)
    if not cfg.bloco_ligado("contratos"):
        print("CONTRATOS: bloco desligado no config; nada a fazer")
        return 0
    cap.CACHE = o.cache
    hoje = dt.date.fromisoformat(o.hoje) if o.hoje else dt.date.today()
    saida = Path(o.saida)
    try:
        r = montar(hoje)
    except RuntimeError as e:
        print("CONTRATOS: falhou (%s); arquivo vigente mantido" % e)
        return 2
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("CONTRATOS: %s — %d contrato(s) vigente(s), %d ressalva(s)"
          % (r["data_coleta"], sum(len(x["contratos"]) for x in r["por_omds"]), len(r["ressalvas"])))
    return 0


if __name__ == "__main__":
    _sys.exit(main())
