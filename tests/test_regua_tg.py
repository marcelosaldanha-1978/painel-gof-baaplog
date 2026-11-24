# -*- coding: utf-8 -*-
"""Testes da régua diária (motor/gof_regua_tg.py) com dados sintéticos, sem pessoa."""
import datetime as dt

import gof_regua_tg as R


def utf16(txt):
    return txt.encode("utf-16")


REGUA = ('Titulo\n\n"Item Informação","","15","16","19","23","24","25","26","28","43","45","47","48"\n'
         '"","","PROV","CONC","DISP","EMP","ALIQ","LIQ","LAP","PAGO","RA","RL","RP","RB"\n'
         '"UG Executora","","S","S","S","S","S","S","S","S","S","S","S","S"\n'
         '"160321","ECT","1.000,00","","200,00","800,00","300,00","500,00","","500,00","50,00","","","10,00"\n'
         '"167321","ECT","100,00","","","100,00","","100,00","","100,00","","","",""\n')


def test_regua_por_ug_e_linha():
    reg = R.regua_por_ug(utf16(REGUA))
    x = R.linha_regua(reg["160321"])
    assert x["provisao"] == 1000.0 and x["em_tela"] == 200.0 and x["pct_empenhado"] == 80.0
    assert x["rpnp_a_liquidar"] == 50.0 and x["rpnp_bloqueado"] == 10.0
    assert "167321" in reg


def test_prazo_escrito_na_nc():
    rec = dt.date(2026, 11, 11)
    assert R.prazo("ATENDE ... PRAZO DE EMPENHO 27 FEV 26.", rec) == dt.date(2026, 2, 27)
    assert R.prazo("EMPENHO IMEDIATO", rec) == dt.date(2026, 11, 12)
    assert R.prazo("sem prazo nenhum", rec) is None


def test_separador_nao_se_engana_com_virgula_do_filtro():
    txt = "Titulo\nFiltro: (UG = 160321, 167321, 160238)\n" + "\t".join(['"a"', '"b"', '"c"', '"d"']) + "\n"
    assert R.linhas(txt.encode("cp1252"))[2] == ["a", "b", "c", "d"]


def test_escolher_trio():
    n = ["2026-11-23_regua_por_ug.csv", "2026-11-23_credito_por_nc.csv", "2026-11-23_credito_movimento.csv",
         "2026-11-24_regua_por_ug.csv"]
    assert R.escolher_trio(n) == "2026-11-23"
    assert R.escolher_trio(n[:2]) is None


def test_calcular_vencido_piso_e_teto():
    # uma célula da ECT com R$ 200 em tela, coberta por uma NC vencida de R$ 150 e uma no prazo de R$ 50
    cred = ('T\n\n' + "\t".join(['"Emitente - UG"', '""', '"UG Executora"', '""', '"NC"', '"Ação Governo"', '"PI"', '""',
                                  '"Natureza Despesa"', '""', '"NC - Descrição"', '"NC - Operação (Tipo)"', '"NC - Dia Emissão"', '"19"']) + "\n" +
            "\t".join(['"160504"', '"COEX"', '"160321"', '"ECT"', '"160504000012026NC420162"', '"21A0"', '"PI1"', '""', '"339039"', '""',
                       '"EMPENHO IMEDIATO"', '"DESC"', '"10/11/2026"', '"150,00"']) + "\n" +
            "\t".join(['"160504"', '"COEX"', '"160321"', '"ECT"', '"160504000012026NC420999"', '"21A0"', '"PI1"', '""', '"339039"', '""',
                       '"PRAZO DE EMPENHO 30 DEZ 26"', '"DESC"', '"20/11/2026"', '"50,00"']) + "\n")
    mov = ('T\n\n' + "\t".join(['"Emitente - UG"', '""', '"UG Executora"', '""', '"NC"', '"NC - Descrição"', '"NC - Operação (Tipo)"',
                                 '"NC - Dia Emissão"', '"15"']) + "\n")
    regua_so_ect = REGUA.replace('"167321","ECT","100,00","","","100,00","","100,00","","100,00","","","",""\n', "")
    out = R.calcular(utf16(regua_so_ect), cred.encode("cp1252"), mov.encode("cp1252"), dt.date(2026, 11, 23))
    u = out["por_omds"]["ECT"]["por_ug"]["160321"]
    assert u["celulas_em_tela"] == 200.0
    assert u["vencido_piso"] == 150.0 and u["vencido_teto"] == 150.0
    assert out["por_omds"]["ECT"]["semaforo"] == "VERDE"


def test_trava_celulas_nao_fecham_com_a_regua():
    import pytest
    cred = ('T\n\n' + "\t".join(['"Emitente - UG"', '""', '"UG Executora"', '""', '"NC"', '"NC - Descrição"', '"NC - Dia Emissão"', '"19"']) + "\n"
            + "\t".join(['"160504"', '"X"', '"160321"', '"ECT"', '"160504000012026NC000001"', '"EMPENHO IMEDIATO"', '"10/11/2026"', '"10,00"']) + "\n")
    mov = 'T\n\n' + "\t".join(['"Emitente - UG"', '""', '"UG Executora"', '""', '"NC"', '"15"']) + "\n"
    with pytest.raises(ValueError, match="não fecham"):
        R.calcular(utf16(REGUA), cred.encode("cp1252"), mov.encode("cp1252"), dt.date(2026, 11, 23))


def test_escolher_trio_com_zip():
    n = ["2026-11-23_regua_por_ug.csv", "2026-11-23_credito_por_nc.zip", "2026-11-23_credito_movimento.csv"]
    assert R.escolher_trio(n) == "2026-11-23"
