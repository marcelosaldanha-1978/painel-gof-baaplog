# -*- coding: utf-8 -*-
"""Testes do formato documento da régua (P-016 do PAINEL GOF DF): crédito por célula sem NC + «NC recebidas documento».
Dados sintéticos, sem pessoa; usa a UG 160321 do config padrão."""
import datetime as dt

import gof_regua_tg as R

REGUA = ('Titulo\n\n"Item Informação","","15","16","19","23","24","25","26","28","43","45","47","48"\n'
         '"","","PROV","CONC","DISP","EMP","ALIQ","LIQ","LAP","PAGO","RA","RL","RP","RB"\n'
         '"UG Executora","","S","S","S","S","S","S","S","S","S","S","S","S"\n'
         '"160321","ECT","1.000,00","","200,00","800,00","300,00","500,00","","500,00","","","",""\n')

# crédito por célula como o da DF: «UG Responsável» numa linha de cabeçalho abaixo de «Item Informação»
CELULA = ('T\n\n' + "\t".join(['"UG Executora"', '""', '"Natureza Despesa"', '""', '"PI"', '""', '"Item Informação"', '""',
                                '"15"', '"19"', '"23"']) + "\n"
          + "\t".join(['""'] * 8 + ['"PROV"', '"DISP"', '"EMP"']) + "\n"
          + "\t".join(['""'] * 6 + ['"UG Responsável"', '""', '"S"', '"S"', '"S"']) + "\n"
          + "\t".join(['"160321"', '"ECT"', '"339000"', '"APLIC"', '"PI1"', '"X"', '"160504"', '"COEX"', '"1.000,00"', '"200,00"', '"800,00"']) + "\n")

CAB_DOC = ['"NC"', '"NC - Dia Emissão"', '"Emitente - UG"', '""', '"NC Item - Favorecido"', '""', '"NC - Operação (Tipo)"',
           '"NC Item - Tipo Operação"', '"NC Item"', '"NC Célula - Tipo"', '"NC Célula - Fonte Recurso De"', '""',
           '"NC Célula - Natureza Despesa"', '""', '"NC Célula - Plano Interno"', '""', '"NC Célula - UG Responsável"', '""',
           '"NC Célula - Valor"', '"NC - Descrição"']


def linha_doc(nc, dia, op, nd, valor, desc):
    return "\t".join(['"%s"' % nc, '"%s"' % dia, '"160504"', '"COEX"', '"160321"', '"ECT"', '"%s"' % op, '"INCLUSAO"', '"1"',
                      '"DESTINO"', '"1000000000"', '"LIVRES"', '"%s"' % nd, '"ND"', '"PI1"', '"PI"', '"160504"', '"COEX"',
                      '"%s"' % valor, '"%s"' % desc]) + "\n"


DOC = ('T\n\n' + "\t".join(CAB_DOC) + "\n"
       + linha_doc("160504000012026NC420162", "10/11/2026", "DESCENTRALIZACAO DE CREDITO", "339039", "150,00", "EMPENHO IMEDIATO")
       + linha_doc("160504000012026NC420999", "20/11/2026", "DESCENTRALIZACAO DE CREDITO", "339030", "100,00", "PRAZO DE EMPENHO 30 DEZ 26")
       + linha_doc("160504000012026NC421000", "21/11/2026", "ANULACAO DE DESCENTRALIZACAO DE CREDITO", "339030", "50,00",
                   "ANULACAO PARCIAL DA 2026NC420999"))


def test_documento_vira_tabela_com_sinal_da_anulacao():
    t = R._tabela_nc(DOC.encode("cp1252"), "15")
    assert [g["valor"] for g in t] == [150.0, 100.0, -50.0]
    assert t[0]["UG Executora"] == "160321" and t[0]["PI"] == "PI1" and t[0]["UG Responsável"] == "160504"


def test_celula_le_a_ugr_da_linha_de_baixo():
    t = R._tabela_nc(CELULA.encode("cp1252"), "19")
    assert len(t) == 1 and t[0]["valor"] == 200.0 and t[0]["UG Responsável"] == "160504"


def test_calcular_formato_documento_liga_nc_pelo_endereco():
    # célula de R$ 200 na ND genérica 339000; NC vencida de 150 (339039) e NC no prazo de 100 - 50 anulados (339030),
    # todas no grupo 3390 do mesmo PI e UGR
    out = R.calcular(REGUA.encode("utf-16"), CELULA.encode("cp1252"), DOC.encode("cp1252"), dt.date(2026, 11, 23))
    u = out["por_omds"]["ECT"]["por_ug"]["160321"]
    assert u["celulas_em_tela"] == 200.0
    assert u["vencido_piso"] == 150.0 and u["vencido_teto"] == 150.0
    assert out["recolhido_no_ano"] == {"ncs": 1, "valor": 50.0}
    assert out["_formato"] == "documento"


def test_sem_documento_nada_muda():
    mov = 'T\n\n' + "\t".join(['"Emitente - UG"', '""', '"UG Executora"', '""', '"NC"', '"15"']) + "\n"
    out = R.calcular(REGUA.encode("utf-16"), CELULA.encode("cp1252"), mov.encode("cp1252"), dt.date(2026, 11, 23))
    u = out["por_omds"]["ECT"]["por_ug"]["160321"]
    assert u["vencido_piso"] == 0.0 and "_formato" not in out
