# -*- coding: utf-8 -*-
"""
gof_rp_por_ano.py (v0.1, 24nov2026) — RESTOS A PAGAR NÃO PROCESSADOS POR ANO DE INSCRIÇÃO (bloco `rp_por_ano`, v2.4).

Entrada (assinatura do TG copiada pelo Apps Script para a pasta privada `PONTE_TG_SEM_PESSOA`, SEM favorecido):
  <entrega>_rpnp_por_ne.csv   «<prefixo>RPNP por NE»: por UG Executora e NE, Movim. Líquido das contas 531xx (inscrição e
                              reinscrição) e 631xx (a liquidar, em liquidação, liquidado, pago, bloqueado, excetuado, cancelado)
Saída: `dados/encerramento/rp_por_ano.json`, só agregado por UG/OMDS e ano (nenhuma NE individual, nenhuma pessoa).

Ano de inscrição = ano do número da NE (…2024NE000426 -> 2024). Datas legais por ano *a* (Dec. 93.872/1986, art. 68,
na redação vigente — conferir a cada exercício): bloqueio em 30/06/(a+2); o desbloqueado e não liquidado é cancelado em
31/12/(a+3). Saldo de RPNP excetuado do cancelamento (Lei 14.133/2021, art. 105, contas 63181/63182) não entra no alerta.

Portões (a montagem não escreve se falharem; segue o arquivo anterior):
  P-RP-1  Σ 631100000 por UG = item 43 da régua (regua.json), mesma data do dado, ao centavo.
  P-RP-4  arquivo com coluna de favorecido é recusado (a ponte tem de cortar pelo nome do cabeçalho).
  P-RP-5  fechamento por NE: Σ 531xx = Σ 631xx (medido em 24/11/2026: 515 NE, todas fecham ao centavo).
  (leitura) a linha «Total» que o TG põe por UG não é somada: é conferida com a soma das NE, conta a conta.
Leitor tolerante: UTF-16, UTF-8 ou cp1252; tabulação ou vírgula; números «1.060,78» ou «(1959.88)»; conta sem
movimento some do CSV (ausência = zero).
"""
import collections
import datetime as dt
import io
import re
import sys as _sys
import zipfile
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import gof_config as cfg  # noqa: E402
from gof_regua_tg import linhas  # noqa: E402  (mesma leitura tolerante da régua)

RE_CONTA = re.compile(r"\d{9}")
RE_NE = re.compile(r"^\d{6}\d{5}(20\d\d)NE\d{6}$")
TOL = 0.005  # meio centavo: as identidades são exatas

# papel de cada conta no bloco (prefixo -> campo); 6316x fica «a classificar» até a 1ª carga real medir o uso
PAPEL = (
    ("5311", "inscrito"), ("5312", "inscrito"), ("5316", "inscrito"),
    ("631100000", "a_liquidar"), ("631200000", "em_liquidacao"),
    ("631300000", "liquidado"), ("631400000", "liquidado"),
    ("6315", "bloqueado"), ("6318", "excetuado"), ("6319", "cancelado"),
    ("6316", "a_classificar"),
)
CAMPOS = ("inscrito", "liquidado", "cancelado", "a_liquidar", "em_liquidacao", "bloqueado", "excetuado", "a_classificar")


def papel(conta):
    return next((p for pre, p in PAPEL if conta.startswith(pre)), None)


def num(s):
    """«1.060,78» (pt-BR) ou «(1959.88)» (negativo com ponto decimal, como o TG exporta) -> float."""
    s = (s or "").strip().replace('"', "")
    if not s:
        return 0.0
    neg = s.startswith("(") or s.startswith("-")
    s = s.strip("()-").strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:  # «1.234.567» sem decimais
        s = s.replace(".", "")
    try:
        x = float(s)
    except ValueError:
        return 0.0
    return -x if neg else x


def _ug_valida(x, sufixos):
    x = (x or "").strip()
    return x if re.fullmatch(r"16[07]\d{3}", x) and x[3:] in sufixos else None


