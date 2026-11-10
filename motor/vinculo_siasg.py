# -*- coding: utf-8 -*-
"""
vinculo_siasg.py (v2.0, 09nov2026) — vinculo NE -> pregao pela CHAVE SIASG da NE (P-064, LOG-181).

A NE do SIAFI traz, no campo «NE - Informacao Complementar» do Tesouro Gerencial, a chave da compra no SIASG:
    UASG(6) + modalidade(2) + numero(5) + ano(4) + " - UASG MINUTA: " + UASG da minuta
    ex.: "16032905900092025 - UASG MINUTA: 160329"  ->  UASG 160329, modalidade 05 (pregao), 90009/2025.
E dado estruturado do sistema, nao texto livre: resolve a colisao de numero entre UASG (cada UASG reinicia a serie
900xx/ano) e dispensa a inferencia por favorecido da regra v1.2. A regra v1.2 (texto + favorecido) fica so como conferencia.

Niveis (v2.0):
  SIASG           : a chave aponta para um pregao da carteira (mesma UASG, numero e ano). E o vinculo que conta.
  SEM_CHAVE_CITA  : a NE nao tem chave SIASG legivel e o texto cita numero/ano de um pregao da carteira. Vai ao B4
                    como «a verificar» (nao entra em total nenhum).
  (sem nivel)     : chave aponta para compra fora da carteira, ou sem chave e sem citacao: nao vinculada.
Medido em 09/11/2026 (TG, item 23, 12 UG): 2.629 NE com chave; 185 NE em 6 pregoes da carteira, R$ 492.252,09.
"""
import re

VERSAO_REGRA = "2.0"
RE_CHAVE = re.compile(r"^\s*(\d{6})(\d{2})(\d{5})(\d{4})\s*-\s*UASG MINUTA:\s*(\d{6})")
MODALIDADE_PREGAO = "05"


def ler_chave(texto):
    """'16032905900092025 - UASG MINUTA: 160329' -> dict; qualquer outra coisa -> None."""
    m = RE_CHAVE.match(str(texto or ""))
    if not m:
        return None
    return {"uasg": m.group(1), "modalidade": m.group(2), "numero": int(m.group(3)), "ano": m.group(4),
            "uasg_minuta": m.group(5)}


def chave_txt(ch):
    return "%s-%s-%05d/%s" % (ch["uasg"], ch["modalidade"], ch["numero"], ch["ano"]) if ch else None


def indice_carteira(fichas):
    """(uasg, numero, ano) -> pregao, para os pregoes da carteira com numero e ano no PNCP (inclui numeros alternativos)."""
    idx = {}
    for f in fichas:
        for n in [f.get("numero_pncp")] + list(f.get("numeros_alternativos", [])):
            if str(n or "").strip() and str(f.get("ano_pncp") or "").strip():
                idx[(str(f["uasg"]), int(n), str(f["ano_pncp"]))] = f["pregao"]
    return idx


def vincular_ne(chave_bruta, texto, fichas, idx=None, cita=None):
    """Classifica uma NE. `cita(texto, numero, ano)` e o detector de citacao da regra v1.2 (injetado para nao duplicar).
    Devolve {"nivel", "pregao", "candidatos", "chave"}; nivel None quando nao ha vinculo."""
    idx = idx if idx is not None else indice_carteira(fichas)
    ch = ler_chave(chave_bruta)
    if ch:
        p = idx.get((ch["uasg"], ch["numero"], ch["ano"]))
        if p and ch["modalidade"] == MODALIDADE_PREGAO:
            return {"nivel": "SIASG", "pregao": p, "candidatos": [p], "chave": chave_txt(ch)}
        return {"nivel": None, "pregao": None, "candidatos": [], "chave": chave_txt(ch)}
    if cita is not None:
        t = str(texto or "").lower()
        citados = [f["pregao"] for f in fichas
                   if any(cita(t, n, f.get("ano_pncp")) for n in [f.get("numero_pncp")] + list(f.get("numeros_alternativos", [])) if n)]
        if citados:
            return {"nivel": "SEM_CHAVE_CITA", "pregao": None, "candidatos": sorted(set(citados)), "chave": None}
    return {"nivel": None, "pregao": None, "candidatos": [], "chave": None}
