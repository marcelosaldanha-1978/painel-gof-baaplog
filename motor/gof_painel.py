# -*- coding: utf-8 -*-
"""
gof_painel.py (v0.3, 07nov2026; v0.2 e v0.1 de 07nov2026) — motor do painel GOF-BaApLog, FASE A (PLANO v2.4; D11, LOG-132).

Python deterministico: le as fontes, calcula os blocos e grava um `dados.json` e um `index.html` unico, com os dados
embutidos, sem pedido externo. O navegador so desenha e calcula a idade do dado (frescor); nenhum numero nasce no navegador.

Blocos da fase A:
  B1  Execucao por OMDS (TG, conta 522920101, 2026): empenhado por OMDS, UG 160 e 167 separadas, ritmo mensal.
      SEM percentual sobre o credito (depende da P-034). O marco de empenho de OUT (100%) venceu em 31/10/2026.
  B3  Carteira de licitacoes (planilha GCALC, aba Controle Processos; KPI do Painel transportado, nunca recalculado).
  B4  Acao imediata: atas a vencer (<= 90 dias, PNCP), processos atrasados ou suspensos, NE a verificar
      (vinculo v1.2: CITADO_SEM_ATA, ALERTA, AMBIGUO) e pendencias do coordenador.
Fora da fase A: percentual do B1 e o B2 (capacidade x uso), que dependem da P-034, do denominador e das fichas (P-038).

v0.2: roda na nuvem (GitHub Actions, workflow gof-painel.yml) a partir do EXTRATO SEM PESSOA da execucao
(`--extrato`: NE, UG, data, valor, modalidade e o resultado do vinculo; sem favorecido nem texto da NE), gerado onde o CSV
do TG estiver (hoje, a pasta do projeto; no alvo, a ponte da subscricao) por `gerar_extrato()`. O CSV com pessoa nunca
vai ao repositorio (D6).

v0.4 (09nov2026, LOG-181; P-063 e P-064): o B1 soma o EMPENHADO LIQUIDO (contas 6229201xx = item 23 do TG), lido do extrato
versao 2 (`gof_extrato_tg.py`); a emissao bruta (522920101) fica como apoio, com rotulo proprio, e as NE anuladas por
inteiro saem da contagem. Vinculo NE -> pregao pela chave SIASG (regra 2.0, `vinculo_siasg.py`); a regra 1.2 (texto +
favorecido) so vale para o extrato do Portal (reserva) e como conferencia. Extrato versao 1 e CSV do R1 continuam lidos,
com a base declarada («emissao bruta») no rotulo do B1.

v0.3 (PLANO v2.4, LOG-141): repositorio proprio `painel-gof-baaplog` (D8). Faixa com a fonte do B1 e a idade em DIAS UTEIS
(D17 revista: ate 2 dias uteis = fresco); `fonte_b1` fica em meta (so "tg" ate o Portal entrar no runner, passo 5).
Pendencias do coordenador com a data da ultima edicao (D20): o JSON e {"editado_em": "AAAA-MM-DD", "itens": [...]};
a lista nua continua aceita (data desconhecida, marcada).

Dado pessoal: nenhum. Contatos da planilha (colunas AF a AI), favorecido e texto da NE NAO entram no dados.json.
Uso:
  python gof_painel.py --execucao "<pasta>/TG_2026-11-06_PILOTO_*/*CSV_completo_ATRIBUTOS_NE_06nov2026.csv" \
      --data-execucao 2026-11-06 --carteira carteira.csv --kpis kpis.json --atas atas.json \
      --fichas pncp_12_processos.json --pendencias pendencias.json --saida painel_saida [--hoje 2026-11-07]
"""
import argparse
import csv
import datetime as dt
import glob
import hashlib
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gcalc_transparencia as tr  # noqa: E402
from vinculo_siasg import VERSAO_REGRA as VERSAO_VINCULO_SIASG  # noqa: E402

VERSAO_MOTOR = "0.4"
DIAS_UTEIS_FRESCO = 2  # D17 revista: ate 2 dias uteis o dado e fresco
DIAS_PENDENCIAS_AMARELO = 14  # D20
OMDS = ["BaApLog", "BCMS", "BMSA", "ECT", "DCMun", "1oDSup"]
ROTULO_OMDS = {"1oDSup": "1º D Sup"}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DIAS_ATA_A_VENCER = 90
NIVEIS_A_VERIFICAR = ("ALERTA", "AMBIGUO", "CITADO_SEM_ATA", "SEM_CHAVE_CITA")
RE_LINK = re.compile(r"editais/(\d{14})/(\d{4})/0*(\d+)")