# ---------------------------------------------------------------- leitura
def ler(b, permitir_favorecido=False, config=None):
    """bytes do CSV -> (linhas por NE agregadas, avisos). Cada linha: {ug, ne, ano, contas{conta: valor}}.

    `permitir_favorecido` existe só para a conferência local com a exportação manual (que traz a coluna); na montagem é
    sempre False (portão P-RP-4). O favorecido nunca é lido nem devolvido."""
    sufixos = {o["ug160"][3:] for o in cfg.omds(config)}
    L = linhas(b)
    h = next((i for i, r in enumerate(L) if sum(bool(RE_CONTA.fullmatch(c)) for c in r) >= 2), None)
    if h is None:
        raise ValueError("RPNP por NE: cabeçalho com as contas contábeis não encontrado")
    cab = L[h]
    if any("favorecido" in c.lower() for r in L[h:h + 3] for c in r) and not permitir_favorecido:
        raise ValueError("RPNP por NE: o arquivo traz coluna de favorecido (portão P-RP-4); a ponte tem de cortá-la")
    cols = {c: j for j, c in enumerate(cab) if RE_CONTA.fullmatch(c)}
    desconhecidas = sorted(c for c in cols if papel(c) is None)
    if desconhecidas:
        raise ValueError("RPNP por NE: conta sem papel no bloco: %s" % ", ".join(desconhecidas))
    por_ne = {}
    totais = collections.defaultdict(collections.Counter)
    avisos = collections.Counter()
    for r in L[h + 1:]:
        ug = next((_ug_valida(c, sufixos) for c in r[:3] if _ug_valida(c, sufixos)), None)
        if not ug:
            continue
        ne = next((c for c in r[:min(len(r), min(cols.values()))] if RE_NE.match(c)), None)
        valores = {c: num(r[j]) for c, j in cols.items() if j < len(r)}
        if not ne and any(c.lower() == "total" for c in r[: min(cols.values())]):
            totais[ug].update(valores)  # subtotal da UG que o TG põe no CSV: conferido abaixo, não somado
            continue
        if not ne:
            if any(abs(x) > TOL for x in valores.values()):
                avisos["linhas sem NE válida (com valor)"] += 1
            continue
        if ne[:6] != ug:
            raise ValueError("RPNP por NE: NE %s na linha da UG %s" % (ne, ug))
        x = por_ne.setdefault(ne, {"ug": ug, "ne": ne, "ano": int(RE_NE.match(ne).group(1)), "contas": collections.Counter()})
        x["contas"].update(valores)
    if not por_ne:
        raise ValueError("RPNP por NE: nenhuma NE das UG da OM no arquivo")
    soma = collections.defaultdict(collections.Counter)
    for x in por_ne.values():
        soma[x["ug"]].update(x["contas"])
    for ug, t in totais.items():  # o subtotal do próprio TG tem de bater com a soma das NE, conta a conta
        ruins = [c for c in set(t) | set(soma[ug]) if abs(t[c] - soma[ug][c]) > TOL]
        if ruins:
            raise ValueError("RPNP por NE: UG %s, soma das NE ≠ «Total» do TG nas contas %s" % (ug, ", ".join(sorted(ruins))))
    return list(por_ne.values()), dict(avisos)


def classificar(contas):
    out = dict.fromkeys(CAMPOS, 0.0)
    for c, x in contas.items():
        out[papel(c)] += x
    return out


def fechamento_por_ne(linhas_ne):
    """Portão P-RP-5: Σ 531xx = Σ 631xx em cada NE. -> lista de NE que não fecham (vazia = passa)."""
    ruins = []
    for x in linhas_ne:
        ins = sum(v for c, v in x["contas"].items() if c.startswith("531"))
        sai = sum(v for c, v in x["contas"].items() if c.startswith("631"))
        if abs(ins - sai) > TOL:
            ruins.append((x["ne"], round(ins - sai, 2)))
    return ruins


# ---------------------------------------------------------------- datas legais
def datas_legais(ano):
    return {"bloqueio": dt.date(ano + 2, 6, 30).isoformat(), "cancelamento": dt.date(ano + 3, 12, 31).isoformat()}


def _indice(x):
    return round(100 * (x["liquidado"] + x["cancelado"]) / x["inscrito"], 2) if abs(x["inscrito"]) > TOL else None


def _linha(base, soma):
    d = dict(base)
    d.update({k: round(soma[k], 2) for k in CAMPOS})
    d["indice"] = _indice(d)
    return d


