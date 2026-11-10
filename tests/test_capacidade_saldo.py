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


def test_item_por_valor_e_separado(tmp_path):
    emp = tmp_path / "emp.json"
    emp.write_text(json.dumps({"empenhado": []}), encoding="utf-8")
    out = tmp_path / "out.json"
    itens = [_item(), _item(item="00002", valor_unitario=1.0, quantidade_registrada_unidade=50000.0, saldo_valor=50000.0)]
    s.main(["--capacidade", str(_cap(tmp_path, itens)), "--empenhado", str(emp), "--saida", str(out)])
    r = json.loads(out.read_text(encoding="utf-8"))["saldo"]["resumo"]["1º D Sup"]
    assert r["saldo_por_natureza"] == {"POR_QUANTIDADE": 1000.0, "POR_VALOR": 50000.0}
    assert r["maiores_itens"][0]["natureza"] == "POR_VALOR"
    assert r["concentracao_5_maiores"] == 51000.0


def test_fora_da_coleta_e_classificado(tmp_path):
    emp = tmp_path / "emp.json"
    emp.write_text(json.dumps({"empenhado": [
        [["160307", "160307", "90005/2025", "00009", "22222222000122"], 10.0],   # mesma compra, item fora
        [["160307", "160307", "90001/2024", "00001", "22222222000122"], 20.0],   # própria sem ata vigente
        [["160307", "160069", "00018/2023", "00001", "22222222000122"], 30.0],   # terceiro sem ata vigente
        [["160307", "160307", "90002/2023", "00001", "22222222000122"], 40.0],   # contrato ativo
    ]}), encoding="utf-8")
    p = tmp_path / "coleta.json"
    p.write_text(json.dumps({"hoje": "2026-11-10", "itens": [_item()],
                             "contratos": {"160307": [{"unidade_compra": "160307", "licitacao": "90002/2023"}]}}),
                 encoding="utf-8")
    out = tmp_path / "out.json"
    s.main(["--capacidade", str(p), "--empenhado", str(emp), "--saida", str(out)])
    f = json.loads(out.read_text(encoding="utf-8"))["saldo"]["empenhado_fora_da_coleta"]
    assert f["valor"] == 100.0
    assert {k: v["valor"] for k, v in f["por_classe"].items()} == {
        "MESMA_COMPRA_ITEM_FORA": 10.0, "COMPRA_PROPRIA_SEM_ATA_VIGENTE": 20.0,
        "COMPRA_DE_TERCEIRO_SEM_ATA_VIGENTE": 30.0, "CONTRATO_ATIVO": 40.0}
