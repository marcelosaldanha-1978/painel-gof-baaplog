# -*- coding: utf-8 -*-
"""
gof_regua_tg.py (v1.0, 23nov2026) — RÉGUA DO ENCERRAMENTO todo dia útil, na nuvem: crédito em tela (e o vencido), %
do crédito recebido e RPNP, por OMDS e por UG (160xxx e 167xxx). Porta para o painel o cálculo auditado de
`02_EVIDENCIAS_E_REGISTROS/TG_CONFERENCIA_2026-11-18/posicao_18nov.py` (LOG-274 a 277).

Entradas (assinaturas do TG copiadas pelo Apps Script `v2PonteTG` para a pasta privada `PONTE_TG_SEM_PESSOA`):
  <entrega>_regua_por_ug.csv          «Execução Crédito e RPNP por UG (v1.0)»: itens 15,16,19,23,24,25,26,28,43,45,47,48 por UG
  <entrega>_credito_por_nc.csv        «Crédito por NC» com UG Responsável, PTRES e Fonte: item 19 por NC (célula)
  <entrega>_credito_movimento.csv     «Crédito por NC movimento 2026»: item 15 por NC no ano (recolhimentos/anulações)
Os CSV ficam só no Drive privado; a saída é SEM texto de NC e sem pessoa (totais por UG/OMDS).
Leitor tolerante: UTF-16 (assinatura) ou cp1252 (exportação manual); tabulação ou vírgula; itens nas linhas ou colunas.

Formato documento (P-016 do PAINEL GOF DF, 25nov2026): onde o «Crédito por NC» não alcança a provisão (NC = -9), o
trio vem como régua + crédito por célula (item 19 por UG, PI, ND e UGR, SEM NC) + «NC recebidas documento» (uma linha
por célula de NC, valor sempre positivo, anulação pela operação). O documento é reconhecido pelo cabeçalho
«NC Célula - Valor»; as NC ligam-se às células pelo endereço (UG, PI, grupo da ND, UGR), pelo valor recebido. A faixa
piso/teto fica mais larga que a do saldo por NC, mas o piso continua conservador. Sem esse cabeçalho, nada muda.

Vencido = saldo da célula coberto por NC recebida de outra UG com prazo escrito anterior à data de referência
(dia útil seguinte aos dados). Piso/teto porque o TG não dá saldo por NC. Ajuste de ND feito pela própria UG não é
rastreado até a NC de origem (a auditoria do LOG-277 fez isso à mão): o piso automático é CONSERVADOR.
"""
import collections
import csv
import datetime as dt
import io
import re
import sys as _sys
import unicodedata
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import gof_config as cfg  # noqa: E402

# OMDS da OM (config/om.json): sufixo da UG (3 dígitos) -> rótulo, e a ordem de exibição
OM = cfg.rotulo_por_sufixo()
ORDEM = cfg.ordem_rotulos()


# ---------------------------------------------------------------- leitura tolerante
def texto(b):
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b.decode("utf-16")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("cp1252", errors="replace")


def linhas(b):
    t = texto(b)
    # tabulação se alguma das primeiras linhas tiver 3+ tabs (o texto do filtro tem vírgulas e engana uma contagem simples)
    sep = "\t" if any(ln.count("\t") >= 3 for ln in t.splitlines()[:80]) else ","
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(t), delimiter=sep)]


def v(s):
    s = (s or "").strip().replace('"', "")
    if not s:
        return 0.0
    neg = s.startswith("(") or s.startswith("-")
    s = s.strip("()-").replace(".", "").replace(",", ".")
    try:
        return -float(s) if neg else float(s)
    except ValueError:
        return 0.0


def _ug(x):
    x = (x or "").strip()
    return x if re.fullmatch(r"16[07]\d{3}", x) and x[3:] in OM else None


