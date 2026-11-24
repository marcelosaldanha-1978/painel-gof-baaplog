# -*- coding: utf-8 -*-
"""Testes do bloco rp_por_ano (motor/gof_rp_por_ano.py) com dados FICTÍCIOS, sem pessoa (UG do config de referência)."""
import gof_rp_por_ano as R
import pytest

CAB = ('Titulo FICTICIO\n\nFiltro do relatório:\n(Conta = "531110100"; ...)\n\n'
       '"UG Executora"\t\t"NE CCor"\t"Conta Contábil"\t"531110100"\t"531210000"\t"631100000"\t"631300000"\t"631400000"'
       '\t"631510000"\t"631980000"\n'
       ' \t\t \t \t"= INSCRITOS"\t"= REINSCRICAO"\t"= A LIQUIDAR"\t"= LIQ A PAGAR"\t"= PAGO"\t"= BLOQ"\t"= CANC"\n'
       ' \t\t \t"NE - Dia Emissão"\t"Movim. Líquido"\t"Movim. Líquido"\t"Movim. Líquido"\t"Movim. Líquido"\t"Movim. Líquido"'
       '\t"Movim. Líquido"\t"Movim. Líquido"\n')
# 160321 (ECT): NE 2025 inscrita 1.000,00 (600 pago, 400 a liquidar); NE 2023 reinscrita 500 (200 cancelado, 300 bloq.)
# 167321 (ECT): NE 2024 reinscrita 100 (100 a liquidar), com um estorno «(1959.88)» compensado na mesma NE
LINHAS = ('"160321"\t"ECT"\t"160321000012025NE000001"\t"NAO SE APLICA"\t"1.000,00"\t""\t"400,00"\t"0,00"\t"600,00"\t""\t""\n'
          '"160321"\t"ECT"\t"160321000012023NE000009"\t"NAO SE APLICA"\t""\t"500,00"\t"0,00"\t""\t""\t"300,00"\t"200,00"\n'
          '"167321"\t"ECT"\t"167321000012024NE000002"\t"NAO SE APLICA"\t""\t"2.059,88"\t"100,00"\t"1959.88"\t""\t""\t""\n'
          '"167321"\t"ECT"\t"167321000012024NE000002"\t"10/01/2024"\t""\t""\t""\t"(1959.88)"\t"1959.88"\t""\t""\n')
REGUA = {"data_dado": "2026-11-23",
         "por_omds": {"ECT": {"por_ug": {"160321": {"rpnp_a_liquidar": 400.0}, "167321": {"rpnp_a_liquidar": 100.0}}}}}


def csv(cab=CAB, linhas=LINHAS, enc="cp1252"):
    return (cab + linhas).encode(enc)


def test_numeros_ptbr_e_parenteses():
    assert R.num("1.060,78") == 1060.78
    assert R.num("(1959.88)") == -1959.88
    assert R.num("1959.88") == 1959.88
    assert R.num("") == 0.0 and R.num("-10,00") == -10.0


def test_ler_agrega_por_ne_e_ano():
    ls, avisos = R.ler(csv())
    por = {x["ne"]: x for x in ls}
    assert len(por) == 3 and avisos == {}
    x = por["167321000012024NE000002"]
    assert x["ano"] == 2024 and round(x["contas"]["631300000"], 2) == 0.0 and x["contas"]["631400000"] == 1959.88


def test_utf16_e_coluna_ausente_vale_zero():
    ls, _ = R.ler(csv(enc="utf-16"))
    assert all(R.classificar(x["contas"])["excetuado"] == 0.0 for x in ls)


def test_agregacao_indice_datas_e_alerta():
    res = R.agregar(R.ler(csv())[0], exercicio=2026)
    u = {(x["ug"], x["ano"]): x for x in res["por_ug"]}
    a = u[("160321", 2025)]
    assert (a["inscrito"], a["liquidado"], a["a_liquidar"], a["indice"]) == (1000.0, 600.0, 400.0, 60.0)
    b = u[("160321", 2023)]
    assert (b["cancelado"], b["bloqueado"], b["indice"]) == (200.0, 300.0, 40.0)
    assert b["bloqueio"] == "2025-06-30" and b["cancelamento"] == "2026-12-31"
    tot = next(x for x in res["por_omds"] if x["omds"] == "ECT" and x["ano"] == "total")
    assert tot["inscrito"] == 3559.88 and tot["a_liquidar"] == 500.0
    al = [x for x in res["alertas"] if x["evento"] == "cancelamento"]
    assert [(x["ug"], x["ano"], x["saldo"]) for x in al] == [("160321", 2023, 300.0)]
    assert res["nao_fecham"] == []


