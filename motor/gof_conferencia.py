# -*- coding: utf-8 -*-
"""
gof_conferencia.py (v1, 07nov2026; derivado de gcalc_conferencia.py v1 de 04nov2026) — CONFRONTO SEMANAL NO RUNNER (D19 parte 1)
=================================================================================================================
Versao SO LEITURA para o GitHub Actions (PLANO v2.4, D19): le a planilha pela conta de servico so de leitura (gof_google),
confronta com PNCP e Compras.gov e grava relatorio e JSON em dados/conferencia/<data>/ + ultimo.json. NUNCA grava na
planilha: --aplicar e recusado aqui (a gravacao continua como sessao do Claude, D19 parte 2).

Fontes: PNCP (compra e atas), Compras.gov dados abertos (contratacoes das 6 UASGs, para achar
relancamento; contratos por unidade gestora, para achar execucao), e a propria planilha.
NAO cobre (sem API publica): IRP Digital, sessao publica/chat, recurso, parecer da CJU, empenho fora de contrato.

MODOS
  python gcalc_conferencia.py                 # SO RELATORIO (padrao): nao grava nada
  python gcalc_conferencia.py --aplicar       # grava SO o que o portal prova (ver abaixo), com guardas e registro de antes/depois
  python gcalc_conferencia.py --saida PASTA   # onde gravar relatorio, estado e registro (padrao: ./saida_conferencia)
  python gcalc_conferencia.py --teste-alterar Z6=Pendente,AB6=Pendente   # altera VALORES EM MEMORIA para testar a deteccao (recusa --aplicar)

O QUE --aplicar PODE GRAVAR (decisao do coordenador de 04/11/2026: «relatorio e gravar o provado»)
  Controle Processos: Z (Aceito/Habilitado), AB (Homologado), AC (Assinada) — so Pendente -> provado, NUNCA rebaixa;
                      AD (valor homologado) — igual ao PNCP, nos dois sentidos, em numero;
                      AZ (Situacao PNCP) e AY (ultima atualizacao) — so pelo dono, via Composio, se COMPOSIO_API_KEY existir;
  aba Atas: recarga pelo gcalc_atas_sync (dado derivado) quando as atas do PNCP diferem das da planilha.
  FICA SO NO RELATORIO (decisao do coordenador): numero do pregao (B), valor estimado (H), datas X e Y, IRP, metas,
  observacoes, relancamento, linha nova, regressao (PNCP menos adiantado que a planilha).
GUARDAS: PNCP indisponivel numa linha = linha ignorada; menos de 80% das linhas lidas = aborta; mais de 30 celulas
  a gravar = aborta; valores monetarios gravados como NUMERO (ACH-010); leitura de volta apos gravar.
Saidas: conferencia_AAAAMMDD_HHMM.md/.json, aplicado_AAAAMMDD_HHMM.json (de/para), estado_conferencia.json.
Codigo de saida: 0 sem pendencia; 2 ha divergencia ou evento a decidir (para o agendador avisar).
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
import gof_google  # noqa: E402
import requests


def get_google_access_token(_conta=None):
    """Token da conta de servico SO DE LEITURA (D14); a assinatura imita a do workspace para o resto do codigo nao mudar."""
    return gof_google.token()


SP = "1XTWMvf47PyWEi5eFg1wk16uOTse8s-wLvSV69pjVQd0"
API = "https://sheets.googleapis.com/v4/spreadsheets/" + SP
ACC_SA = "sa"
ACC_DONO = "7aa3cd63-2e78-41ad-81be-57dd59abce59"
CNPJ = "00394452000103"
UASGS = {
    "160238": "BaApLog",
    "160329": "BCMS",
    "160304": "BMSA",
    "160321": "ECT",
    "160246": "DCMun",
    "160307": "1oDSup",
}
EPOCH = dt.date(1899, 12, 30)
MAX_CELULAS = 30
SITUACAO_AZ = {"Divulgada no PNCP": "Ativo", "Suspensa": "Suspenso", "Anulada": "Anulado", "Revogada": "Revogado"}
RE_LINK = re.compile(r"editais/(\d{14})/(\d{4})/0*(\d+)")
UA = {"Accept": "application/json", "User-Agent": "gcalc-conferencia/1.0"}


def http(url, tent=5):
    """GET JSON com recuo em 429. Devolve (status, json)."""
    for i in range(tent):
        time.sleep(1.2)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                b = r.read()
                return r.status, (json.loads(b) if b else {})
        except urllib.error.HTTPError as e:
            if e.code in (204, 404):
                return e.code, {}
            if e.code == 429:
                time.sleep(25 * (i + 1))
                continue
            if i == tent - 1:
                return e.code, {"_erro": "HTTP %s" % e.code}
        except (OSError, ValueError) as e:  # rede (urllib herda de OSError) e JSON
            if i == tent - 1:
                return 0, {"_erro": str(e)[:80]}
            time.sleep(3 * (i + 1))
    return 0, {"_erro": "falha"}


def col(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def ci(c):
    n = 0
    for ch in c:
        n = n * 26 + ord(ch) - 64
    return n - 1


def d_serial(x):
    return (EPOCH + dt.timedelta(days=int(x))) if isinstance(x, (int, float)) else None


def iso_serial(s):
    return (dt.date.fromisoformat(s[:10]) - EPOCH).days if s else None


def so_digitos(s):
    return re.sub(r"\D", "", str(s or ""))


# ------------------------------------------------------------------ leitura da planilha
def ler_planilha(h):
    r = requests.get(
        API + "/values:batchGet",
        headers=h,
        timeout=90,
        params=[
            ("valueRenderOption", "UNFORMATTED_VALUE"),
            ("ranges", "'Controle Processos'!A3:AZ16"),
            ("ranges", "Atas!A1:I400"),
        ],
    )
    r.raise_for_status()
    v = r.json()["valueRanges"]
    return v[0].get("values", []), v[1].get("values", [])


def celula(cp, a1):
    m = re.match(r"([A-Z]+)(\d+)", a1)
    c, r = ci(m.group(1)), int(m.group(2)) - 3
    return cp[r][c] if r < len(cp) and c < len(cp[r]) else ""


# ------------------------------------------------------------------ coleta nos portais
def pncp_compra(cnpj, ano, seq):
    s, det = http("https://pncp.gov.br/api/consulta/v1/orgaos/%s/compras/%s/%s" % (cnpj, ano, seq))
    atas, pg = [], 1
    while "_erro" not in det and s == 200:
        s2, d = http(
            "https://pncp.gov.br/api/pncp/v1/orgaos/%s/compras/%s/%s/atas?pagina=%d&tamanhoPagina=100"
            % (cnpj, ano, seq, pg)
        )
        if "_erro" in d:
            return {"_erro": d["_erro"]}
        lista = d.get("data", []) if isinstance(d, dict) else []
        atas += lista
        if len(lista) < 100 or pg > 5:
            break
        pg += 1
    if "_erro" in det or s != 200:
        return {"_erro": det.get("_erro", "HTTP %s" % s)}
    return {"detalhe": det, "atas": atas}


def compras_gov_contratacoes(hoje):
    """Todas as contratacoes (pregao) das 6 UASGs desde 01/09/2025, inclusive excluidas: serve para achar relancamento."""
    base = "https://dadosabertos.compras.gov.br/modulo-contratacoes/1_consultarContratacoes_PNCP_14133"
    out = {}
    janelas = [("2025-09-01", "2025-12-31"), ("2026-01-01", "2026-06-30"), ("2026-07-01", hoje.isoformat())]
    for u in UASGS:
        todos = []
        for excl in ("false", "true"):
            for a, b in janelas:
                p = 1
                while p < 30:
                    s, d = http(
                        "%s?unidadeOrgaoCodigoUnidade=%s&dataPublicacaoPncpInicial=%s&dataPublicacaoPncpFinal=%s&codigoModalidade=5&contratacaoExcluida=%s&pagina=%d&tamanhoPagina=100"
                        % (base, u, a, b, excl, p)
                    )
                    if "_erro" in d:
                        todos.append({"_erro": d["_erro"], "uasg": u})
                        break
                    todos += d.get("resultado") or []
                    if p >= (d.get("totalPaginas") or 1):
                        break
                    p += 1
        out[u] = todos
    return out


def compras_gov_contratos(hoje):
    base = "https://dadosabertos.compras.gov.br/modulo-contratos/1_consultarContratos"
    out = {}
    for u in UASGS:
        lst, p = [], 1
        while p < 30:
            s, d = http(
                "%s?codigoOrgao=52121&codigoUnidadeGestora=%s&dataVigenciaInicialMin=2025-11-01&dataVigenciaInicialMax=2028-12-31&pagina=%d&tamanhoPagina=100"
                % (base, u, p)
            )
            if "_erro" in d:
                lst.append({"_erro": d["_erro"], "uasg": u})
                break
            lst += d.get("resultado") or []
            if p >= (d.get("totalPaginas") or 1):
                break
            p += 1
        out[u] = lst
    return out


# ------------------------------------------------------------------ analise
def analisar(cp, atas_sheet, fatos, cg_contrat, cg_contr, estado_ant):
    prov, via_dono, rel, eventos = [], [], [], []
    controles_nossos = {}
    for r in range(4, 16):
        no = celula(cp, "B%d" % r)
        if not no:
            continue
        f = fatos.get(r)
        link = str(celula(cp, "AE%d" % r)).strip()
        uasg = str(celula(cp, "E%d" % r))
        if not f:
            if link:
                rel.append((r, no, "SEM LEITURA", "PNCP indisponivel ou link ilegivel; linha ignorada nesta rodada"))
            continue
        det, atas = f["detalhe"], f["atas"]
        controles_nossos[det.get("numeroControlePNCP")] = (r, no)
        hom = det.get("valorTotalHomologado") or 0
        # --- gravaveis (provado pelo portal; nunca rebaixa)
        z, ab, ac, ad = (celula(cp, "%s%d" % (c, r)) for c in ("Z", "AB", "AC", "AD"))
        if hom > 0 and z == "Pendente":
            prov.append(("Z%d" % r, z, "Aceito/Habilitado", "PNCP: homologado em R$ %.2f" % hom, no))
        if hom > 0 and ab == "Pendente":
            prov.append(("AB%d" % r, ab, "Homologado", "PNCP: valorTotalHomologado R$ %.2f" % hom, no))
        if atas and ac == "Pendente":
            prov.append(("AC%d" % r, ac, "Assinada", "PNCP: %d ata(s)" % len(atas), no))
        if hom > 0 and (not isinstance(ad, (int, float)) or abs(ad - hom) > 0.005):
            prov.append(("AD%d" % r, ad, round(hom, 2), "PNCP valorTotalHomologado", no))
        # regressao: planilha mais adiantada que o portal
        if hom == 0 and (ab == "Homologado" or isinstance(ad, (int, float)) and ad > 0):
            rel.append((r, no, "REGRESSAO", "planilha diz homologado/valor, mas o PNCP nao traz valor homologado"))
        if not atas and ac == "Assinada":
            rel.append((r, no, "REGRESSAO", "planilha diz ata assinada, mas o PNCP nao traz ata"))
        # --- via dono (AZ, AY)
        sit = det.get("situacaoCompraNome", "")
        az_esp = SITUACAO_AZ.get(sit)
        az = celula(cp, "AZ%d" % r)
        if az_esp is None:
            rel.append((r, no, "SITUACAO NOVA", "situacao PNCP desconhecida: %r (AZ nao mapeia)" % sit))
        elif az != az_esp:
            via_dono.append(("AZ%d" % r, az, az_esp, "PNCP: %s" % sit, no))
        # --- so relatorio
        num_esp = "PE %s/%s" % (det.get("numeroCompra"), det.get("anoCompra"))
        if no != num_esp and not str(no).startswith("INT-"):
            rel.append(
                (
                    r,
                    no,
                    "NUMERO DO PREGAO",
                    "planilha %r, PNCP %r (renumeracao ou relancamento: decisao do coordenador)" % (no, num_esp),
                )
            )
        est, h = det.get("valorTotalEstimado"), celula(cp, "H%d" % r)
        if est and (not isinstance(h, (int, float)) or abs(h - est) > 0.005):
            rel.append((r, no, "VALOR ESTIMADO", "planilha %s, PNCP %.2f" % (h, est)))
        for c, campo in (("X", "dataPublicacaoPncp"), ("Y", "dataEncerramentoProposta")):
            pv, sv = iso_serial(det.get(campo)), celula(cp, "%s%d" % (c, r))
            if pv and sv != pv:
                rel.append((r, no, "DATA " + c, "planilha %s, PNCP %s" % (d_serial(sv), d_serial(pv))))
        # --- relancamento: outra contratacao da mesma UASG com o mesmo processo
        proc = so_digitos(det.get("processo"))
        aj = str(celula(cp, "AJ%d" % r))
        for c in cg_contrat.get(uasg, []):
            if c.get("_erro") or so_digitos(c.get("processoCompra") or c.get("processo")) != proc or not proc:
                continue
            seq_c = c.get("sequencialCompraPncp")
            if seq_c and int(seq_c) != int(det.get("sequencialCompra")):
                ident = "PE %s/%s" % (c.get("numeroCompra"), c.get("anoCompraPncp"))
                if ident not in aj and ident != no:
                    rel.append(
                        (
                            r,
                            no,
                            "RELANCAMENTO?",
                            "mesmo processo na UASG %s: %s (seq. %s), situacao %s. Nao consta nas observacoes da linha"
                            % (uasg, ident, seq_c, c.get("situacaoCompraNomePncp")),
                        )
                    )
        # --- evento desde a ultima rodada (mudanca no portal)
        chave = "%s/%s" % (det.get("anoCompra"), det.get("sequencialCompra"))
        ant = estado_ant.get(chave)
        atual = {"atualizacao": det.get("dataAtualizacao"), "situacao": sit, "atas": len(atas), "homologado": hom}
        if ant and ant != atual:
            mud = [k for k in atual if atual[k] != ant.get(k)]
            eventos.append(
                (r, no, "MUDANCA NO PORTAL", ", ".join("%s: %s -> %s" % (k, ant.get(k), atual[k]) for k in mud))
            )
        f["_estado"] = (chave, atual)
    # --- atas: PNCP x aba Atas
    esperadas = {}
    for r, f in fatos.items():
        no = celula(cp, "B%d" % r)
        for a in f["atas"]:
            esperadas[(no, "%s/%s" % (a["numeroAtaRegistroPreco"], a["anoAta"]))] = a
    na_planilha = {}
    for ln in atas_sheet[1:]:
        if ln and ln[0]:
            na_planilha[(ln[0], ln[1])] = ln
    atas_dif = []
    for k, a in esperadas.items():
        ln = na_planilha.get(k)
        if not ln:
            atas_dif.append("falta %s %s" % k)
            continue
        if (
            iso_serial(a.get("dataVigenciaFim")) != ln[5]
            or iso_serial(a.get("dataAssinatura")) != ln[3]
            or ("SIM" if a.get("cancelado") else "NAO") != ln[6]
        ):
            atas_dif.append("difere %s %s" % k)
    for k in na_planilha:
        if k not in esperadas and k[0] in {celula(cp, "B%d" % r) for r in fatos}:
            atas_dif.append("sobra %s %s" % k)
    # --- contratos ligados as compras do GCALC
    ligados = []
    for u, lst in cg_contr.items():
        for c in lst:
            if c.get("_erro"):
                continue
            if c.get("numeroControlePncpCompra") in controles_nossos:
                ligados.append(
                    (
                        u,
                        c.get("numeroContrato"),
                        controles_nossos[c.get("numeroControlePncpCompra")][1],
                        c.get("valorGlobal"),
                    )
                )
    return prov, via_dono, rel, eventos, atas_dif, len(esperadas), ligados


# ------------------------------------------------------------------ gravacao
# gravar(): REMOVIDA nesta versao (D19 parte 1): o runner nunca escreve na planilha.

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--saida", default="saida_conferencia")
    ap.add_argument("--teste-alterar", default="")
    ap.add_argument(
        "--execucao",
        action="store_true",
        help="acrescenta a secao Execucao da despesa (Portal da Transparencia + ficha ao vivo); so leitura",
    )
    ap.add_argument("--execucao-desde", default="2026-04-01", help="inicio da janela de empenhos (AAAA-MM-DD)")
    ap.add_argument(
        "--execucao-ugs-ampliadas", action="store_true", help="coleta tambem as UG participantes/adesoes (mais lento)"
    )
    o = ap.parse_args()
    if o.aplicar:
        print("RECUSADO: esta versao roda no runner com conta so de leitura (D14/D19); a gravacao e sessao do Claude")
        return 1
    if o.teste_alterar and o.aplicar:
        print("RECUSADO: --teste-alterar altera valores em memoria e nao pode ser combinado com --aplicar")
        return 1
    hoje = dt.date.today()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    os.makedirs(o.saida, exist_ok=True)
    h = {"Authorization": "Bearer " + get_google_access_token(ACC_SA), "Content-Type": "application/json"}
    cp, atas_sheet = ler_planilha(h)
    for par in filter(None, o.teste_alterar.split(",")):
        a1, val = par.split("=", 1)
        m = re.match(r"([A-Z]+)(\d+)", a1)
        r_, c_ = int(m.group(2)) - 3, ci(m.group(1))
        while len(cp[r_]) <= c_:
            cp[r_].append("")
        cp[r_][c_] = float(val) if re.fullmatch(r"-?\d+(\.\d+)?", val) else val
    # PNCP por linha
    fatos, falhas, publicados = {}, 0, 0
    for r in range(4, 16):
        m = RE_LINK.search(str(celula(cp, "AE%d" % r)))
        if not m:
            continue
        publicados += 1
        f = pncp_compra(m.group(1), m.group(2), m.group(3))
        if "_erro" in f:
            falhas += 1
            print("linha %d: PNCP indisponivel (%s)" % (r, f["_erro"]))
            continue
        fatos[r] = f
    if publicados and len(fatos) < 0.8 * publicados:
        print("ABORTADO: PNCP respondeu em %d de %d linhas (menos de 80%%)" % (len(fatos), publicados))
        return 1
    cg_contrat, cg_contr = compras_gov_contratacoes(hoje), compras_gov_contratos(hoje)
    ep = Path(o.saida) / "estado_conferencia.json"
    estado_ant = json.load(open(ep, encoding="utf-8")) if ep.exists() else {}
    prov, via_dono, rel, eventos, atas_dif, n_atas, ligados = analisar(
        cp, atas_sheet, fatos, cg_contrat, cg_contr, estado_ant
    )
    pendencia = bool(rel or eventos)
    # --- relatorio
    L = [
        "# Conferencia da planilha GCALC contra os portais — %s" % stamp,
        "",
        "Modo: **%s**. Linhas publicadas lidas no PNCP: %d de %d. Atas no PNCP: %d; atas na planilha (dos mesmos processos): %d."
        % (
            "APLICAR" if o.aplicar else "so relatorio",
            len(fatos),
            publicados,
            n_atas,
            sum(1 for lin in atas_sheet[1:] if lin and lin[0]),
        ),
        "",
    ]

    def bloco(tit, linhas, cab):
        L.append("## %s (%d)" % (tit, len(linhas)))
        if not linhas:
            L.append("nenhum\n")
            return
        L.append(cab)
        L.append("|" + "---|" * (cab.count("|") - 1))
        for x in linhas:
            L.append(x)
        L.append("")

    bloco(
        "O portal prova e a planilha esta atras (gravaveis)",
        ["| %s | %s | %s | %s | %s |" % (c, no, de, novo, m) for c, de, novo, m, no in prov],
        "| Celula | Pregao | Atual | Novo | Prova |",
    )
    bloco(
        "Situacao PNCP e data de conferencia (so o dono grava)",
        ["| %s | %s | %s | %s |" % (c, no, de, novo) for c, de, novo, m, no in via_dono],
        "| Celula | Pregao | Atual | Novo |",
    )
    bloco(
        "Divergencias que dependem de decisao (so relatorio)",
        ["| %d | %s | %s | %s |" % (r, no, t, m) for r, no, t, m in rel],
        "| Linha | Pregao | Tipo | Detalhe |",
    )
    bloco(
        "Mudancas no portal desde a ultima conferencia",
        ["| %d | %s | %s |" % (r, no, m) for r, no, t, m in eventos],
        "| Linha | Pregao | O que mudou |",
    )
    L.append(
        "## Aba Atas: %s"
        % ("; ".join(atas_dif[:12]) + (" ..." if len(atas_dif) > 12 else "") if atas_dif else "confere com o PNCP")
    )
    L.append("")
    L.append("## Contratos no Compras.gov ligados a compras do GCALC: %d" % len(ligados))
    for u, n, no, v in ligados:
        L.append("- UG %s, contrato %s, compra %s, valor global %s" % (u, n, no, v))
    L.append("")
    exec_dados = None
    if o.execucao:
        try:
            import gcalc_execucao

            sec, exec_dados = gcalc_execucao.secao(
                sys.modules[__name__],
                cp,
                fatos,
                hoje,
                dt.date.fromisoformat(o.execucao_desde),
                o.execucao_ugs_ampliadas,
            )
        except (ImportError, OSError, RuntimeError, ValueError, KeyError, TypeError) as e:  # nunca derruba a conferencia
            sec, exec_dados = (
                [
                    "## Execucao da despesa dos pregoes",
                    "Secao indisponivel nesta rodada: %s: %s" % (type(e).__name__, str(e)[:160]),
                    "",
                ],
                {"ok": False},
            )
        L.extend(sec)
    L.append(
        "_Fora do alcance das APIs publicas: IRP Digital, sessao e chat, recursos, parecer da CJU, empenho fora de contrato._"
    )
    rel_txt = "\n".join(L)
    open(os.path.join(o.saida, "conferencia_%s.md" % stamp), "w", encoding="utf-8").write(rel_txt)
    json.dump(
        {
            "prov": prov,
            "via_dono": via_dono,
            "rel": rel,
            "eventos": eventos,
            "atas_dif": atas_dif,
            "ligados": ligados,
            "execucao": exec_dados,
        },
        open(os.path.join(o.saida, "conferencia_%s.json" % stamp), "w", encoding="utf-8"),
        ensure_ascii=False,
        default=str,
        indent=1,
    )
    resumo = {
        "data": hoje.isoformat(),
        "stamp": stamp,
        "linhas_lidas_pncp": len(fatos),
        "publicados": publicados,
        "gravaveis": len(prov),
        "so_dono": len(via_dono),
        "divergencias": len(rel),
        "eventos": len(eventos),
        "atas_diferentes": len(atas_dif),
        "contratos_ligados": len(ligados),
        "pendencia": pendencia,
        "itens": [{"linha": r, "pregao": no, "tipo": t, "detalhe": m} for r, no, t, m in rel]
        + [{"linha": r, "pregao": no, "tipo": "evento", "detalhe": m} for r, no, t, m in eventos]
        + [
            {"celula": c, "pregao": no, "tipo": "gravavel", "detalhe": "%s -> %s (%s)" % (de, novo, m)}
            for c, de, novo, m, no in prov
        ],
    }
    json.dump(
        resumo,
        open(os.path.join(o.saida, "ultimo.json"), "w", encoding="utf-8"),
        ensure_ascii=False,
        default=str,
        indent=1,
    )
    novo_estado = {f["_estado"][0]: f["_estado"][1] for f in fatos.values() if "_estado" in f}
    if not o.teste_alterar:
        json.dump(novo_estado, open(ep, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(rel_txt)
    return 2 if pendencia else 0


if __name__ == "__main__":
    sys.exit(main())
