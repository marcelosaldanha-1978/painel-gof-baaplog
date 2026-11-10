# -*- coding: utf-8 -*-
"""Saldo de ata por item: registrado (API) × valor unitário − empenhado pelo TG; nunca negativo; excesso sinalizado."""
import json

from motor import gof_capacidade_saldo as s


def _cap(tmp_path, itens):
    p = tmp_path / "coleta.json"
    p.write_text(json.dumps({"hoje": "2026-11-10", "itens": itens}), encoding="utf-8")
    return p


def _item(**k):
    base = {"omds": "1º D Sup", "uasg": "160307", "gerenciadora": "160307", "compra": "90005/2025", "item": "00001",
            "cnpj": "11111111000111", "tipo_unidade": "GERENCIADORA", "quantidade_registrada_unidade": 10.0,
            "valor_unitario": 100.0, "saldo_valor": 1000.0, "vigencia_fim": "2027-03-01"}
    base.update(k)
    return base


def test_saldo_desconta_empenho_do_tg(tmp_path):
    emp = tmp_path / "emp.json"
    emp.write_text(json.dumps({"empenhado": [[["160307", "160307", "90005/2025", "00001", "11111111000111"], 300.0]]}),
                   encoding="utf-8")
    out = tmp_path / "out.json"
    s.main(["--capacidade", str(_cap(tmp_path, [_item()])), "--empenhado", str(emp), "--saida", str(out)])
    d = json.loads(out.read_text(encoding="utf-8"))
    x = d["itens"][0]
    assert x["registrado_valor"] == 1000.0
    assert x["empenhado_tg"] == 300.0
    assert x["saldo_proprio"] == 700.0
    assert d["saldo"]["resumo"]["1º D Sup"]["saldo_proprio"] == 700.0


def test_saldo_nunca_negativo_e_excesso_sinalizado(tmp_path):
    emp = tmp_path / "emp.json"
    emp.write_text(json.dumps({"empenhado": [[["160307", "160307", "90005/2025", "00001", "11111111000111"], 1500.0]]}),
                   encoding="utf-8")
    out = tmp_path / "out.json"
    s.main(["--capacidade", str(_cap(tmp_path, [_item()])), "--empenhado", str(emp), "--saida", str(out)])
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["itens"][0]["saldo_proprio"] == 0.0
    assert len(d["saldo"]["empenho_acima_do_registrado"]) == 1


def test_empenho_de_outra_uasg_nao_desconta(tmp_path):
    emp = tmp_path / "emp.json"
    emp.write_text(json.dumps({"empenhado": [[["160329", "160307", "90005/2025", "00001", "11111111000111"], 300.0]]}),
                   encoding="utf-8")
    out = tmp_path / "out.json"
    s.main(["--capacidade", str(_cap(tmp_path, [_item()])), "--empenhado", str(emp), "--saida", str(out)])
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["itens"][0]["saldo_proprio"] == 1000.0
    assert d["saldo"]["empenhado_fora_da_coleta"]["itens"] == 1