# ---------------------------------------------------------------- agregação
def agregar(linhas_ne, exercicio=None, config=None):
    """-> {por_ug[], por_omds[], alertas[], nao_fecham[]} (só agregado; nenhuma NE na saída)."""
    exercicio = exercicio or cfg.exercicio(config)
    chave = cfg.ug_para_chave_intercalado(config)
    rot = cfg.rotulo_por_chave(config)
    ordem = cfg.chaves_omds(config)
    ug_ano = collections.defaultdict(lambda: dict.fromkeys(CAMPOS, 0.0))
    for x in linhas_ne:
        s = ug_ano[(x["ug"], x["ano"])]
        for k, v in classificar(x["contas"]).items():
            s[k] += v
    por_ug = []
    om_ano = collections.defaultdict(lambda: dict.fromkeys(CAMPOS, 0.0))
    for (ug, ano), s in sorted(ug_ano.items(), key=lambda t: (ordem.index(chave[t[0][0]]), t[0][0], t[0][1])):
        por_ug.append(_linha({"omds": chave[ug], "ug": ug, "ano": ano, **datas_legais(ano)}, s))
        for k in (ano, "total"):
            for c in CAMPOS:
                om_ano[(chave[ug], k)][c] += s[c]
    por_omds = []
    for o in ordem:
        anos = sorted(a for (oo, a) in om_ano if oo == o and a != "total")
        for a in anos + (["total"] if anos else []):
            base = {"omds": o, "rotulo": rot[o], "ano": a}
            if a != "total":
                base.update(datas_legais(a))
            por_omds.append(_linha(base, om_ano[(o, a)]))
    alertas = []
    for x in por_ug:
        saldo = round(x["a_liquidar"] + x["em_liquidacao"] + x["bloqueado"], 2)
        if x["ano"] <= exercicio - 3 and saldo > TOL:
            alertas.append({"omds": x["omds"], "ug": x["ug"], "ano": x["ano"], "saldo": saldo,
                            "evento": "cancelamento", "data": "%d-12-31" % exercicio,
                            "texto": "RPNP de %d com saldo: cancela em 31/12/%d se não liquidado" % (x["ano"], exercicio)})
        if abs(x["a_classificar"]) > TOL:
            alertas.append({"omds": x["omds"], "ug": x["ug"], "ano": x["ano"], "saldo": x["a_classificar"],
                            "evento": "conta_6316", "data": None,
                            "texto": "saldo nas contas 6316x (papel a classificar): conferir antes de publicar"})
    return {"por_ug": por_ug, "por_omds": por_omds, "alertas": alertas, "nao_fecham": fechamento_por_ne(linhas_ne)}


def identidade_regua(res, regua):
    """Portão P-RP-1: Σ a_liquidar (631100000) por UG = rpnp_a_liquidar (item 43) da régua. -> lista de divergências."""
    item43 = {ug: u["rpnp_a_liquidar"] for o in (regua.get("por_omds") or {}).values() for ug, u in o["por_ug"].items()}
    nosso = collections.Counter()
    for x in res["por_ug"]:
        nosso[x["ug"]] += x["a_liquidar"]
    div = []
    for ug in sorted(set(item43) | set(nosso)):
        a, b = round(nosso.get(ug, 0.0), 2), round(item43.get(ug, 0.0), 2)
        if abs(a - b) > TOL:
            div.append({"ug": ug, "rpnp_por_ne": a, "item43": b, "diferenca": round(a - b, 2)})
    return div


def calcular(b, regua, data_dado, config=None, permitir_favorecido=False):
    """bytes do CSV + regua.json do mesmo dia -> dict de rp_por_ano.json, ou ValueError se um portão falhar."""
    if (regua or {}).get("data_dado") != data_dado:
        raise ValueError("RPNP por NE de %s sem régua do mesmo dia (régua: %s) — portão P-RP-1 não verificável"
                         % (data_dado, (regua or {}).get("data_dado")))
    linhas_ne, avisos = ler(b, permitir_favorecido=permitir_favorecido, config=config)
    res = agregar(linhas_ne, config=config)
    if res["nao_fecham"]:
        raise ValueError("portão P-RP-5: %d NE com Σ531 ≠ Σ631 (ex.: %s)" % (len(res["nao_fecham"]), res["nao_fecham"][0]))
    div = identidade_regua(res, regua)
    if div:
        raise ValueError("portão P-RP-1: Σ 631100000 por NE ≠ item 43 da régua: %s" % div)
    del res["nao_fecham"]
    res.update({"data_dado": data_dado, "avisos": avisos, "nes": len(linhas_ne),
                "conferencia": "Σ 631100000 por NE = item 43 da régua em todas as UG; Σ531 = Σ631 em cada NE",
                "criterio_indice": "(liquidado + cancelado) ÷ (inscrito + reinscrito), Diretriz 26-27"})
    return res


