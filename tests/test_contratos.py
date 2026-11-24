# -*- coding: utf-8 -*-
"""Testes do bloco contratos mínimo (motor/gof_contratos.py) com registros FICTÍCIOS da API, sem pessoa."""
import datetime as dt
import json

import gof_contratos as C
import pytest

HOJE = dt.date(2026, 11, 24)


def reg(numero, fim, situacao="Ativo", rd="Despesa", valor="1.000,00", forn="EMPRESA FICTICIA LTDA"):
    return {"numero": numero, "tipo": "Contrato", "objeto": "OBJETO FICTICIO " * 30, "receita_despesa": rd,
            "situacao": situacao, "vigencia_inicio": "2025-01-01", "vigencia_fim": fim, "valor_global": valor,
            "fornecedor": {"nome": forn, "cnpj_cpf_idgener": "00.000.000/0001-00"}, "links": {"empenhos": "x"}}


def test_vigente_pela_data_e_nao_pela_situacao():
    lista = [reg("1/2025", "2026-11-23"),                      # ativo, mas vencido ontem: fora
             reg("2/2025", "2026-11-24", situacao="Inativo"),  # inativo na API, mas vigente hoje: dentro
             reg("3/2025", "2027-12-31"), reg("4/2025", "2027-01-01", rd="Receita"), reg("5/2025", "")]
    cs = C.vigentes(lista, HOJE)
    assert [c["numero"] for c in cs] == ["2/2025", "3/2025"]
    assert cs[0]["dias_para_vencer"] == 0 and cs[0]["faixa"] == "até 90 dias"


def test_faixas_teto_e_objeto_curto():
    cs = C.vigentes([reg("9/2024", "2027-05-24", valor="288.914.869,54")], HOJE)
    assert cs[0]["faixa"] == "181 a 365 dias" and cs[0]["valor_global_teto"] == 288914869.54
    assert len(cs[0]["objeto"]) == 200
    assert [C.faixa(d) for d in (90, 91, 180, 181, 365, 366)] == [
        "até 90 dias", "91 a 180 dias", "91 a 180 dias", "181 a 365 dias", "181 a 365 dias", "mais de 365 dias"]


def test_sem_fornecedor_cnpj_nem_empenhado_na_saida():
    r = C.montar(HOJE, ler=lambda ug: [reg("3/2025", "2027-12-31")])
    s = json.dumps(r, ensure_ascii=False)
    assert "EMPRESA FICTICIA" not in s and "0001-00" not in s
    chaves = {k for x in r["por_omds"] for c in x["contratos"] for k in c}
    assert not chaves & {"fornecedor", "cnpj", "empenhado", "empenhado_ano", "links"}


def test_api_fora_numa_omds_vira_ressalva():
    def ler(ug):
        if ug == "160321":
            raise RuntimeError("falha em ...: HTTP 503")
        return [reg("3/2025", "2027-06-01")]

    r = C.montar(HOJE, ler=ler)
    ect = next(x for x in r["por_omds"] if x["ug"] == "160321")
    assert ect["indisponivel"] and ect["contratos"] == [] and len(r["ressalvas"]) == 1
    outra = next(x for x in r["por_omds"] if x["ug"] != "160321")
    assert outra["quantidade"] == 1 and outra["vencem_90"] == 0 and outra["vencem_365"] == 1


def test_api_fora_em_todas_nao_escreve():
    def ler(ug):
        raise RuntimeError("fora")

    with pytest.raises(RuntimeError, match="todas"):
        C.montar(HOJE, ler=ler)