def test_excetuado_nao_entra_no_alerta():
    cab = CAB.replace('"631980000"\n', '"631980000"\t"631810000"\n', 1)
    linha = '"160321"\t"ECT"\t"160321000012022NE000003"\t"NAO SE APLICA"\t""\t"700,00"\t""\t""\t""\t""\t""\t"700,00"\n'
    res = R.agregar(R.ler(csv(cab=cab, linhas=linha))[0], exercicio=2026)
    assert res["por_ug"][0]["excetuado"] == 700.0 and res["alertas"] == []


def test_portao_p_rp_1_passa_e_reprova_por_um_centavo():
    r = R.calcular(csv(), REGUA, "2026-11-23")
    assert r["nes"] == 3 and "por_ug" in r and "nao_fecham" not in r
    ruim = {"data_dado": "2026-11-23",
            "por_omds": {"ECT": {"por_ug": {"160321": {"rpnp_a_liquidar": 400.01}, "167321": {"rpnp_a_liquidar": 100.0}}}}}
    with pytest.raises(ValueError, match="P-RP-1"):
        R.calcular(csv(), ruim, "2026-11-23")


def test_portao_p_rp_3_regua_de_outro_dia():
    with pytest.raises(ValueError, match="mesmo dia"):
        R.calcular(csv(), dict(REGUA, data_dado="2026-11-20"), "2026-11-23")


def test_portao_p_rp_4_favorecido_recusado():
    cab = CAB.replace('"NE CCor"\t', '"NE CCor"\t"NE CCor - Favorecido"\t', 1)
    linha = '"160321"\t"ECT"\t"160321000012025NE000001"\t"EMPRESA FICTICIA"\t"NAO SE APLICA"\t"1,00"\t""\t"1,00"\t""\t""\t""\t""\n'
    with pytest.raises(ValueError, match="P-RP-4"):
        R.ler(csv(cab=cab, linhas=linha))
    ls, _ = R.ler(csv(cab=cab, linhas=linha), permitir_favorecido=True)  # só a conferência local
    assert "EMPRESA FICTICIA" not in repr(ls)


def test_portao_p_rp_5_ne_que_nao_fecha():
    linha = '"160321"\t"ECT"\t"160321000012025NE000001"\t"NAO SE APLICA"\t"1.000,00"\t""\t"399,99"\t""\t"600,00"\t""\t""\n'
    reg = {"data_dado": "2026-11-23", "por_omds": {"ECT": {"por_ug": {"160321": {"rpnp_a_liquidar": 399.99}}}}}
    with pytest.raises(ValueError, match="P-RP-5"):
        R.calcular(csv(linhas=linha), reg, "2026-11-23")


def test_conta_desconhecida_e_ne_de_outra_ug():
    with pytest.raises(ValueError, match="sem papel"):
        R.ler(csv(cab=CAB.replace('"631980000"', '"639990000"', 1)))
    linha = '"160321"\t"ECT"\t"160329000012025NE000001"\t"NAO SE APLICA"\t"1,00"\t""\t"1,00"\t""\t""\t""\t""\n'
    with pytest.raises(ValueError, match="na linha da UG"):
        R.ler(csv(linhas=linha))


def test_linha_sem_ne_com_valor_e_acusada():
    linha = LINHAS + '"160321"\t"ECT"\t"-9"\t"NAO SE APLICA"\t"5,00"\t""\t"5,00"\t""\t""\t""\t""\n'
    _, avisos = R.ler(csv(linhas=linha))
    assert avisos == {"linhas sem NE válida (com valor)": 1}


def test_escolher_arquivo_mais_recente():
    nomes = ["2026-11-24_rpnp_por_ne.csv", "2026-11-25_rpnp_por_ne.zip", "2026-11-26_regua_por_ug.csv", "x.csv"]
    assert R.escolher(nomes) == "2026-11-25" and R.escolher(["x"]) is None


def test_linha_total_do_tg_e_conferida_e_nao_somada():
    total = '"160321"\t"ECT"\t"Total"\t""\t"1.000,00"\t"500,00"\t"400,00"\t"0,00"\t"600,00"\t"300,00"\t"200,00"\n'
    ls, avisos = R.ler(csv(linhas=LINHAS + total))
    assert avisos == {} and len(ls) == 3
    ruim = total.replace('"200,00"', '"200,01"')
    with pytest.raises(ValueError, match="Total"):
        R.ler(csv(linhas=LINHAS + ruim))
