# -*- coding: utf-8 -*-
"""
verificar_config.py (v1.0, 24nov2026) — portão da configuração por OM (Etapa A, desenho v0.1, §7).

Reprova a configuração se:
  - faltar campo obrigatório do om.json, ou não houver OMDS;
  - uma UG estiver fora do padrão 16[07]ddd, repetida, ou sem a UG 160; ou a UG 167 não tiver o mesmo sufixo da 160
    (a régua do TG identifica a OMDS pelo sufixo); ou a UASG não tiver 6 dígitos;
  - chave ou ordem de OMDS se repetir;
  - as metas não tiverem sha256, estiverem fora da vigência do exercício, ou um grupo não tiver um valor por marco;
  - o calendário for de outro exercício, ou um evento não tiver data, papel (UGE/UGR/ambos), bloco ou texto;
  - um bloco estiver ligado sem o arquivo de dados correspondente.
Avisa (sem reprovar) quando o calendário passou da validade: o painel segue montando e a página mostra o dado; a
troca do calendário é a rotina anual (P3: parâmetro fixo tem prazo).

Uso: python verificar_config.py [--config config/om.json] [--hoje AAAA-MM-DD] [--dados <raiz dos dados>]
Sai com código 1 se houver erro. Nada de segredo é lido ou exigido aqui.
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gof_config as cfg  # noqa: E402

RE_UG = re.compile(r"16[07]\d{3}")
RE_UASG = re.compile(r"\d{6}")
RE_SHA = re.compile(r"[0-9a-f]{64}")
OBRIGATORIOS = ("id", "nome", "sigla", "exercicio", "calendario", "omds", "blocos", "textos")
TEXTOS = ("titulo_pagina", "eyebrow", "titulo")
PAPEIS = {"UGE", "UGR", "ambos"}
# bloco ligado -> arquivos de dados que ele exige (relativos à raiz do repositório)
DADOS_DO_BLOCO = {
    "carteira_gcalc": ["dados/carteira_processos.json", "dados/kpis_painel.json", "dados/pendencias_coordenador.json",
                       "dados/pncp/ultimo.json"],
    "pncp_atas": ["dados/pncp/ultimo.json"],
    "capacidade": ["dados/capacidade/ultimo.json"],
    "dispensa": ["dados/dispensa/ultimo.json"],
    # v2.4: sem arquivo obrigatório; sem o dado, a página publica o bloco com ressalva (P-RP-3)
    "rp_por_ano": [],
    "contratos": [],
}


def _data(s):
    try:
        return dt.date.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


def verificar(caminho, hoje=None, raiz_dados=None, avisos=None):
    """Lista de erros (vazia = aprovada). `avisos`, se for lista, recebe os avisos."""
    hoje = hoje or dt.date.today()
    raiz_dados = Path(raiz_dados) if raiz_dados else cfg.RAIZ
    avisos = avisos if avisos is not None else []
    erros = []
    p = Path(caminho)
    try:
        om = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return ["om.json ilegível (%s): %s" % (p, e)]
    for k in OBRIGATORIOS:
        if k not in om:
            erros.append("om.json sem o campo obrigatório «%s»" % k)
    if erros:
        return erros
    for k in TEXTOS:
        if not str((om.get("textos") or {}).get(k) or "").strip():
            erros.append("textos.%s vazio" % k)
    exercicio = om["exercicio"]
    omds = om.get("omds") or []
    if not omds:
        erros.append("nenhuma OMDS em omds[]")
    vistas, chaves, ordens = {}, set(), set()
    for i, o in enumerate(omds):
        rot = o.get("chave") or "omds[%d]" % i
        for campo in ("chave", "rotulo", "ordem", "ug160", "uasg"):
            if o.get(campo) in (None, ""):
                erros.append("%s sem «%s»" % (rot, campo))
        if o.get("chave") in chaves:
            erros.append("chave de OMDS repetida: %s" % o.get("chave"))
        chaves.add(o.get("chave"))
        if o.get("ordem") in ordens:
            erros.append("ordem de OMDS repetida: %s (%s)" % (o.get("ordem"), rot))
        ordens.add(o.get("ordem"))
        for campo in ("ug160", "ug167"):
            ug = o.get(campo)
            if ug in (None, ""):
                continue
            ug = str(ug)
            if not RE_UG.fullmatch(ug):
                erros.append("%s.%s fora do padrão 16[07]ddd: %s" % (rot, campo, ug))
            elif not ug.startswith(campo[2:]):
                erros.append("%s.%s deve começar por %s: %s" % (rot, campo, campo[2:], ug))
            if ug in vistas:
                erros.append("UG repetida: %s (%s e %s)" % (ug, vistas[ug], rot))
            vistas[ug] = rot
        if o.get("ug160") and o.get("ug167") and str(o["ug160"])[3:] != str(o["ug167"])[3:]:
            erros.append("%s: UG 160 e 167 com sufixos diferentes (%s, %s)" % (rot, o["ug160"], o["ug167"]))
        if o.get("uasg") and not RE_UASG.fullmatch(str(o["uasg"])):
            erros.append("%s.uasg fora do padrão de 6 dígitos: %s" % (rot, o["uasg"]))
    # calendário
    cal_p = cfg._resolver(p.parent, om["calendario"])
    if not cal_p.exists():
        erros.append("calendário não encontrado: %s" % om["calendario"])
    else:
        cal = json.loads(cal_p.read_text(encoding="utf-8"))
        if cal.get("exercicio") != exercicio:
            erros.append("calendário de outro exercício: %s (om.json: %s)" % (cal.get("exercicio"), exercicio))
        for campo in ("diploma", "diploma_curto", "diploma_rodape", "validade"):
            if not cal.get(campo):
                erros.append("calendário sem «%s»" % campo)
        for d in list(cal.get("feriados") or []) + list(cal.get("feriados_ano") or []):
            if not _data(d):
                erros.append("calendário: feriado com data inválida: %s" % d)
        if not cal.get("eventos"):
            erros.append("calendário sem eventos")
        for e in cal.get("eventos") or []:
            ev = e.get("ev") or "?"
            if not _data(e.get("data")):
                erros.append("evento %s sem data válida" % ev)
            elif _data(e["data"]).year != exercicio:
                erros.append("evento %s fora do exercício: %s" % (ev, e["data"]))
            if e.get("papel") not in PAPEIS:
                erros.append("evento %s sem papel UGE/UGR/ambos" % ev)
            if not e.get("bloco"):
                erros.append("evento %s sem bloco" % ev)
            if not e.get("texto"):
                erros.append("evento %s sem texto" % ev)
        val = _data(cal.get("validade"))
        if val and hoje > val:
            avisos.append("calendário vencido em %s: trocar pelo do exercício seguinte" % val.isoformat())
    # metas
    if om.get("metas"):
        met_p = cfg._resolver(p.parent, om["metas"])
        if not met_p.exists():
            erros.append("metas não encontradas: %s" % om["metas"])
        else:
            met = json.loads(met_p.read_text(encoding="utf-8"))
            if not RE_SHA.fullmatch(str((met.get("fonte") or {}).get("sha256") or "")):
                erros.append("metas sem sha256 da fonte")
            vig = met.get("vigencia") or {}
            ini, fim = _data(vig.get("inicio")), _data(vig.get("fim"))
            if not (ini and fim and ini.year <= exercicio <= fim.year):
                erros.append("metas fora da vigência do exercício %s: %s a %s" % (exercicio, vig.get("inicio"), vig.get("fim")))
            n = len(met.get("marcos") or [])
            for g in met.get("grupos") or []:
                for campo in ("empenho", "liquidacao", "liquidacao_rp"):
                    if len(g.get(campo) or []) != n:
                        erros.append("metas: grupo %s.%s sem um valor por marco (%d)" % (g.get("id"), campo, n))
    # brasões (opcional)
    if om.get("brasoes") and not cfg._resolver(p.parent, om["brasoes"]).exists():
        erros.append("brasões não encontrados: %s" % om["brasoes"])
    # bloco ligado sem dado
    for bloco, ligado in (om.get("blocos") or {}).items():
        if bloco not in DADOS_DO_BLOCO:
            erros.append("bloco desconhecido: %s" % bloco)
            continue
        if ligado:
            for arq in DADOS_DO_BLOCO[bloco]:
                if not (raiz_dados / arq).exists():
                    erros.append("bloco %s ligado sem o arquivo de dados %s" % (bloco, arq))
    return erros


def main(argv=None):
    ap = argparse.ArgumentParser(description="Portão da configuração por OM")
    ap.add_argument("--config", default=None, help="om.json (padrão: GOF_CONFIG ou config/om.json)")
    ap.add_argument("--hoje", default=None)
    ap.add_argument("--dados", default=None, help="raiz dos dados (padrão: a raiz do repositório)")
    o = ap.parse_args(argv)
    caminho = Path(o.config).resolve() if o.config else cfg.caminho_om()
    avisos = []
    erros = verificar(caminho, dt.date.fromisoformat(o.hoje) if o.hoje else None, o.dados, avisos)
    for a in avisos:
        print("AVISO: " + a)
    if erros:
        print("CONFIG: %d erro(s) em %s" % (len(erros), caminho))
        for e in erros:
            print("  - " + e)
        return 1
    print("CONFIG: ok (%s)" % caminho)
    return 0


if __name__ == "__main__":
    sys.exit(main())
