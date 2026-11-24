# -*- coding: utf-8 -*-
"""v2.4: blocos opcionais rp_por_ano e contratos na página, no portão 0 e no recálculo (dados FICTÍCIOS, sem pessoa)."""
import gof_painel as gp
import recalculo_independente as ri


def rp(aliq=400.0):
    ug = [{"omds": "ECT", "ug": "160321", "ano": 2025, "inscrito": 1000.0, "liquidado": 600.0, "cancelado": 0.0,
           "a_liquidar": aliq, "em_liquidacao": 0.0, "bloqueado": 0.0, "excetuado": 0.0, "a_classificar": 0.0, "indice": 60.0,
           "bloqueio": "2027-06-30", "cancelamento": "2028-12-31"}]
    om = [dict(ug[0], ano=2025, rotulo="ECT"), dict(ug[0], ano="total", rotulo="ECT")]
    for x in om:
        x.pop("ug")
    return {"data_dado": "2026-11-23", "por_ug": ug, "por_omds": om, "alertas": []}


def test_sem_bloco_o_modelo_sai_intacto():
    h = gp.render_html({"meta": {}})
    assert "rpano" not in h and "Contratos vigentes" not in h


def test_com_bloco_a_pagina_ganha_as_secoes():
    h = gp.render_html({"meta": {}, "rp_por_ano": {"ausente": True, "ressalva": "x"}})
    assert 'sec("rpano"' in h and h.rstrip().endswith("</html>")
    assert h.count("<script") == h.count("</script>")


def test_recalculo_v24_confere_e_acusa():
    D = {"rp_por_ano": rp(), "regua": {"data_dado": "2026-11-23",
                                      "por_omds": {"ECT": {"por_ug": {"160321": {"rpnp_a_liquidar": 400.0}}}}}}
    assert ri.conferir_v24(D) == []
    D["regua"]["por_omds"]["ECT"]["por_ug"]["160321"]["rpnp_a_liquidar"] = 400.02
    assert any("régua" in f for f in ri.conferir_v24(D))
    D2 = {"rp_por_ano": rp()}
    D2["rp_por_ano"]["por_omds"][1]["inscrito"] = 999.0
    assert any("inscrito" in f for f in ri.conferir_v24(D2))


def test_recalculo_v24_contratos_sem_fornecedor():
    c = {"numero": "1/2025", "objeto": "X", "vigencia_fim": "2027-01-01", "dias_para_vencer": 38, "valor_global_teto": 10.0}
    o = {"omds": "ECT", "indisponivel": False, "contratos": [c], "quantidade": 1, "teto_total": 10.0,
         "vencem_90": 1, "vencem_180": 1, "vencem_365": 1}
    assert ri.conferir_v24({"contratos": {"por_omds": [o]}}) == []
    c["fornecedor"] = "EMPRESA FICTICIA"
    assert ri.conferir_v24({"contratos": {"por_omds": [o]}})
    assert ri.conferir_v24({"contratos": {"ausente": True}}) == []


# ---- auditoria independente de 24/11 (itens 9 e 12)
def test_texto_de_bloco_nao_casa_com_marcador_nem_abre_tag():
    import json
    import re

    obj = "__HASH__ __BRASOES__ <!--<script></script>"
    dados = {"meta": {}, "contratos": {"por_omds": [{"omds": "ECT", "contratos": [{"objeto": obj}]}]}}
    h = gp.render_html(dados)
    m = re.search(r'<script type="application/json" id="dados">(.*?)</script>', h, re.S)
    assert json.loads(m.group(1)) == dados and "<!--<script" not in m.group(1)


def test_recalculo_v24_acusa_documento_no_objeto():
    c = {"numero": "1/2025", "objeto": "CNPJ 00.000.000/0001-91", "vigencia_fim": "2027-01-01", "dias_para_vencer": 38,
         "valor_global_teto": 10.0}
    o = {"omds": "ECT", "indisponivel": False, "contratos": [c], "quantidade": 1, "teto_total": 10.0,
         "vencem_90": 1, "vencem_180": 1, "vencem_365": 1}
    assert any("CPF/CNPJ" in f for f in ri.conferir_v24({"contratos": {"por_omds": [o]}}))