# ---------------------------------------------------------------- régua por UG
def regua_por_ug(b):
    """Itens 15..48 por UG. Aceita itens nas colunas (cabeçalho com códigos '15','16',...) — o formato do relatório."""
    L = linhas(b)
    h = next(i for i, r in enumerate(L) if any(c in ("15", "19", "23") for c in r))
    cab = L[h]
    cols = {c: j for j, c in enumerate(cab) if re.fullmatch(r"\d{2,3}", c)}
    reg = collections.defaultdict(collections.Counter)
    for r in L[h + 1:]:
        ug = next((_ug(c) for c in r[:3] if _ug(c)), None)
        if not ug:
            continue
        for k, j in cols.items():
            if j < len(r):
                reg[ug][k] += v(r[j])
    if not reg:
        raise ValueError("régua: nenhuma UG das OMDS no CSV")
    return reg


def linha_regua(r):
    prov = r["15"] - r["16"]
    return {"provisao": round(prov, 2), "empenhado": round(r["23"], 2), "liquidado": round(r["25"], 2),
            "a_liquidar": round(r["24"], 2), "em_tela": round(r["19"], 2),
            "pct_empenhado": round(100 * r["23"] / prov, 2) if prov else 0.0,
            "pct_liquidado": round(100 * r["25"] / prov, 2) if prov else 0.0,
            "rpnp_a_liquidar": round(r["43"], 2), "rpnp_bloqueado": round(r["48"], 2)}


# ---------------------------------------------------------------- prazo escrito na NC (prazo_v2.py, 12nov2026)
FER = cfg.feriados_ano()  # feriados nacionais do exercício (config/calendario/encerramento_<ano>.json)
MES = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12}
ATE = r"(?:ATE|AT E|AT)"
M = r"(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)"
PADS = [
    ("data_mes", re.compile(r"(?:EMPENH\w*|EMPH|EMP|PRAZO)\W{0,25}?" + ATE + r"\W{0,3}(\d{1,2})\s*/?\s*" + M + r"\w*\s*/?\s*(\d{2,4})")),
    ("data_num", re.compile(r"(?:EMPENH\w*|EMPH|EMP|PRAZO\W{0,6}(?:PARA|DE)?\W{0,3}EMPENHO)\W{0,25}?(?:" + ATE + r"|:)\W{0,3}(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})")),
    ("prazo_emp", re.compile(r"PRAZO\W{0,3}(?:DE|PARA)?\W{0,3}EMPENHO\W{0,6}(\d{1,2})\s*/?\s*" + M + r"\w*\s*/?\s*(\d{2,4})")),
    ("nh", re.compile(r"(?:EMPENH\w*|EMPH|EMP)[^.]{0,25}?(24|72)\s*H")),
    ("imediato", re.compile(r"(?:EMPENHO|EMPH|EMP)\W{0,3}(?:IMEDIATO|IMTO|IMDT|IMED)")),
    ("48h", re.compile(r"(?:EMPENH\w*|EMPH|EMP)\W{0,10}" + ATE + r"?\W{0,3}48\s*H")),
    ("7du", re.compile(r"(\d{1,2})\s*DIAS?\s*UTEIS")),
    ("dias", re.compile(r"(?:EMPENH\w*|EMPH|EMP)\W{0,10}" + ATE + r"\W{0,3}(\d{1,3})\s*DIAS(?!\s*UTEIS)")),
    ("sem_ano", re.compile(r"(?:(?:EMPENH\w*|EMPH|EMP)\W{0,25}?" + ATE + r"|NAO EMPENHADOS " + ATE + r"|PRAZO)\W{0,3}(\d{1,2})\s*/?\s*(?:DE\s*)?" + M)),
]


def _du(d, n):
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5 and d not in FER:
            n -= 1
    return d


def _ano(a):
    a = int(a)
    return a + 2000 if a < 100 else a


