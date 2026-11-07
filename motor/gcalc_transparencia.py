# -*- coding: utf-8 -*-
"""
gcalc_transparencia.py (v1.2, 07nov2026; v1.1 de 06nov2026; v1 de 04nov2026) — execucao da despesa (empenhos) dos pregoes do GCALC, pelo Portal da Transparencia.

SOMENTE LEITURA. A chave da API vem de PORTAL_TRANSPARENCIA_API_KEY (nuvem) ou do .env; NUNCA e impressa nem gravada.
O Portal NAO informa numero de pregao, ata ou item: o vinculo empenho -> pregao e INFERIDO por regra explicita (3 niveis):
  CONFIRMADO     : texto cita numero/ano do pregao E o favorecido e fornecedor de ata do pregao (CNPJ ou nome normalizado).
                   Regra de 06/11/2026 (LOG-121): a UASG gerenciadora NAO e exigida no texto, porque o EB escreve a UG da NC
                   ou da requisicao depois do numero ("PREGAO 90023/2025 - 1602462026NC011459 ..."), nao a UASG do pregao.
  CITADO_SEM_ATA : texto cita numero/ano do pregao, mas o favorecido NAO e fornecedor de ata: colisao de numero (cada UASG
                   do EB reinicia a serie 900xx/ano) ou compra fora de ata. Nao e execucao; vai ao relatorio para verificar.
  ALERTA         : texto cita pregao + a UASG gerenciadora explicitamente (como numero isolado, nao dentro do numero da NC)
                   e o favorecido NAO e fornecedor de ata.
  PROVAVEL       : sem citar o pregao, mas favorecido e fornecedor de ata do pregao, a UG emitente e do GCALC e a data
                   e posterior a primeira assinatura de ata. NAO e dado confirmado: vai ao relatorio como "a confirmar".
  AMBIGUO        : (v1.2, 07/11/2026, LOG-130) o melhor nivel (CONFIRMADO ou PROVAVEL) e atingido por MAIS DE UM pregao
                   (mesmo fornecedor com ata nos dois): nao e atribuido a nenhum; vai ao relatorio com os candidatos.
  (demais)       : NAO VINCULADO (fica so no bruto).
Numeros baixos colidem entre unidades (ex.: "74/2026" do BMSA x PE 74/2026 da ECT): por isso numero SOZINHO nunca vincula.
Biblioteca padrao + requests.
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"
UGS = {"160238": "BaApLog", "160329": "BCMS", "160304": "BMSA", "160321": "ECT", "160246": "DCMun", "160307": "1oDSup",
       # regra viva de 05/11/2026 (LOG-098): toda consulta inclui a UG secundaria 167xxx de cada OMDS
       "167238": "BaApLog", "167329": "BCMS", "167304": "BMSA", "167321": "ECT", "167246": "DCMun", "167307": "1oDSup"}
# UG alvo ampliadas: as 6 do GCALC + participantes de atas + unidades com adesao aprovada (coleta de 04/11/2026)
UGS_ALVO = set(UGS) | {"160253", "160290", "160317", "160501", "785340", "160311", "160315", "160279", "930147",
                       "160327", "160123", "160236", "765703", "160468"}
POR_PAGINA = 15
MAX_PAGINAS = 40  # teto de seguranca; se atingido, a coleta ABORTA o dia (nunca trunca em silencio)
PAUSA = 0.75
VERSAO_REGRA = "1.2"  # gravada em cada vinculo, para o recalculo saber com que regra o numero foi feito


class Truncado(RuntimeError):
    pass


def chave_api():
    """Chave da API: variavel de ambiente ou .env da raiz do workspace. Nunca e impressa."""
    k = os.environ.get("PORTAL_TRANSPARENCIA_API_KEY", "").strip()
    if k:
        return k
    raiz = Path(__file__).resolve().parents[5] if len(Path(__file__).resolve().parents) > 5 else Path.cwd()
    env = raiz / ".env"
    if env.exists():
        m = re.search(r"^PORTAL_TRANSPARENCIA_API_KEY\s*=\s*(\S+)", env.read_text(encoding="utf-8", errors="ignore"), re.M)
        if m:
            return m.group(1).strip().strip("'\"")
    return ""


def so_digitos(s):
    return re.sub(r"\D", "", str(s or ""))


def norm_nome(s):
    """Nome de favorecido normalizado (sem acento, so letras e digitos, maiusculas) para casar com a ficha quando nao ha CNPJ."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", t)