# ---------------------------------------------------------------- passo da montagem (nuvem)
RE_ARQ = re.compile(r"^(\d{4}-\d{2}-\d{2})_rpnp_por_ne\.(csv|zip)$")


def escolher(nomes):
    """Data de entrega (AAAA-MM-DD) do arquivo mais recente, ou None."""
    ds = sorted(m.group(1) for m in map(RE_ARQ.match, nomes) if m)
    return ds[-1] if ds else None


def main(argv=None):
    import argparse
    import json
    from pathlib import Path

    import gof_google
    import gof_ponte_tg as pt

    ap = argparse.ArgumentParser(description="bloco rp_por_ano: RPNP por ano de inscrição (assinatura RPNP por NE)")
    ap.add_argument("--regua", default="../dados/encerramento/regua.json")
    ap.add_argument("--saida", default="../dados/encerramento/rp_por_ano.json")
    ap.add_argument("--local", default=None, help="CSV local (conferência fora da nuvem; aceita a coluna de favorecido)")
    ap.add_argument("--data-dado", default=None, help="com --local: AAAA-MM-DD do dado")
    o = ap.parse_args(argv)
    if not cfg.bloco_ligado("rp_por_ano"):
        print("RP_POR_ANO: bloco desligado no config; nada a fazer")
        return 0
    saida, regua_p = Path(o.saida), Path(o.regua)
    ant = json.loads(saida.read_text(encoding="utf-8")) if saida.exists() else {}
    regua = json.loads(regua_p.read_text(encoding="utf-8")) if regua_p.exists() else {}
    try:
        if o.local:
            b, data_dado, origem = Path(o.local).read_bytes(), o.data_dado, "exportação manual (conferência local)"
            r = calcular(b, regua, data_dado, permitir_favorecido=True)
            print(json.dumps(r, ensure_ascii=False, indent=1))
            return 0  # conferência local não escreve a saída da página
        tok = gof_google.token()
        arqs = pt.listar_pasta(tok)
        entrega = escolher(arqs)
        if not entrega:
            print("RP_POR_ANO: nenhum arquivo rpnp_por_ne na pasta; vigente (%s) mantido" % ant.get("data_dado"))
            return 2
        data_dado = pt.dia_util_anterior(dt.date.fromisoformat(entrega)).isoformat()
        if data_dado <= (ant.get("data_dado") or ""):
            print("RP_POR_ANO: arquivo de %s não é mais novo que o vigente; nada a fazer" % entrega)
            return 0
        nome = next(n for n in arqs if RE_ARQ.match(n) and n.startswith(entrega + "_"))
        b = pt._get("https://www.googleapis.com/drive/v3/files/%s?alt=media" % arqs[nome], tok)
        if nome.endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(b))
            b = z.read(z.namelist()[0])
        origem = nome + " (assinatura do TG via ponte)"
        r = calcular(b, regua, data_dado)
    except (OSError, ValueError, RuntimeError, KeyError, StopIteration) as e:
        print("RP_POR_ANO: falhou (%s: %s); vigente (%s) mantido" % (type(e).__name__, e, ant.get("data_dado")))
        return 2
    r["fonte"] = "TG, assinatura «%sRPNP por NE» (%s)" % ((cfg.carregar().get("assinaturas_tg") or {}).get("prefixo_assunto", ""), origem)
    saida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("RP_POR_ANO: dados até %s — %d NE, %d alerta(s)" % (r["data_dado"], r["nes"], len(r["alertas"])))
    return 0


if __name__ == "__main__":
    _sys.exit(main())