def sha256(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def _num_br(s):
    """'R$ 1.234,56' -> 1234.56; vazio -> None."""
    t = re.sub(r"[^\d,\-]", "", str(s or ""))
    return float(t.replace(",", ".")) if t else None


def _data_br(s):
    try:
        return dt.datetime.strptime(str(s or "").strip()[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def dias_uteis(desde, ate):
    """Dias uteis (seg a sex) entre duas datas, excluido o dia inicial e incluido o final. Sem feriados (declarado)."""
    if desde is None or ate is None or ate <= desde:
        return 0
    n, d = 0, desde
    while d < ate:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def ler_pendencias(obj):
    """D20: {"editado_em", "editado_por", "itens"} ou lista nua (legado) -> dict normalizado com a data visivel."""
    if isinstance(obj, list):
        return {"editado_em": None, "editado_por": None, "itens": obj}
    return {"editado_em": obj.get("editado_em"), "editado_por": obj.get("editado_por"), "itens": list(obj.get("itens", []))}


# ------------------------------------------------------------------ B1 execucao
BASES_B1 = {
    "liquido": ("Tesouro Gerencial, empenhado LÍQUIDO (contas 6229201xx = item 23 «despesas empenhadas»: emissão + reforço "
                "− anulação), NE emitidas em 2026, UG 160xxx e 167xxx", "Empenhado líquido nas 6 OMDS"),
    "emissao": ("Tesouro Gerencial, conta 522920101 (EMISSÃO BRUTA, sem reforço nem anulação), NE emitidas em 2026, "
                "UG 160xxx e 167xxx", "Emissão bruta nas 6 OMDS (não é o empenhado líquido)"),
    "portal": ("Portal da Transparência (RESERVA): valor da NE no Portal, que mistura emissão e valor atualizado; "
               "não comparável ao líquido do TG", "Valor das NE no Portal (reserva; base mista)"),
}


def bloco_b1(regs, data_dado, base="emissao", vinculos=None):
    """Empenhado por OMDS (UG 160 e 167 separadas) e por mes de emissao. regs = saida de tr.ler_csv_tg ou de ler_extrato.
    base: "liquido" (extrato v2), "emissao" (CSV do R1 ou extrato v1) ou "portal". Na base liquida, NE com valor 0,00
    (anulada por inteiro) nao entra na contagem de NE; o valor emitido vai ao apoio."""
    por = {o: {"omds": o, "rotulo": ROTULO_OMDS.get(o, o), "ug160": None, "ug167": None, "ne160": 0, "valor160": 0.0,
               "ne167": 0, "valor167": 0.0, "por_mes": [0.0] * 12, "ne_anuladas": 0, "emitido": 0.0} for o in OMDS}
    docs = set()
    for r in regs:
        if r["documento"] in docs:
            raise ValueError("NE repetida na entrada (CSV duplicado?): %s" % r["documento"])
        docs.add(r["documento"])
        ug = r["_ug"]
        o = por[tr.UGS[ug]]
        v = tr._num(r["valor"])
        lado = "160" if ug.startswith("160") else "167"
        o["ug" + lado] = ug
        if r.get("_emitido") is not None:
            o["emitido"] += r["_emitido"]
        if base == "liquido" and v == 0.0:
            o["ne_anuladas"] += 1
            continue
        o["ne" + lado] += 1
        o["valor" + lado] += v
        d = tr._data(r.get("data"))
        if d and d.year == 2026:
            o["por_mes"][d.month - 1] += v
    linhas = []
    for o in OMDS:
        x = por[o]
        x["valor160"], x["valor167"] = round(x["valor160"], 2), round(x["valor167"], 2)
        x["total"] = round(x["valor160"] + x["valor167"], 2)
        x["ne"] = x["ne160"] + x["ne167"]
        x["por_mes"] = [round(v, 2) for v in x["por_mes"]]
        x["emitido"] = round(x["emitido"], 2) if base == "liquido" else None
        linhas.append(x)
    fonte, rotulo = BASES_B1[base]
    out = {"fonte": fonte, "base": base, "rotulo_total": rotulo,
           "data_dado": data_dado, "omds": linhas, "total": round(sum(x["total"] for x in linhas), 2),
           "ne": sum(x["ne"] for x in linhas),
           "marco": "O marco de empenho de 100% (OUT) da Tabela 2 venceu em 31/10/2026. O percentual sobre o crédito "
                    "recebido só entra depois da P-034 (conferência do crédito por UG).",
           "lastro": "exato (TG, conferido ao centavo com o item 23)" if base == "liquido" else
                     ("exato (TG), mas é emissão bruta" if base == "emissao" else "reserva com lacunas")}
    if base == "liquido":
        out["apoio"] = {"emissao_bruta": round(sum(x["emitido"] for x in linhas), 2),
                        "ne_emitidas": len(docs), "ne_anuladas": sum(x["ne_anuladas"] for x in linhas),
                        "nota": "Líquido = emissão + reforço − anulação. A emissão bruta não soma os reforços nem desconta "
                                "as anulações (inclusive de NE anuladas e reemitidas). O ritmo mensal usa o mês de emissão da NE."}
    if vinculos is not None:
        g = {}
        for v in vinculos:
            if v.get("nivel") == "SIASG" and tr._num(v["valor"]) != 0.0:
                x = g.setdefault(v["pregao"], {"pregao": v["pregao"], "ne": 0, "valor": 0.0})
                x["ne"] += 1
                x["valor"] += tr._num(v["valor"])
        lista = sorted(({**x, "valor": round(x["valor"], 2)} for x in g.values()), key=lambda x: -x["valor"])
        out["vinculo_gcalc"] = {"regra": "chave SIASG da NE (v%s): UASG + modalidade 05 + número/ano do pregão da carteira"
                                % VERSAO_VINCULO_SIASG, "pregoes": lista, "ne": sum(x["ne"] for x in lista),
                                "valor": round(sum(x["valor"] for x in lista), 2)}
    return out


# ------------------------------------------------------------------ B3 carteira
COLS = {"ordem": 0, "processo": 1, "objeto": 2, "ugg": 3, "uasg": 4, "estimado": 7, "homologado": 29, "link": 30,
        "prazo_meta": 38, "status_prazo": 39, "fase": 40, "etapa": 41, "pct_total": 46, "proxima_acao": 48,
        "ultima_atualizacao": 50, "situacao_pncp": 51}


def ler_carteira(caminho):
    """CSV exportado da aba Controle Processos. So as colunas de COLS (contatos AF-AI e observacoes ficam fora)."""
    linhas = list(csv.reader(open(caminho, encoding="utf-8")))
    cab = next((i for i, ln in enumerate(linhas) if len(ln) > 51 and ln[1].strip().startswith("N")
                and "Processo" in ln[1]), None)
    if cab is None or linhas[cab][51].strip() != "Situação PNCP" or linhas[cab][29].strip() != "Valor Homologado (R$)":
        raise RuntimeError("cabeçalho da aba Controle Processos não reconhecido: a estrutura mudou?")
    out = []
    for ln in linhas[cab + 1:]:
        if not ln or not ln[0].strip().isdigit():
            continue
        p = {k: ln[i].strip() for k, i in COLS.items()}
        p["ordem"] = int(p["ordem"])
        p["estimado"], p["homologado"] = _num_br(p["estimado"]), _num_br(p["homologado"])
        out.append(p)
    return out


def bloco_b3(processos, kpis):
    atrasados = [p for p in processos if p["status_prazo"] == "Atrasado"]
    return {"fonte": "Planilha GCALC, aba Controle Processos; KPI do Painel transportado (não recalculado)",
            "data_dado": max((_data_br(p["ultima_atualizacao"]) or dt.date.min) for p in processos).isoformat(),
            "processos": [{k: p[k] for k in COLS if k != "link"} for p in processos],
            "resumo": {"processos": len(processos), "estimado": round(sum(p["estimado"] or 0 for p in processos), 2),
                       "homologado": round(sum(p["homologado"] or 0 for p in processos), 2),
                       "concluidos": sum(1 for p in processos if p["fase"] == "Concluido"),
                       "atrasados": len(atrasados),
                       "suspensos": sum(1 for p in processos if p["situacao_pncp"] == "Suspenso"),
                       "nao_publicados": sum(1 for p in processos if p["situacao_pncp"] == "Nao publicado")},
            "kpis_painel": kpis}


# ------------------------------------------------------------------ atas (PNCP)
def coletar_atas(processos, buscar=None):
    """Atas de cada processo publicado, direto do PNCP (mesma fonte da aba Atas). Falha de rede ABORTA (nunca parcial)."""
    import requests
    if buscar is None:
        def buscar(cnpj, ano, seq):
            r = requests.get("https://pncp.gov.br/api/pncp/v1/orgaos/%s/compras/%s/%s/atas" % (cnpj, ano, seq),
                             timeout=40, headers={"User-Agent": "GOF-BaApLog painel"})
            if r.status_code in (204, 404):
                return []
            r.raise_for_status()
            return r.json().get("data", []) or []
    atas = []
    for p in processos:
        m = RE_LINK.search(p.get("link") or "")
        if not m:
            continue
        for a in buscar(*m.groups()):
            atas.append({"processo": p["processo"], "ata": "%s/%s" % (a.get("numeroAtaRegistroPreco"), a.get("anoAta")),
                         "assinatura": str(a.get("dataAssinatura") or "")[:10],
                         "vigencia_fim": str(a.get("dataVigenciaFim") or "")[:10],
                         "cancelada": bool(a.get("cancelado"))})
    return atas


# ------------------------------------------------------------------ B4 acao imediata
def resumo_conferencia(obj):
    """D19 parte 1: ultimo.json do confronto semanal (runner, so leitura) -> bloco enxuto para o B4. None se nao houver."""
    if not obj:
        return None
    itens = [{k: str(i.get(k, "")) for k in ("linha", "celula", "pregao", "tipo", "detalhe")} for i in obj.get("itens", [])][:25]
    return {"data": obj.get("data"), "divergencias": obj.get("divergencias", 0), "eventos": obj.get("eventos", 0),
            "gravaveis": obj.get("gravaveis", 0), "atas_diferentes": obj.get("atas_diferentes", 0), "pendencia": bool(obj.get("pendencia")),
            "linhas_lidas_pncp": obj.get("linhas_lidas_pncp"), "publicados": obj.get("publicados"), "itens": itens,
            "fonte": "confronto semanal planilha x PNCP/Compras.gov no runner (D19 parte 1); a gravacao do provado e sessao do Claude"}


def bloco_b4(atas, processos, vinculos, pendencias, hoje, conferencia=None, regra=None):
    vig = [a for a in atas if not a["cancelada"] and a["vigencia_fim"]]
    for a in vig:
        a["dias"] = (dt.date.fromisoformat(a["vigencia_fim"]) - hoje).days
    vencer = sorted((a for a in vig if 0 <= a["dias"] <= DIAS_ATA_A_VENCER), key=lambda a: a["dias"])
    proxima = min(vig, key=lambda a: a["dias"]) if vig else None
    atencao = [{"processo": p["processo"], "objeto": p["objeto"], "ugg": p["ugg"], "situacao_pncp": p["situacao_pncp"],
                "status_prazo": p["status_prazo"], "prazo_meta": p["prazo_meta"], "proxima_acao": p["proxima_acao"]}
               for p in processos if p["status_prazo"] == "Atrasado" or p["situacao_pncp"] == "Suspenso"]
    ver = [v for v in vinculos if v["nivel"] in NIVEIS_A_VERIFICAR]
    contagem = {n: dict.fromkeys(OMDS, 0) for n in NIVEIS_A_VERIFICAR}
    for v in ver:
        contagem[v["nivel"]][v["ug"]] += 1
    lista = sorted(ver, key=lambda v: (NIVEIS_A_VERIFICAR.index(v["nivel"]), -tr._num(v["valor"])))
    return {"atas": {"fonte": "PNCP (atas de registro de preços dos processos da carteira)", "n_vigentes": len(vig),
                     "a_vencer": vencer, "limite_dias": DIAS_ATA_A_VENCER,
                     "proxima": {k: proxima[k] for k in ("processo", "ata", "vigencia_fim", "dias")} if proxima else None},
            "processos": atencao,
            "ne_verificar": {"regra": "vínculo NE -> pregão v%s" % (regra or tr.VERSAO_REGRA), "contagem": contagem,
                             "lista": [{"documento": v["documento"], "omds": v["ug"], "valor": round(tr._num(v["valor"]), 2),
                                        "data": v["data"], "nivel": v["nivel"],
                                        "pregoes": v.get("candidatos") or ([v["pregao"]] if v["pregao"] else [])}
                                       for v in lista]},
            "pendencias": pendencias, "conferencia": resumo_conferencia(conferencia)}


# ------------------------------------------------------------------ extrato sem pessoa (ponte para a nuvem)
CAMPOS_EXTRATO = ("documento", "ug", "data", "valor", "modalidade", "nivel", "pregao", "candidatos")


def _br(v):
    """1234.5 -> '1.234,50' (formato do CSV do TG, que o leitor e o vinculo esperam)."""
    return f"{v:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def gerar_extrato(regs, fichas, data_execucao, origem):
    """Extrato SEM PESSOA da execucao: uma linha por NE com o resultado do vinculo. Nao leva favorecido nem texto."""
    vin = {v["documento"]: v for v in tr.vincular(regs, fichas)}
    linhas = []
    for r in regs:
        v = vin.get(r["documento"]) or {}
        linhas.append({"documento": r["documento"], "ug": r["_ug"], "data": r.get("data"), "valor": round(tr._num(r["valor"]), 2),
                       "modalidade": r.get("modalidade") or "", "nivel": v.get("nivel"), "pregao": v.get("pregao"),
                       "candidatos": v.get("candidatos") or []})
    return {"versao": 1, "data_execucao": data_execucao, "origem": origem, "regra_vinculo": tr.VERSAO_REGRA,
            "campos": list(CAMPOS_EXTRATO), "ne": linhas}


def ler_extrato(extrato):
    """Extrato -> (regs no formato do leitor do TG, vinculos). Versao 2: valor = LIQUIDO e valor_emitido no _emitido."""
    regs, vinculos = [], []
    for x in extrato["ne"]:
        nome = tr.UGS[x["ug"]]
        regs.append({"documento": x["documento"], "valor": _br(x["valor"]), "data": x["data"], "_ug": x["ug"], "_nome": nome,
                     "modalidade": x.get("modalidade", ""), "_emitido": x.get("valor_emitido")})
        if x.get("nivel"):
            vinculos.append({"nivel": x["nivel"], "pregao": x.get("pregao"), "candidatos": x.get("candidatos") or [],
                             "documento": x["documento"], "data": x["data"], "ug": nome, "valor": _br(x["valor"])})
    return regs, vinculos


def base_do_extrato(extrato):
    return "liquido" if extrato.get("versao") == 2 and extrato.get("base") == "liquido_6229201" else "emissao"


# ------------------------------------------------------------------ montagem e HTML
def montar(regs, data_execucao, processos, kpis, atas, fichas, pendencias, hoje, fontes, vinculos=None, conferencia=None,
           base="emissao", regra=None):
    if vinculos is None:
        vinculos = tr.vincular(regs, fichas)
    pend = ler_pendencias(pendencias)
    if pend["editado_em"]:
        pend["dias"] = (hoje - dt.date.fromisoformat(pend["editado_em"])).days
    idade_b1 = dias_uteis(dt.date.fromisoformat(data_execucao), hoje)
    regra = regra or tr.VERSAO_REGRA
    dados = {"meta": {"versao_motor": VERSAO_MOTOR, "regra_vinculo": regra, "base_b1": base, "hoje": hoje.isoformat(),
                      "fase": "A", "fontes": fontes, "fonte_b1": "tg", "idade_b1_dias_uteis": idade_b1,
                      "b1_fresco": idade_b1 <= DIAS_UTEIS_FRESCO, "dias_uteis_fresco": DIAS_UTEIS_FRESCO,
                      "dias_pendencias_amarelo": DIAS_PENDENCIAS_AMARELO},
             "b1": bloco_b1(regs, data_execucao, base, vinculos if regra == VERSAO_VINCULO_SIASG else None),
             "b3": bloco_b3(processos, kpis),
             "b4": bloco_b4(atas, processos, vinculos, pend, hoje, conferencia, regra)}
    dados["b4"]["data_dado_atas"] = next((f["data_dado"] for f in fontes if f["nome"] == "atas"), None)
    return dados


def json_canonico(dados):
    return json.dumps(dados, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_html(dados):
    corpo = json_canonico(dados)
    h = hashlib.sha256(corpo.encode("utf-8")).hexdigest()
    seguro = corpo.replace("</", "<\\/")  # nunca fechar o <script> por acidente
    return (Path(__file__).with_name("gof_painel_modelo.html").read_text(encoding="utf-8")
            .replace("__DADOS__", seguro).replace("__HASH__", h).replace("__TITULO__", html.escape("Painel GOF-BaApLog")))


def ler_carteira_json(caminho):
    """dados/carteira_processos.json (versionado, so colunas publicas) -> mesmo formato de ler_carteira()."""
    out = []
    for p in json.load(open(caminho, encoding="utf-8"))["processos"]:
        x = {k: str(p.get(k, "") or "").strip() for k in COLS}
        x["ordem"] = int(x["ordem"])
        x["estimado"], x["homologado"] = _num_br(x["estimado"]), _num_br(x["homologado"])
        out.append(x)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Motor do painel GOF-BaApLog, fase A")
    ex = ap.add_mutually_exclusive_group(required=True)
    ex.add_argument("--execucao", help="glob dos CSV do TG (um por OMDS); so onde o CSV com pessoa estiver")
    ex.add_argument("--extrato", help="extrato SEM PESSOA da execucao (JSON de gerar_extrato); e o que roda na nuvem")
    ap.add_argument("--data-execucao", help="data da exportacao do TG (AAAA-MM-DD); obrigatoria com --execucao")
    ap.add_argument("--fichas", required=True)
    ap.add_argument("--so-extrato", help="com --execucao: grava so o extrato sem pessoa neste caminho e sai")
    ap.add_argument("--carteira", help="CSV da aba Controle Processos ou dados/carteira_processos.json")
    ap.add_argument("--data-carteira", default=None, help="data da leitura da planilha (AAAA-MM-DD)")
    ap.add_argument("--kpis")
    ap.add_argument("--atas", help="JSON de atas; se nao existir, coleta do PNCP e grava")
    ap.add_argument("--pendencias")
    ap.add_argument("--conferencia", default=None, help="dados/conferencia/ultimo.json do confronto semanal (D19 parte 1)")
    ap.add_argument("--extrato-portal", default=None, help="extrato SEM PESSOA do Portal (gof_portal.py); reserva do B1 pela D17")
    ap.add_argument("--saida")
    ap.add_argument("--hoje", default=dt.date.today().isoformat())
    o = ap.parse_args(argv)
    hoje = dt.date.fromisoformat(o.hoje)
    conj = json.load(open(o.fichas, encoding="utf-8"))
    fichas = tr.ficha_de_pncp(conj)
    data_fichas = str(conj.get("coletado_em") or "2026-11-03")[:10]
    fonte_b1, motivo_b1, data_portal, base, regra = "tg", None, None, "emissao", None
    if o.execucao:
        if not o.data_execucao:
            raise SystemExit("--data-execucao e obrigatoria com --execucao")
        csvs = sorted(glob.glob(o.execucao))
        if len(csvs) != len(OMDS):
            raise SystemExit("esperados %d CSV do TG (um por OMDS), achados %d" % (len(OMDS), len(csvs)))
        regs = [r for c in csvs for r in tr.ler_csv_tg(c)]
        if o.so_extrato:
            ext = gerar_extrato(regs, fichas, o.data_execucao,
                                [{"arquivo": Path(c).name, "sha256": sha256(c)} for c in csvs])
            Path(o.so_extrato).write_text(json.dumps(ext, ensure_ascii=False, indent=0), encoding="utf-8")
            print("extrato sem pessoa: %d NE -> %s" % (len(ext["ne"]), o.so_extrato))
            return 0
        vinculos, data_exec = None, o.data_execucao
        f_exec = [{"nome": "execucao_tg", "arquivo": Path(c).name, "sha256": sha256(c), "data_dado": data_exec} for c in csvs]
    else:
        ext = json.load(open(o.extrato, encoding="utf-8"))
        regs, vinculos = ler_extrato(ext)
        data_exec = ext["data_execucao"]
        base, regra = base_do_extrato(ext), ext.get("regra_vinculo")
        f_exec = [{"nome": "execucao_tg", "arquivo": Path(o.extrato).name, "sha256": sha256(o.extrato), "data_dado": data_exec,
                   "nota": "extrato sem pessoa; vínculo v%s" % ext.get("regra_vinculo")}]
    # D17 revista: o Portal so substitui o TG parado ha mais de DIAS_UTEIS_FRESCO dias uteis E mais atual que ele
    if o.extrato_portal and Path(o.extrato_portal).exists():
        ext_p = json.load(open(o.extrato_portal, encoding="utf-8"))
        data_portal = ext_p.get("data_execucao")
        idade_tg = dias_uteis(dt.date.fromisoformat(data_exec), hoje)
        if idade_tg > DIAS_UTEIS_FRESCO and data_portal and data_portal > data_exec:
            regs, vinculos = ler_extrato(ext_p)
            fonte_b1, data_exec, base, regra = "portal", data_portal, "portal", ext_p.get("regra_vinculo")
            motivo_b1 = "TG parado ha %d dias uteis e Portal mais atual (%s > %s)" % (idade_tg, data_portal, ext["data_execucao"])
            f_exec = [{"nome": "execucao_portal", "arquivo": Path(o.extrato_portal).name, "sha256": sha256(o.extrato_portal),
                       "data_dado": data_exec, "nota": "RESERVA (D17): Portal da Transparencia, lacunas e atraso de ~7 dias; extrato sem pessoa"}]
        else:
            motivo_b1 = "TG fresco (%d dias uteis)" % idade_tg if idade_tg <= DIAS_UTEIS_FRESCO else "TG parado, mas Portal nao e mais atual (%s <= %s)" % (data_portal, data_exec)
    for k in ("carteira", "kpis", "atas", "pendencias", "saida"):
        if not getattr(o, k):
            raise SystemExit("--%s e obrigatorio para montar o painel" % k)
    processos = ler_carteira_json(o.carteira) if o.carteira.endswith(".json") else ler_carteira(o.carteira)
    kpis = json.load(open(o.kpis, encoding="utf-8"))
    pa = Path(o.atas)
    if not pa.exists():
        pa.write_text(json.dumps({"coletado_em": hoje.isoformat(), "atas": coletar_atas(processos)}, ensure_ascii=False,
                                 indent=1), encoding="utf-8")
    atas_j = json.load(open(pa, encoding="utf-8"))
    pend = json.load(open(o.pendencias, encoding="utf-8"))
    fontes = (f_exec
              + [{"nome": "carteira", "arquivo": Path(o.carteira).name, "sha256": sha256(o.carteira),
                  "data_dado": o.data_carteira or hoje.isoformat()},
                 {"nome": "kpis_painel", "arquivo": Path(o.kpis).name, "sha256": sha256(o.kpis), "data_dado": kpis.get("lido_em")},
                 {"nome": "atas", "arquivo": pa.name, "sha256": sha256(pa), "data_dado": atas_j.get("coletado_em")},
                 {"nome": "fichas_pncp", "arquivo": Path(o.fichas).name, "sha256": sha256(o.fichas), "data_dado": data_fichas}])
    conf = json.load(open(o.conferencia, encoding="utf-8")) if o.conferencia and Path(o.conferencia).exists() else None
    dados = montar(regs, data_exec, processos, kpis, atas_j["atas"], fichas, pend, hoje, fontes, vinculos=vinculos, conferencia=conf,
                   base=base, regra=regra)
    dados["meta"].update({"fonte_b1": fonte_b1, "fonte_b1_motivo": motivo_b1, "data_portal": data_portal,
                          "data_tg": data_exec if (o.execucao or fonte_b1 == "tg") else ext["data_execucao"]})
    s = Path(o.saida)
    s.mkdir(parents=True, exist_ok=True)
    (s / "dados.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    (s / "index.html").write_text(render_html(dados), encoding="utf-8")
    print("B1: %d NE, R$ %.2f | B3: %d processos | B4: %d atas vigentes, %d a vencer, %d processos em atencao, %d NE a verificar"
          % (dados["b1"]["ne"], dados["b1"]["total"], dados["b3"]["resumo"]["processos"], dados["b4"]["atas"]["n_vigentes"],
             len(dados["b4"]["atas"]["a_vencer"]), len(dados["b4"]["processos"]), len(dados["b4"]["ne_verificar"]["lista"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