def nome_bate(fav_nome, nomes):
    """O TG trunca o nome do favorecido (~55 caracteres): aceita igualdade ou prefixo com ao menos 12 caracteres."""
    if not fav_nome or len(fav_nome) < 12:
        return False
    return any(n == fav_nome or n.startswith(fav_nome) or fav_nome.startswith(n) for n in nomes if len(n) >= 12)


RE_NE = re.compile(r"^(\d{6})000012\d{3}NE\d{6}$")  # UG + 00001 + ano + NE + 6 digitos


def ler_csv_tg(caminho, encoding="cp1252"):
    """Le o CSV exportado pela tela do TG (Exportar > Arquivo em formato CSV): tabulacao, cp1252, cabecalho de varias linhas,
    linhas de SUBTOTAL e TOTAL misturadas aos dados (LOG-120, item 6). So entram as linhas cujo campo 'NE CCor' tem o padrao da NE.
    Devolve empenhos no mesmo formato da API do Portal (documento, valor, observacao, favorecido, _ug, _nome, modalidade, data)."""
    txt = Path(caminho).read_bytes().decode(encoding)
    linhas = txt.splitlines()
    hdr = next((i for i, ln in enumerate(linhas) if "UG Executora" in ln and "NE CCor" in ln), None)
    if hdr is None:
        raise RuntimeError("cabecalho do CSV do TG nao encontrado em %s" % caminho)
    h = [c.strip().strip('"').strip() for c in linhas[hdr].split("\t")]
    def col(nome):
        return h.index(nome) if nome in h else None
    ine, ifav, imod, idesc, idia = col("NE CCor"), col("NE CCor - Favorecido"), col("NE - Modalidade Licitação"), col("NE - Descrição"), col("NE - Dia Emissão")
    out = []
    re_data = re.compile(r"^\d{2}/\d{2}/\d{4}$")
    for ln in linhas[hdr + 1:]:
        c = [x.strip().strip('"').strip() for x in ln.split("\t")]
        if len(c) < len(h) or ine is None:
            continue
        m = RE_NE.match(c[ine])
        if not m:
            continue  # cabecalho secundario, subtotal, total ou linha vazia
        if idia is None:
            # "NE - Dia Emissao" vem na SEGUNDA linha do cabecalho do TG (atributo de coluna): achar pelo conteudo
            idia = next((i for i, x in enumerate(c) if re_data.match(x)), -1)
        val = c[-1]
        if not re.match(r"^-?\d{1,3}(\.\d{3})*,\d{2}$", val):
            continue
        ug = m.group(1)
        out.append({"documento": c[ine], "valor": val, "observacao": c[idesc] if idesc is not None else "",
                    "favorecido": c[ifav] if ifav is not None else "", "codigoFavorecido": "",
                    "modalidade": c[imod] if imod is not None else "", "data": c[idia] if idia not in (None, -1) else "",
                    "_ug": ug, "_nome": UGS.get(ug, ug), "_fonte": "TG"})
    return out


def _pega(sess, headers, ug, dia, pag):
    import requests  # import tardio: o modulo de vinculo funciona sem rede
    for i in range(4):
        time.sleep(PAUSA)
        r = requests.get(BASE + "/despesas/documentos", headers=headers, timeout=60,
                         params={"unidadeGestora": ug, "dataEmissao": dia.strftime("%d/%m/%Y"), "fase": 1, "pagina": pag})
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            time.sleep(30 * (i + 1))
            continue
        raise RuntimeError("HTTP %s em %s %s p%d" % (r.status_code, ug, dia, pag))
    raise RuntimeError("429 persistente em %s %s" % (ug, dia))


def coletar(inicio, fim, ugs=UGS):
    """Empenhos (fase 1) das UG, de `inicio` a `fim` (dias uteis). Devolve (registros, falhas)."""
    chave = chave_api()
    if not chave:
        raise RuntimeError("PORTAL_TRANSPARENCIA_API_KEY ausente")
    headers = {"chave-api-dados": chave, "Accept": "application/json"}
    regs, falhas = [], []
    dia = inicio
    while dia <= fim:
        if dia.weekday() < 5:
            for ug, nome in ugs.items():
                pag = 1
                try:
                    while True:
                        if pag > MAX_PAGINAS:
                            raise Truncado("mais de %d paginas em %s %s" % (MAX_PAGINAS, ug, dia))
                        d = _pega(None, headers, ug, dia, pag)
                        if not d:
                            break
                        regs += [dict(x, _ug=ug, _nome=nome) for x in d]
                        if len(d) < POR_PAGINA:
                            break
                        pag += 1
                except (OSError, RuntimeError, ValueError, KeyError) as e:  # rede (requests herda de OSError), HTTP e JSON: registrada, nunca silenciada
                    falhas.append({"ug": ug, "dia": dia.isoformat(), "erro": str(e)[:120]})
        dia += dt.timedelta(days=1)
    return regs, falhas