def prazo(textonc, rec):
    t = re.sub(r"\s+", " ", unicodedata.normalize("NFKD", textonc or "").encode("ascii", "ignore").decode().upper())
    for nome, p in PADS:
        m = p.search(t)
        if not m:
            continue
        try:
            if nome in ("data_mes", "prazo_emp"):
                return dt.date(_ano(m.group(3)), MES[m.group(2)], int(m.group(1)))
            if nome == "data_num":
                return dt.date(_ano(m.group(3)), int(m.group(2)), int(m.group(1)))
            if nome == "nh":
                return _du(rec, int(m.group(1)) // 24)
            if nome == "dias":
                return rec + dt.timedelta(days=int(m.group(1)))
            if nome == "sem_ano":
                return dt.date(rec.year, MES[m.group(2)], int(m.group(1)))
            if nome == "imediato":
                return _du(rec, 1)
            if nome == "48h":
                return _du(rec, 2)
            if nome == "7du":
                return _du(rec, int(m.group(1)))
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- tabelas de NC (formato de linhas OU cruzado)
DOC_VALOR = "NC Célula - Valor"


def _eh_documento(L):
    return any(DOC_VALOR in r for r in L[:30])


def _tabela_nc_documento(L):
    """«NC recebidas documento»: uma linha por célula de NC. -> dicts com os nomes que calcular() usa; a UG é o
    favorecido da NC; o valor vem positivo e a anulação recebe sinal negativo (como no item 15)."""
    h = next(i for i, r in enumerate(L) if DOC_VALOR in r)
    idx = {}
    for j, c in enumerate(L[h]):
        if c and c not in idx:
            idx[c] = j
    mapa = {"NC": "NC", "NC - Dia Emissão": "NC - Dia Emissão", "NC - Descrição": "NC - Descrição",
            "NC - Operação (Tipo)": "NC - Operação (Tipo)", "Emitente - UG": "Emitente - UG",
            "PI": "NC Célula - Plano Interno", "Natureza Despesa": "NC Célula - Natureza Despesa",
            "UG Responsável": "NC Célula - UG Responsável", "Fonte Recursos": "NC Célula - Fonte Recurso Detalhada"}
    j_ug = idx.get("NC Item - Favorecido")
    if j_ug is None:
        raise ValueError("documento de NC sem «NC Item - Favorecido»")
    out = []
    for r in L[h + 1:]:
        ug = _ug(r[j_ug]) if j_ug < len(r) else None
        if not ug or idx[DOC_VALOR] >= len(r):
            continue
        g = {k: (r[idx[c]] if c in idx and idx[c] < len(r) else "") for k, c in mapa.items()}
        if not g["Fonte Recursos"] and "NC Célula - Fonte Recurso De" in idx:  # rótulo cortado no CSV
            j = idx["NC Célula - Fonte Recurso De"]
            g["Fonte Recursos"] = r[j] if j < len(r) else ""
        x = abs(v(r[idx[DOC_VALOR]]))
        g["UG Executora"] = ug
        g["valor"] = -x if "ANULACAO" in g["NC - Operação (Tipo)"].upper() else x
        out.append(g)
    return out


def _tabela_nc(b, item):
    """-> lista de dicts com UG Executora, NC, Ação Governo, PI, Natureza Despesa, NC - Descrição, NC - Dia Emissão,
    NC - Operação (Tipo), [UG Responsável, PTRES, Fonte Recursos] e 'valor' do item pedido ('19' ou '15').
    Aceita o item como coluna própria ('19') ou o layout com 'Item Informação' nas linhas."""
    L = linhas(b)
    if _eh_documento(L):
        return _tabela_nc_documento(L)
    h = next(i for i, r in enumerate(L) if "UG Executora" in r or "Emitente - UG" in r)
    cab = L[h]
    idx = {}
    for j, c in enumerate(cab):
        if c and c not in idx:
            idx[c] = j
    rot_col = [j for j, c in enumerate(cab) if c in ("PTRES", "UG Responsável", "Fonte Recursos")]
    if rot_col and h + 5 < len(L):  # leiaute CRUZADO (PTRES, Fonte, UGR e item nas colunas) — despivotar
        c0 = rot_col[0] + 1  # a ordem dos rótulos varia (exportação manual: PTRES primeiro; assinatura: UGR primeiro)
        lab = {L[h + k][c0 - 1]: k for k in range(0, 6) if c0 - 1 < len(L[h + k])}
        k_ptres, k_fonte, k_ugr = lab.get("PTRES", 0), lab.get("Fonte Recursos", 1), lab.get("UG Responsável", 3)
        k_item = max(lab.values()) if lab else 5
        cols = [j for j in range(c0, len(L[h + k_item])) if L[h + k_item][j] == item]
        out = []
        for r in L[h + k_item + 2:]:
            ug = _ug(r[idx["UG Executora"]]) if idx["UG Executora"] < len(r) else None
            if not ug:
                continue
            base = {k: (r[j] if j < len(r) else "") for k, j in idx.items() if j < c0 - 1}
            base["NC - Dia Emissão"] = r[c0 - 1] if c0 - 1 < len(r) else ""
            base["UG Executora"] = ug
            for j in cols:
                if j < len(r) and r[j].strip():
                    g = dict(base)
                    g.update({"PTRES": L[h + k_ptres][j], "Fonte Recursos": L[h + k_fonte][j], "UG Responsável": L[h + k_ugr][j],
                              "valor": v(r[j])})
                    out.append(g)
        return out
    col_item = idx.get(item)
    if col_item is None:  # cabeçalho em várias linhas: procurar o código do item nas linhas seguintes
        for k in range(1, 6):
            if h + k < len(L) and item in L[h + k]:
                col_item = L[h + k].index(item)
                break
    if col_item is None:
        raise ValueError("coluna do item %s não encontrada" % item)
    if "Item Informação" in idx:  # crédito por célula da DF: a «UG Responsável» vem numa linha de cabeçalho abaixo
        for k in range(1, 4):
            for j, c in enumerate(L[h + k] if h + k < len(L) else []):
                if c == "UG Responsável" and c not in idx and j < col_item:
                    idx[c] = j
    out = []
    for r in L[h + 1:]:
        ug = _ug(r[idx["UG Executora"]]) if "UG Executora" in idx and idx["UG Executora"] < len(r) else None
        if not ug or col_item >= len(r):
            continue
        g = {k: (r[j] if j < len(r) else "") for k, j in idx.items()}
        g["UG Executora"], g["valor"] = ug, v(r[col_item])
        out.append(g)
    return out


def calcular(b_regua, b_credito, b_mov, ref):
    """-> dict no formato de dados/encerramento/regua.json (por_omds com por_ug e total)."""
    reg = regua_por_ug(b_regua)
    # recolhimentos e anulações no ano (item 15 negativo em operação de anulação/devolução)
    rec = collections.defaultdict(float)
    ncs_rec, v_rec = set(), 0.0
    for g in _tabela_nc(b_mov, "15"):
        if g["valor"] < -0.004 and re.search("ANULACAO|DEVOLUCAO", g.get("NC - Operação (Tipo)", "").upper()):
            ncs_rec.add((g["UG Executora"], g.get("NC", "")))
            v_rec += -g["valor"]
            for mnc in set(re.findall(r"(?:2026)?NC\s?(\d{6})", g.get("NC - Descrição", "").upper())):
                if "NC" + mnc != g.get("NC", "")[-8:]:
                    rec[(g["UG Executora"], "NC" + mnc)] += -g["valor"]
    # células de crédito em tela (item 19)
    cel = collections.defaultdict(lambda: {"S": 0.0, "nc": collections.defaultdict(float), "meta": {}})
    for g in _tabela_nc(b_credito, "19"):
        k = (g["UG Executora"], g.get("Ação Governo", ""), g.get("PI", ""), g.get("Natureza Despesa", ""),
             g.get("PTRES", ""), g.get("Fonte Recursos", ""), g.get("UG Responsável", ""))
        cel[k]["S"] += g["valor"]
        nc = g.get("NC", "").strip()
        if nc not in ("-9", "") and nc[:6] != g["UG Executora"]:
            cel[k]["nc"][nc] += g["valor"]
            try:
                d = dt.datetime.strptime(g.get("NC - Dia Emissão", ""), "%d/%m/%Y").date()
            except ValueError:
                d = None
            cel[k]["meta"][nc] = (d, prazo(g.get("NC - Descrição", ""), d) if d else None)
    # formato documento: o crédito por célula não traz NC; ligar as NC recebidas às células pelo endereço
    doc = _eh_documento(linhas(b_mov))
    if doc and not any(cc["nc"] for cc in cel.values()):
        ender = collections.defaultdict(lambda: collections.defaultdict(float))
        meta = {}
        for g in _tabela_nc(b_mov, "15"):
            if g["valor"] <= 0.004 or g.get("Emitente - UG", "")[:6] == g["UG Executora"]:
                continue  # anulação entra pelo «rec» (NC citada na descrição); NC da própria UG não conta
            e = (g["UG Executora"], g.get("PI", ""), g.get("Natureza Despesa", "")[:4], g.get("UG Responsável", ""))
            nc = g.get("NC", "").strip()
            ender[e][nc] += g["valor"]
            try:
                d = dt.datetime.strptime(g.get("NC - Dia Emissão", ""), "%d/%m/%Y").date()
            except ValueError:
                d = None
            meta[nc] = (d, prazo(g.get("NC - Descrição", ""), d) if d else None)
        for k, cc in cel.items():
            for nc, a in ender.get((k[0], k[2], k[3][:4], k[6]), {}).items():
                cc["nc"][nc] += a
                cc["meta"][nc] = meta[nc]
    por_ug = collections.defaultdict(lambda: [0.0, 0.0, 0.0])  # tela, piso, teto
    for k, cc in cel.items():
        S = round(cc["S"], 2)
        if S <= 0.004:
            continue
        ncs = [(a - rec.get((k[0], n[-8:]), 0.0),) + cc["meta"][n] for n, a in cc["nc"].items()]
        ncs = [t for t in ncs if t[0] > 0.004]
        sv = sum(t[0] for t in ncs if t[2] and t[2] < ref)
        snv = sum(t[0] for t in ncs if not (t[2] and t[2] < ref))
        u = por_ug[k[0]]
        u[0] += S
        u[1] += min(sv, max(0.0, S - snv))
        u[2] += min(S, sv)
    out = {}
    tot = collections.Counter()
    for ug in sorted(reg):
        o = OM[ug[3:]]
        x = linha_regua(reg[ug])
        p = por_ug.get(ug, [0.0, 0.0, 0.0])
        x["vencido_piso"], x["vencido_teto"] = round(p[1], 2), round(p[2], 2)
        x["celulas_em_tela"] = round(p[0], 2)
        # trava: a soma das células (crédito por NC) tem de fechar com o crédito disponível da régua, UG a UG
        if abs(x["celulas_em_tela"] - x["em_tela"]) > max(1.0, 0.001 * abs(x["em_tela"])):
            raise ValueError("UG %s: células (%.2f) não fecham com a régua (%.2f)" % (ug, x["celulas_em_tela"], x["em_tela"]))
        out.setdefault(o, {"por_ug": {}})["por_ug"][ug] = x
    for o in ORDEM:
        if o not in out:
            continue
        r = out[o]
        soma = collections.Counter()
        for x in r["por_ug"].values():
            soma.update({k: x[k] for k in ("provisao", "empenhado", "liquidado", "a_liquidar", "em_tela", "rpnp_a_liquidar",
                                           "rpnp_bloqueado", "vencido_piso", "vencido_teto")})
        r.update({k: round(val, 2) for k, val in soma.items()})
        r["pct_empenhado"] = round(100 * r["empenhado"] / r["provisao"], 2) if r["provisao"] else 0.0
        r["pct_liquidado"] = round(100 * r["liquidado"] / r["provisao"], 2) if r["provisao"] else 0.0
        r["semaforo"] = "VERMELHO" if r["vencido_piso"] >= 1e5 else "AMARELO" if r["vencido_piso"] >= 1e4 else "VERDE"
        tot.update({k: r[k] for k in soma})
    total = {k: round(val, 2) for k, val in tot.items()}
    total["pct_empenhado"] = round(100 * total["empenhado"] / total["provisao"], 2) if total.get("provisao") else 0.0
    total["pct_liquidado"] = round(100 * total["liquidado"] / total["provisao"], 2) if total.get("provisao") else 0.0
    r = {"por_omds": {o: out[o] for o in ORDEM if o in out}, "total": total,
         "recolhido_no_ano": {"ncs": len(ncs_rec), "valor": round(v_rec, 2)}}
    if doc:
        r["_formato"] = "documento"  # só em memória: main() troca o texto da fonte e retira a marca
    return r


# ---------------------------------------------------------------- passo da montagem (nuvem)
CHAVES = ("regua_por_ug", "credito_por_nc", "credito_movimento")
RE_ARQ = re.compile(r"^(\d{4}-\d{2}-\d{2})_(regua_por_ug|credito_por_nc|credito_movimento)\.(csv|zip)$")


def escolher_trio(nomes):
    """Data de entrega (AAAA-MM-DD) do trio completo mais recente, ou None."""
    por = {}
    for n in nomes:
        m = RE_ARQ.match(n)
        if m:
            por.setdefault(m.group(1), set()).add(m.group(2))
    ok = sorted(d for d, k in por.items() if k == set(CHAVES))
    return ok[-1] if ok else None


def main(argv=None):
    import argparse
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gof_google
    import gof_ponte_tg as pt

    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="../dados/encerramento/regua.json")
    o = ap.parse_args(argv)
    saida = Path(o.saida)
    ant = json.loads(saida.read_text(encoding="utf-8")) if saida.exists() else {}
    try:
        tok = gof_google.token()
        arqs = pt.listar_pasta(tok)
        entrega = escolher_trio(arqs)
        if not entrega:
            print("REGUA: nenhum trio completo na pasta; régua vigente (%s) mantida" % ant.get("data_dado"))
            return 2
        data_dado = pt.dia_util_anterior(dt.date.fromisoformat(entrega)).isoformat()
        if data_dado <= (ant.get("data_dado") or "") and "assinaturas" in (ant.get("atualizacao") or ""):
            print("REGUA: trio de %s (dados até %s) não é mais novo que o vigente; nada a fazer" % (entrega, data_dado))
            return 0
        b = {}
        for k in CHAVES:
            nome = next(n for n in arqs if RE_ARQ.match(n) and n.startswith("%s_%s." % (entrega, k)))
            bruto = pt._get("https://www.googleapis.com/drive/v3/files/%s?alt=media" % arqs[nome], tok)
            if nome.endswith(".zip"):  # o CSV cruzado vem compactado (assinatura com «Compactar conteúdo»)
                import zipfile
                z = zipfile.ZipFile(io.BytesIO(bruto))
                bruto = z.read(z.namelist()[0])
            b[k] = bruto
        r = calcular(b["regua_por_ug"], b["credito_por_nc"], b["credito_movimento"], dt.date.fromisoformat(entrega))
    except (OSError, ValueError, RuntimeError, KeyError, StopIteration) as e:
        print("REGUA: falhou (%s: %s); régua vigente (%s) mantida" % (type(e).__name__, e, ant.get("data_dado")))
        return 2
    d = dt.date.fromisoformat(data_dado)
    documento = r.pop("_formato", None) == "documento"
    r.update({"data_dado": data_dado,
              "posicao_siafi": "TG, assinaturas entregues em %s (dados até %s)" % (entrega[8:] + "/" + entrega[5:7], d.strftime("%d/%m")),
              "fonte": ("TG, assinaturas «Execução Crédito e RPNP por UG», «Crédito e empenho por UG, PI, ND e UGR» e «NC recebidas "
                        "documento», pela ponte; NC ligadas às células pelo endereço (UG, PI, grupo da ND, UGR)" if documento else
                        "TG, assinaturas «Execução Crédito e RPNP por UG», «Crédito por NC» e «Crédito por NC movimento 2026», pela ponte P-041"),
              "regra_vencido": "vencido = saldo da célula coberto por NC de outra UG com prazo escrito anterior a %s; NC de «empenho imediato» "
                               "conta como vencida; piso e teto porque o TG não dá saldo por NC; ajuste de ND da própria UG não é rastreado "
                               "à NC de origem (piso conservador)" % (entrega[8:] + "/" + entrega[5:7]),
              "atualizacao": "diária (assinaturas do TG, ponte P-041)"})
    if ant.get("referencia_1rm"):
        r["referencia_1rm"] = ant["referencia_1rm"]
    saida.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("REGUA: dados até %s — em tela R$ %.2f, vencido (piso) R$ %.2f, RPNP R$ %.2f"
          % (data_dado, r["total"]["em_tela"], r["total"]["vencido_piso"], r["total"]["rpnp_a_liquidar"]))
    return 0


if __name__ == "__main__":
    import sys as _s
    _s.exit(main())
