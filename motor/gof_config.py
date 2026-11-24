# -*- coding: utf-8 -*-
"""
gof_config.py (v1.0, 24nov2026) — configuração por OM do painel (Etapa A, release v2.2-parametrizado).

Lê `config/om.json` (a OM e as suas OMDS/UG), o calendário do exercício e as metas da Diretriz que ele aponta, e entrega
as tabelas derivadas que os módulos usavam fixas no código (inventário v1.0, §3). Nada de segredo aqui.

Qual configuração: a variável de ambiente GOF_CONFIG (caminho de um om.json); sem ela, `config/om.json` do repositório.
Os caminhos de `metas`, `calendario` e `brasoes` são relativos à pasta do om.json; se não existirem ali, à pasta `config/`.
"""
import datetime as dt
import json
import os
import re
from functools import cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_CONFIG = RAIZ / "config"


def caminho_om():
    return Path(os.environ.get("GOF_CONFIG") or PASTA_CONFIG / "om.json").resolve()


def _resolver(base, rel):
    p = Path(rel)
    if p.is_absolute():
        return p
    for pasta in (base, PASTA_CONFIG):
        if (pasta / p).exists():
            return (pasta / p).resolve()
    return (base / p).resolve()


def _ler(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


@cache
def _carregar(caminho):
    p = Path(caminho)
    om = _ler(p)
    base = p.parent
    cal_p = _resolver(base, om["calendario"])
    om["_caminho"] = str(p)
    om["_calendario_caminho"] = str(cal_p)
    om["_calendario"] = _ler(cal_p)
    if om.get("metas"):
        met_p = _resolver(base, om["metas"])
        om["_metas_caminho"] = str(met_p)
        om["_metas"] = _ler(met_p) if met_p.exists() else None
    if om.get("brasoes"):
        om["_brasoes_caminho"] = str(_resolver(base, om["brasoes"]))
    return om


def carregar(caminho=None):
    """Configuração completa (om.json + calendário + metas), em cache por caminho."""
    return _carregar(str(Path(caminho).resolve() if caminho else caminho_om()))


PASTA_PONTE_PADRAO = "PONTE_TG_SEM_PESSOA"
MODOS_CPF = ("mascarado", "completo")
SEP_CPF = r"[\s.\u2013\u2014]?"          # espaço, ponto ou travessão entre os grupos
SEP_DV = r"[\s.\-\u2013\u2014/]?"        # antes do dígito verificador, também hífen e barra
_RE_CPF = re.compile(r"(?<![\d*])(\d{3})" + SEP_CPF + r"(\d{3})" + SEP_CPF + r"(\d{3})" + SEP_DV + r"(\d{2})(?![\d*])")


def dados_pessoais(caminho=None):
    """O que a OM mostra de favorecido (campo `dados_pessoais` do config). Sem o campo (BaApLog): nada, o corte
    histórico. `favorecido`: nome e documento de quem recebe; `cpf`: «mascarado» (***.456.789-**, padrão do Portal da
    Transparência) ou «completo» (só com a página fora da internet aberta; decisão do usuário, LOG-033 do PAINEL GOF DF)."""
    om = caminho if isinstance(caminho, dict) else carregar(caminho)
    d = om.get("dados_pessoais") or {}
    # «completo» não vale enquanto a página for pública (decisão do usuário, LOG-034 do PAINEL GOF DF): o verificar_config
    # o reprova e, por segurança, aqui ele vira «mascarado» — nada publica CPF inteiro.
    return {"favorecido": bool(d.get("favorecido")), "cpf": "mascarado"}


def mascarar_cpf(texto, modo="mascarado"):
    """CPF (11 dígitos, com ou sem pontuação) -> ***.ddd.ddd-** quando o modo é «mascarado»; CNPJ não é tocado."""
    if modo == "completo":
        return texto
    return _RE_CPF.sub(lambda m: "***.%s.%s-**" % (m.group(2), m.group(3)), str(texto))


def pasta_ponte(caminho=None):
    """Nome da pasta privada do Drive que a ponte do TG grava e a montagem lê (`assinaturas_tg.pasta_drive`).

    Sem o campo, vale o nome histórico da BaApLog. Outra OM na mesma conta Google deve ter pasta própria, para que
    as duas cadeias não se cruzem (verificar_config reprova o nome padrão fora da BaApLog)."""
    om = caminho if isinstance(caminho, dict) else carregar(caminho)
    return (om.get("assinaturas_tg") or {}).get("pasta_drive") or PASTA_PONTE_PADRAO


def omds(cfg=None):
    """Lista de OMDS na ordem de exibição."""
    cfg = cfg or carregar()
    return sorted(cfg["omds"], key=lambda o: o["ordem"])


# ---------------------------------------------------------------- tabelas derivadas (as que eram fixas no código)
def chaves_omds(cfg=None):
    """gof_painel.OMDS: chaves na ordem."""
    return [o["chave"] for o in omds(cfg)]


def rotulos_curtos_diferentes(cfg=None):
    """gof_painel.ROTULO_OMDS: só as chaves cujo rótulo curto difere da chave."""
    return {o["chave"]: o["rotulo_curto"] for o in omds(cfg) if o.get("rotulo_curto", o["chave"]) != o["chave"]}


def rotulo_por_chave(cfg=None):
    """gof_ponte_tg.OMDS_ROTULO e NOME do HTML: chave -> rótulo."""
    return {o["chave"]: o["rotulo"] for o in omds(cfg)}


def ordem_rotulos(cfg=None):
    """gof_regua_tg.ORDEM e ORDEM do HTML."""
    return [o["rotulo"] for o in omds(cfg)]


def rotulo_por_sufixo(cfg=None):
    """gof_regua_tg.OM: 3 últimos dígitos da UG -> rótulo, em ordem numérica do sufixo."""
    return {o["ug160"][3:]: o["rotulo"] for o in sorted(omds(cfg), key=lambda o: o["ug160"][3:])}


def ug_para_chave_intercalado(cfg=None):
    """recalculo_independente.UGS: UG 160 e 167 de cada OMDS, intercaladas, na ordem."""
    out = {}
    for o in omds(cfg):
        out[o["ug160"]] = o["chave"]
        if o.get("ug167"):
            out[o["ug167"]] = o["chave"]
    return out


def ug_para_chave_160_depois_167(cfg=None):
    """gcalc_transparencia.UGS: primeiro as UG 160 na ordem, depois as 167."""
    out = {o["ug160"]: o["chave"] for o in omds(cfg)}
    out.update({o["ug167"]: o["chave"] for o in omds(cfg) if o.get("ug167")})
    return out


def uasg_para_chave(cfg=None):
    """gof_conferencia.UASGS: UASG -> chave, na ordem."""
    return {o["uasg"]: o["chave"] for o in omds(cfg)}


def uasg_para_rotulo_numerico(cfg=None):
    """gof_capacidade.OMDS: UASG -> rótulo, em ordem numérica da UASG."""
    return {o["uasg"]: o["rotulo"] for o in sorted(omds(cfg), key=lambda o: o["uasg"])}


def ug_nome(cfg=None):
    """UGNOME do HTML: UG 160 -> nota da UG, só onde houver nota."""
    return {o["ug160"]: o["nota_ug"] for o in omds(cfg) if o.get("nota_ug")}


def ugs_alvo_extras(cfg=None):
    return list((cfg or carregar()).get("ugs_alvo_extras") or [])


def exercicio(cfg=None):
    return int((cfg or carregar())["exercicio"])


def bloco_ligado(nome, cfg=None):
    return bool(((cfg or carregar()).get("blocos") or {}).get(nome, False))


def janela(nome, padrao=None, cfg=None):
    return ((cfg or carregar()).get("janelas") or {}).get(nome, padrao)


def texto(nome, padrao="", cfg=None):
    return ((cfg or carregar()).get("textos") or {}).get(nome, padrao)


def referencia_regional(cfg=None):
    return (cfg or carregar()).get("referencia_regional")


def calendario(cfg=None):
    return (cfg or carregar())["_calendario"]


def feriados(cfg=None):
    """gof_painel.FERIADOS_2026: feriados do período do encerramento."""
    return {dt.date.fromisoformat(d) for d in calendario(cfg).get("feriados", [])}


def feriados_ano(cfg=None):
    """gof_regua_tg.FER: feriados nacionais do ano (prazo escrito na NC)."""
    return {dt.date.fromisoformat(d) for d in calendario(cfg).get("feriados_ano", [])}


def marcos_encerramento(cfg=None):
    """gof_painel.MARCOS_ENCERRAMENTO: (data, «ev. N», texto) na ordem do calendário."""
    return [(e["data"], "ev. " + e["ev"], e["texto"]) for e in calendario(cfg)["eventos"]]


def brasoes_caminho(cfg=None):
    c = (cfg or carregar()).get("_brasoes_caminho")
    return Path(c) if c else None


def js_objeto(d):
    """Objeto JS com a mesma grafia do modelo: chave sem aspas se for identificador, senão entre aspas."""
    partes = []
    for k, v in d.items():
        chave = k if (k[:1].isalpha() or k[:1] == "_") and k.replace("_", "").isalnum() and k.isascii() else json.dumps(k)
        partes.append("%s:%s" % (chave, json.dumps(v, ensure_ascii=False)))
    return "{" + ",".join(partes) + "}"


def js_lista(xs):
    return "[" + ",".join(json.dumps(x, ensure_ascii=False) for x in xs) + "]"


def main(argv=None):
    """v2.3: os workflows e o portao.sh perguntam ao config se um bloco está ligado (imprime 1 ou 0)."""
    import argparse

    ap = argparse.ArgumentParser(description="consulta a configuração da OM (config/om.json ou GOF_CONFIG)")
    ap.add_argument("--bloco", required=True, help="nome do bloco em «blocos» (ex.: carteira_gcalc, capacidade)")
    o = ap.parse_args(argv)
    blocos = carregar().get("blocos") or {}
    if o.bloco not in blocos:  # nome errado não pode virar «desligado» calado
        ap.error("bloco desconhecido no config: %s (há: %s)" % (o.bloco, ", ".join(sorted(blocos)) or "nenhum"))
    print(int(bool(blocos[o.bloco])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