def sha256(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


# ------------------------------------------------------------------ ficha-mestre dos pregoes
ALIASES = {"PE 108/2026": {"numero": "108", "ano": "2026", "alternativos": ["92"]}}  # relancamento: PE 92 -> PE 108


def ficha_de_pncp(conjunto):
    """Ficha de cada pregao a partir do conjunto PNCP (pncp_12_processos.json): so o que o portal prova."""
    fichas = []
    chaves = list(conjunto["dados"])
    for i, p in enumerate(conjunto["processos"]):
        # a planilha ja pode trazer o numero novo (PE 108/2026) enquanto o conjunto guarda o antigo (PE 92/2026)
        al = ALIASES.get(p["no"], {})
        v = conjunto["dados"].get(p["no"]) or conjunto["dados"].get(chaves[i]) or {}
        det = v.get("detalhe") or {}
        cnpjs = {}
        for itens in (v.get("resultados") or {}).values():
            for r in itens or []:
                ni = so_digitos(r.get("niFornecedor"))
                if ni:
                    cnpjs[ni] = r.get("nomeRazaoSocialFornecedor") or ""
        atas = []
        for a in ((v.get("atas") or {}).get("data") or []):
            atas.append({"ata": "%s/%s" % (a.get("numeroAtaRegistroPreco"), a.get("anoAta")),
                         "assinatura": a.get("dataAssinatura"), "vigencia_fim": a.get("dataVigenciaFim"),
                         "cancelada": bool(a.get("cancelado"))})
        ass = sorted(a["assinatura"] for a in atas if a["assinatura"])
        fichas.append({
            "ordem": p["ordem"], "pregao": p["no"], "numero_pncp": al.get("numero") or str(det.get("numeroCompra") or ""),
            "numeros_alternativos": al.get("alternativos", []),
            "ano_pncp": al.get("ano") or str(det.get("anoCompra") or p.get("ano") or ""), "uasg": p["uasg"], "ugg": p["ugg"],
            "objeto_planilha": p["objeto"], "objeto_pncp": (det.get("objetoCompra") or "")[:300],
            "situacao_pncp": det.get("situacaoCompraNome"), "estimado": det.get("valorTotalEstimado"),
            "homologado": det.get("valorTotalHomologado"),
            "identificacao_pncp": "%s-1-%s/%s" % (p.get("cnpj"), str(p.get("seq", "")).zfill(6), p.get("ano")),
            "fornecedores": cnpjs, "fornecedores_nomes": {norm_nome(n) for n in cnpjs.values() if n},
            "atas": atas, "primeira_assinatura": ass[0] if ass else None})
    return fichas


# ------------------------------------------------------------------ vinculo empenho -> pregao
def _cita_pregao(texto, numero, ano):
    """Numero/ano precedido de PREGAO/PE/UGP <uasg> (evita 'REQ N 92/2026' e numeros de NC/processo)."""
    if not str(numero).strip() or not str(ano).strip():
        return False
    n = str(numero).lstrip("0") or "0"
    a = str(ano)
    # prefixos aceitos: PREGAO, PE, UGP <uasg>, UGP/UGG direto, e "N", "NR", "N°" entre o prefixo e o numero
    pad = r"(?:preg\w*|\bpe|\bug[pg]|\bugp\W{0,3}\d{6})\W{0,6}(?:n[ro°º]?\.?\W{0,3})?0*%s\s*/\s*(?:%s|%s)(?!\d)"
    return bool(re.search(pad % (re.escape(n), a, a[-2:]), texto))


_RE_CITA = re.compile(r"(?:preg\w*|pe|ug[pg])\W{0,6}(?:n[ro°º]?\.?\W{0,3})?0*(\d{1,6})\s*/\s*(\d{4}|\d{2})(?!\d)(?P<resto>.{0,90})")
_RE_UASG = re.compile(r"(?:uasg|ug[pg]?|ug)\W{0,4}(\d{6})")


def citados_fora_da_carteira(empenhos, fichas):
    """Empenhos que citam 'PREGAO n/ano ... UASG xxxxxx' de um pregao que NAO esta na carteira.
    Devolve lista ordenada por valor: [{uasg, numero, ano, n_ne, valor, ugs, amostra}]. So leitura; e pista, nao prova."""
    conhecidos = set()
    for f in fichas:
        for n in [f.get("numero_pncp")] + list(f.get("numeros_alternativos", [])):
            if n:
                conhecidos.add((str(f.get("uasg")), str(n).lstrip("0"), str(f.get("ano_pncp"))))
    grupos = {}
    for e in empenhos:
        texto = " ".join(str(e.get(k) or "") for k in ("observacao", "numeroProcesso")).lower()
        for m in _RE_CITA.finditer(texto):
            mu = _RE_UASG.search(m.group("resto"))
            if not mu:
                continue
            ano = m.group(2) if len(m.group(2)) == 4 else "20" + m.group(2)
            chave = (mu.group(1), m.group(1).lstrip("0") or "0", ano)
            if chave in conhecidos:
                continue
            g = grupos.setdefault(chave, {"uasg": chave[0], "numero": chave[1], "ano": chave[2], "n_ne": 0, "valor": 0.0, "ugs": set(), "amostra": []})
            g["n_ne"] += 1
            g["valor"] += _num(e.get("valor"))
            g["ugs"].add(e.get("_nome") or e.get("_ug") or "")
            if len(g["amostra"]) < 3:
                g["amostra"].append(e.get("documento"))
    out = []
    for g in grupos.values():
        g["ugs"] = sorted(x for x in g["ugs"] if x)
        out.append(g)
    return sorted(out, key=lambda x: -x["valor"])


def _data(s):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(str(s or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def vincular(empenhos, fichas):
    """Classifica cada empenho. Devolve lista de dicts com nivel, pregao e a regra que sustentou."""
    saida = []
    for e in empenhos:
        texto = " ".join(str(e.get(k) or "") for k in ("observacao", "numeroProcesso")).lower()
        fav = so_digitos(e.get("codigoFavorecido"))
        fav_nome = norm_nome(e.get("favorecido") or e.get("nomeFavorecido"))
        dia = _data(e.get("data"))
        modalidade = str(e.get("modalidade") or "").strip()
        achados = []
        for f in fichas:
            cita = any(_cita_pregao(texto, n, f["ano_pncp"]) for n in [f["numero_pncp"]] + f.get("numeros_alternativos", []))
            # fronteira de digito: a UASG aparece DENTRO do numero da NC ("1602462026NC...") e isso nao e citar a UASG (LOG-130)
            cita_uasg = cita and bool(re.search(r"(?<!\d)%s(?!\d)" % re.escape(str(f["uasg"])), texto))
            fornecedor = bool(fav and fav in f["fornecedores"]) or (not fav and nome_bate(fav_nome, f.get("fornecedores_nomes", set())))
            if cita and fornecedor:
                if modalidade and modalidade not in ("12", "PREGAO"):
                    nivel, regra = "ALERTA", "texto cita o pregao e favorecido e de ata, mas a modalidade da NE nao e pregao (%s)" % modalidade
                else:
                    nivel, regra = "CONFIRMADO", "texto cita o pregao e favorecido e fornecedor de ata (CNPJ ou nome); UASG nao exigida (LOG-121)"
            elif cita_uasg:
                nivel, regra = "ALERTA", "texto cita pregao + UASG gerenciadora, favorecido NAO consta nas atas (compra fora de ata?)"
            elif cita:
                nivel, regra = "CITADO_SEM_ATA", "texto cita o numero do pregao, favorecido NAO e de ata: colisao de numero ou fora de ata; verificar"
            elif (fornecedor and e.get("_ug") in UGS_ALVO and f["primeira_assinatura"] and dia
                  and str(dia) >= str(f["primeira_assinatura"])[:10]):
                nivel, regra = "PROVAVEL", "favorecido e fornecedor de ata, UG do GCALC, data apos a assinatura; texto nao cita o pregao"
            else:
                continue
            achados.append(({"CONFIRMADO": 0, "ALERTA": 1, "CITADO_SEM_ATA": 2, "PROVAVEL": 3}[nivel], nivel, regra, f))
        if not achados:
            continue
        topo = min(a[0] for a in achados)
        empatados = [a for a in achados if a[0] == topo]
        _, nivel_final, regra_final, ficha = empatados[0]
        candidatos = [a[3]["pregao"] for a in empatados]
        pregao = ficha["pregao"]
        if len(empatados) > 1 and nivel_final in ("CONFIRMADO", "PROVAVEL"):
            # v1.2 (LOG-130): antes o valor ia para o primeiro pregao da lista; agora nao vai para nenhum
            regra_final = "%s em mais de um pregao (%s): nao atribuido" % (nivel_final, " | ".join(candidatos))
            nivel_final, pregao = "AMBIGUO", None
        elif nivel_final == "CONFIRMADO" and _num(e.get("valor")) == 0.0:
            # NE com valor R$ 0,00 (possivel anulacao total): vinculo existe, mas nao e execucao
            nivel_final, regra_final = "ZERADO", regra_final + "; NE com valor R$ 0,00 (possivel anulacao): fora do total"
        saida.append({"nivel": nivel_final, "pregao": pregao, "candidatos": candidatos, "regra": regra_final,
                      "versao_regra": VERSAO_REGRA, "documento": e.get("documento"),
                      "data": e.get("data"), "ug": e.get("_nome"), "valor": e.get("valor"),
                      "favorecido": e.get("favorecido"), "elemento": e.get("elemento"),
                      "observacao": str(e.get("observacao") or "")[:140]})
    return saida


def _num(s):
    try:
        return float(str(s).replace(".", "").replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def resumo(vinculos, fichas):
    """Empenhado por pregao e por UG (so CONFIRMADO conta como execucao; PROVAVEL e informado a parte)."""
    por = {f["pregao"]: {"confirmado": 0.0, "n_confirmado": 0, "provavel": 0.0, "n_provavel": 0, "alertas": 0,
                         "por_ug": {}, "homologado": f.get("homologado")} for f in fichas}
    for v in vinculos:
        if v["nivel"] == "AMBIGUO":
            # informativo em cada candidato; o valor NAO entra em confirmado nem em provavel de nenhum
            for c in v.get("candidatos") or []:
                rc = por[c]
                rc["n_ambiguo"] = rc.get("n_ambiguo", 0) + 1
                rc["ambiguo_informativo"] = rc.get("ambiguo_informativo", 0.0) + _num(v["valor"])
            continue
        r = por[v["pregao"]]
        val = _num(v["valor"])
        if v["nivel"] == "CONFIRMADO":
            r["confirmado"] += val
            r["n_confirmado"] += 1
            r["por_ug"][v["ug"]] = r["por_ug"].get(v["ug"], 0.0) + val
        elif v["nivel"] == "PROVAVEL":
            r["provavel"] += val
            r["n_provavel"] += 1
        elif v["nivel"] == "ZERADO":
            r["n_zerado"] = r.get("n_zerado", 0) + 1
        elif v["nivel"] == "CITADO_SEM_ATA":
            r["n_citado_sem_ata"] = r.get("n_citado_sem_ata", 0) + 1
        else:
            r["alertas"] += 1
    for r in por.values():
        h = r["homologado"]
        r["taxa_uso"] = round(r["confirmado"] / h, 4) if h else None
    return por


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Coleta empenhos e vincula aos pregoes (somente leitura)")
    ap.add_argument("--conjunto", required=True, help="pncp_12_processos.json")
    ap.add_argument("--bruto", help="JSON de empenhos ja coletado (evita rede)")
    ap.add_argument("--desde", default="2026-09-28")
    ap.add_argument("--ate", default=dt.date.today().isoformat())
    ap.add_argument("--saida", default=".")
    o = ap.parse_args()
    fichas = ficha_de_pncp(json.load(open(o.conjunto, encoding="utf-8")))
    if o.bruto:
        regs, falhas = json.load(open(o.bruto, encoding="utf-8")), []
    else:
        regs, falhas = coletar(dt.date.fromisoformat(o.desde), dt.date.fromisoformat(o.ate))
    vin = vincular(regs, fichas)
    res = resumo(vin, fichas)
    os.makedirs(o.saida, exist_ok=True)
    json.dump({"fichas": fichas, "vinculos": vin, "resumo": res, "falhas": falhas, "empenhos_lidos": len(regs),
               "janela": [o.desde, o.ate]},
              open(os.path.join(o.saida, "transparencia_vinculos.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cont = {}
    for v in vin:
        cont[v["nivel"]] = cont.get(v["nivel"], 0) + 1
    print("empenhos lidos:", len(regs), "| vinculados:", cont, "| falhas:", len(falhas))


if __name__ == "__main__":
    main()
