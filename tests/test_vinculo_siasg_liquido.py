# -*- coding: utf-8 -*-
"""Regra 2.0 (chave SIASG, P-064) e B1 na base liquida (P-063), LOG-181 (09nov2026)."""
import json

import gcalc_transparencia as tr
import gof_extrato_tg as gx
import gof_painel as gp
import vinculo_siasg as vs

FICHAS = [
    {"pregao": "PE 90009/2025", "uasg": "160329", "numero_pncp": "90009", "numeros_alternativos": [], "ano_pncp": "2025"},
    {"pregao": "PE 108/2026", "uasg": "160307", "numero_pncp": "108", "numeros_alternativos": ["92"], "ano_pncp": "2026"},
    {"pregao": "INT-90005/2025", "uasg": "160321", "numero_pncp": "", "numeros_alternativos": [], "ano_pncp": ""},
]


def test_chave_da_carteira_vincula():
    v = vs.vincular_ne("16032905900092025 - UASG MINUTA: 160238", "texto qualquer", FICHAS, cita=tr._cita_pregao)
    assert v["nivel"] == "SIASG" and v["pregao"] == "PE 90009/2025" and v["chave"] == "160329-05-90009/2025"


def test_mesmo_numero_em_outra_uasg_nao_vincula():
    # colisao de serie: 90009/2025 do BMSA (160304) nao e o PE 90009/2025 do BCMS, mesmo que o texto cite o numero
    v = vs.vincular_ne("16030405900092025 - UASG MINUTA: 160304", "PREGAO 90009/2025", FICHAS, cita=tr._cita_pregao)
    assert v["nivel"] is None and v["pregao"] is None


def test_numero_alternativo_e_modalidade():
    assert vs.vincular_ne("16030705000922026 - UASG MINUTA: 160307", "", FICHAS)["pregao"] == "PE 108/2026"
    # modalidade 06 (dispensa) com o mesmo numero: nao e o pregao
    assert vs.vincular_ne("16030706000922026 - UASG MINUTA: 160307", "", FICHAS)["nivel"] is None


def test_sem_chave_que_cita_vai_a_verificar():
    v = vs.vincular_ne("SEM INFORMACAO", "CONFORME PREGAO 90009/2025", FICHAS, cita=tr._cita_pregao)
    assert v["nivel"] == "SEM_CHAVE_CITA" and v["candidatos"] == ["PE 90009/2025"] and v["pregao"] is None
    assert vs.vincular_ne("SEM INFORMACAO", "AQUISICAO DE MATERIAL", FICHAS, cita=tr._cita_pregao)["nivel"] is None


def _linha(ne, ug, emit, liq, desc="", dia="10/03/2026"):
    return {"ne": ne, "ug": ug, "dia_emissao": dia, "emissao_522920101": emit, "empenhado_liquido_6229201": liq,
            "modalidade": "12", "descricao": desc}


def test_extrato_confere_item23_e_aborta_se_diverge():
    liq = {"160329000012026NE000001": _linha("160329000012026NE000001", "160329", "100,00", "100,00"),
           "160329000012026NE000002": _linha("160329000012026NE000002", "160329", "50,00", "0,00")}
    ch = {"160329000012026NE000001": {"chave": "16032905900092025 - UASG MINUTA: 160329", "item23": 100.0},
          "160329000012026NE000002": {"chave": "SEM INFORMACAO", "item23": 0.0}}
    ext = gx.gerar(liq, ch, FICHAS, "2026-11-09", [])
    assert ext["versao"] == 2 and ext["total_item23"] == 100.0 and ext["ne"][0]["nivel"] == "SIASG"
    assert all("descricao" not in x and "favorecido" not in x for x in ext["ne"])
    ch["160329000012026NE000001"]["item23"] = 90.0
    try:
        gx.gerar(liq, ch, FICHAS, "2026-11-09", [])
    except ValueError as e:
        assert "item 23" in str(e)
    else:
        raise AssertionError("deveria abortar com liquido diferente do item 23")


def test_b1_liquido_anuladas_fora_da_contagem_e_apoio():
    ext = {"versao": 2, "base": "liquido_6229201", "regra_vinculo": "2.0", "data_execucao": "2026-11-09", "ne": [
        {"documento": "A", "ug": "160329", "data": "10/03/2026", "valor": 100.0, "valor_emitido": 120.0, "nivel": "SIASG",
         "pregao": "PE 90009/2025", "candidatos": ["PE 90009/2025"]},
        {"documento": "B", "ug": "167329", "data": "11/03/2026", "valor": 0.0, "valor_emitido": 80.0, "nivel": "SIASG",
         "pregao": "PE 90009/2025", "candidatos": ["PE 90009/2025"]},
        {"documento": "C", "ug": "160238", "data": "12/04/2026", "valor": 30.0, "valor_emitido": 30.0, "nivel": None}]}
    regs, vin = gp.ler_extrato(ext)
    assert gp.base_do_extrato(ext) == "liquido"
    b1 = gp.bloco_b1(regs, "2026-11-09", "liquido", vin)
    assert b1["total"] == 130.0 and b1["ne"] == 2 and b1["base"] == "liquido"
    assert b1["apoio"] == {"emissao_bruta": 230.0, "ne_emitidas": 3, "ne_anuladas": 1, "nota": b1["apoio"]["nota"]}
    assert b1["vinculo_gcalc"]["pregoes"] == [{"pregao": "PE 90009/2025", "ne": 1, "valor": 100.0}]
    assert "LÍQUIDO" in b1["fonte"] and "líquido" in b1["rotulo_total"]
    json.dumps(b1)


def test_extrato_v1_declara_emissao_bruta():
    ext = {"versao": 1, "data_execucao": "2026-11-06", "ne": [
        {"documento": "A", "ug": "160329", "data": "10/03/2026", "valor": 100.0, "nivel": None}]}
    regs, _ = gp.ler_extrato(ext)
    b1 = gp.bloco_b1(regs, "2026-11-06", gp.base_do_extrato(ext))
    assert b1["base"] == "emissao" and "EMISSÃO BRUTA" in b1["fonte"] and "apoio" not in b1
