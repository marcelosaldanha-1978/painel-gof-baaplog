# -*- coding: utf-8 -*-
"""Testes da ponte do TG (motor/gof_ponte_tg.py) com dados sintéticos, sem pessoa."""
import datetime as dt

import gof_ponte_tg as pt
import pytest

NE1 = "160238000012026NE000003"
NE2 = "160238000012026NE000004"


def emissao(*linhas):
    cab = "UG\tnome\tNE\tdia\t522920101\t522920102\t522920104\t622920101\t622920102\t622920103\t622920104\n"
    return cab + "".join("\t".join(f'"{c}"' for c in ln) + "\n" for ln in linhas)


def info(*linhas):
    return "".join("\t".join(f'"{c}"' for c in ln) + "\n" for ln in linhas)


def ln_info(ne, item23, chave="16023806000942026 - UASG MINUTA: 160238"):
    return ["2026", "160238", "BASE", "06", "DISPENSA", ne, chave, "descricao", item23, item23]


def test_agrega_varias_linhas_por_ne():
    # mesma NE: linha do dia de emissao + linha «NAO SE APLICA» que move a liquidar -> pago
    e = emissao(["160238", "BASE", NE1, "29/01/2026", "3.596,23", "", "", "3.596,23", "", "", ""],
                ["160238", "BASE", NE1, "NAO SE APLICA", "", "", "", "(3.596,23)", "0,00", "0,00", "3.596,23"])
    ag = pt.agregar_emissao(e)
    assert ag[NE1]["dia"] == "29/01/2026"
    assert ag[NE1]["liq"] == 3596.23
    assert ag[NE1]["e101"] == 3596.23


def test_anulacao_entra_negativa():
    e = emissao(["160238", "BASE", NE1, "29/01/2026", "3.300,00", "", "(3.300,00)", "0,00", "", "", ""])
    assert pt.agregar_emissao(e)[NE1]["e104"] == -3300.0


def test_montar_entradas_formato_do_gerador():
    e = emissao(["160238", "BASE", NE1, "29/01/2026", "1.000,00", "", "", "1.000,00", "", "", ""])
    liq, cha = pt.montar_entradas(e, info(ln_info(NE1, "1.000,00")))
    # o gerador usa num(): o valor tem de vir com virgula decimal
    assert pt.num(liq[NE1]["empenhado_liquido_6229201"]) == 1000.0
    assert liq[NE1]["modalidade"] == "06"
    assert cha[NE1]["item23"] == 1000.0


def test_ne_com_liquido_sem_informacao_aborta():
    e = emissao(["160238", "BASE", NE1, "29/01/2026", "10,00", "", "", "10,00", "", "", ""],
                ["160238", "BASE", NE2, "29/01/2026", "5,00", "", "", "5,00", "", "", ""])
    with pytest.raises(ValueError, match="sem informação complementar"):
        pt.montar_entradas(e, info(ln_info(NE1, "10,00")))


def test_ne_sem_dia_de_emissao_aborta():
    e = emissao(["160238", "BASE", NE1, "NAO SE APLICA", "", "", "", "10,00", "", "", ""])
    with pytest.raises(ValueError, match="sem dia"):
        pt.agregar_emissao(e)


def test_arquivo_vazio_aborta():
    with pytest.raises(ValueError, match="vazio"):
        pt.montar_entradas(emissao(), info())


def test_escolher_par_mais_recente_completo():
    nomes = ["2026-11-20_emissao_sem_pessoa.tsv", "2026-11-20_info_complementar.tsv",
             "2026-11-24_emissao_sem_pessoa.tsv",  # par incompleto: ignorado
             "outro.txt"]
    assert pt.escolher_par(nomes) == "2026-11-20"
    assert pt.escolher_par(["x.tsv"]) is None


def test_dia_util_anterior():
    assert pt.dia_util_anterior(dt.date(2026, 11, 20)) == dt.date(2026, 11, 19)  # sexta -> quinta
    assert pt.dia_util_anterior(dt.date(2026, 11, 23)) == dt.date(2026, 11, 20)  # segunda -> sexta


def test_extrato_sem_fichas_para_om_sem_carteira_gcalc():
    # v2.3 (P-012 do PAINEL GOF DF): OM sem o bloco carteira_gcalc chama a ponte sem --fichas; nenhuma NE vira pregão
    import gof_extrato_tg as ext

    e = emissao(["160238", "BASE", NE1, "29/01/2026", "1.000,00", "", "", "1.000,00", "", "", ""])
    liq, cha = pt.montar_entradas(e, info(ln_info(NE1, "1.000,00")))
    extrato = ext.gerar(liq, cha, [], "2026-11-23", [])
    assert extrato["total_item23"] == 1000.0
    assert [n["pregao"] for n in extrato["ne"]] == [None]
