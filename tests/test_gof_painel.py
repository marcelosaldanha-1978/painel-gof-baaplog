# -*- coding: utf-8 -*-
"""
Testes do motor do painel GOF-BaApLog, fase A (gof_painel v0.1, 07/11/2026; PLANO v2.1, passo 7).

O que se trava aqui:
- B1 soma por OMDS com UG 160 e 167 separadas e ritmo mensal; NE repetida na entrada aborta;
- B3 le a aba Controle Processos pelo cabecalho e NAO leva contatos nem observacoes;
- B4: ata a vencer so ate 90 dias e nunca cancelada; NE a verificar sem favorecido nem texto;
- portao 3 e 4: o JSON embutido no HTML e identico ao dados.json e o hash do rodape e o do JSON canonico;
- dado embutido com "</script>" nao quebra a pagina;
- recalculo contra as evidencias reais (quando acessiveis): LOG-120 (3.032 NE, R$ 63.990.398,67) e Painel (R$ 19.117.236,67).
"""
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

import gcalc_transparencia as tr
import gof_painel as gp
import pytest

HOJE = dt.date(2026, 11, 7)


def _reg(doc_ug, n, valor, data, nome=None):
    return {"documento": "%s000012026NE%06d" % (doc_ug, n), "valor": valor, "data": data, "_ug": doc_ug,
            "_nome": nome or tr.UGS[doc_ug], "observacao": "texto", "favorecido": "FULANO DE TAL", "modalidade": "12",
            "codigoFavorecido": ""}


# ----------------------------------------------------------------- B1
def test_b1_soma_por_omds_com_160_e_167_separadas_e_ritmo_mensal():
    regs = [_reg("160321", 1, "1.000,00", "10/03/2026"), _reg("160321", 2, "500,50", "20/03/2026"),
            _reg("167321", 3, "99,50", "05/10/2026"), _reg("160246", 4, "10,00", "01/01/2026")]
    b1 = gp.bloco_b1(regs, "2026-11-06")
    ect = next(o for o in b1["omds"] if o["omds"] == "ECT")
    assert (ect["valor160"], ect["valor167"], ect["total"], ect["ne"]) == (1500.5, 99.5, 1600.0, 3)
    assert ect["por_mes"][2] == 1500.5 and ect["por_mes"][9] == 99.5
    assert b1["total"] == 1610.0 and b1["ne"] == 4
    assert {o["omds"] for o in b1["omds"]} == set(gp.OMDS)  # OMDS sem NE aparece com zero


def test_b1_ne_repetida_aborta():
    with pytest.raises(ValueError):
        gp.bloco_b1([_reg("160321", 1, "1,00", "10/03/2026")] * 2, "2026-11-06")


# ----------------------------------------------------------------- B3
def _carteira_csv(tmp_path, situacao="Ativo"):
    cab = [""] * 52
    for k, i in gp.COLS.items():
        cab[i] = k
    cab[1], cab[29], cab[51], cab[34] = "Nº Processo", "Valor Homologado (R$)", "Situação PNCP", "E-mail"
    lin = [""] * 52
    vals = {"ordem": "1", "processo": "PE 90009/2025", "objeto": "Obj", "ugg": "BCMS", "uasg": "160329",
            "estimado": "R$ 9.231.579,04", "homologado": "R$ 3.045.078,60", "prazo_meta": "30/01/2026",
            "status_prazo": "Atrasado", "fase": "Fase Externa", "pct_total": "70%", "proxima_acao": "Retomar",
            "ultima_atualizacao": "04/11/2026", "situacao_pncp": situacao,
            "link": "https://pncp.gov.br/app/editais/00394452000103/2025/025363"}
    for k, v in vals.items():
        lin[gp.COLS[k]] = v
    lin[34] = "salc@exemplo.mil.br"
    tot = ["TOTALIZADORES"] + [""] * 51
    import csv
    p = tmp_path / "c.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows([["titulo"] + [""] * 51, cab, lin, tot])
    return p


def test_b3_le_pelo_cabecalho_e_nao_leva_contato(tmp_path):
    procs = gp.ler_carteira(_carteira_csv(tmp_path))
    assert len(procs) == 1 and procs[0]["estimado"] == 9231579.04 and procs[0]["homologado"] == 3045078.6
    b3 = gp.bloco_b3(procs, {"score_bsc": "66,9%"})
    texto = json.dumps(b3, ensure_ascii=False)
    assert "@" not in texto and "link" not in b3["processos"][0]
    assert b3["resumo"]["atrasados"] == 1 and b3["data_dado"] == "2026-11-04"


def test_b3_cabecalho_diferente_falha_alto(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        gp.ler_carteira(p)


# ----------------------------------------------------------------- B4
def test_b4_atas_a_vencer_ate_90_dias_e_nunca_canceladas():
    atas = [{"processo": "A", "ata": "1/2026", "vigencia_fim": "2027-01-30", "cancelada": False},   # 84 dias
            {"processo": "A", "ata": "2/2026", "vigencia_fim": "2027-02-06", "cancelada": False},   # 91 dias
            {"processo": "A", "ata": "3/2026", "vigencia_fim": "2026-12-01", "cancelada": True}]
    b4 = gp.bloco_b4(atas, [], [], [], HOJE)
    assert [a["ata"] for a in b4["atas"]["a_vencer"]] == ["1/2026"]
    assert b4["atas"]["n_vigentes"] == 2 and b4["atas"]["proxima"]["dias"] == 84


def test_b4_ne_a_verificar_sem_favorecido_nem_texto():
    vin = [{"nivel": "AMBIGUO", "pregao": None, "candidatos": ["PE 1/2026", "PE 2/2026"], "documento": "D1",
            "data": "01/06/2026", "ug": "BCMS", "valor": "10,00", "favorecido": "FULANO", "observacao": "segredo"},
           {"nivel": "CONFIRMADO", "pregao": "PE 1/2026", "candidatos": ["PE 1/2026"], "documento": "D2",
            "data": "01/06/2026", "ug": "BCMS", "valor": "5,00", "favorecido": "X", "observacao": "y"}]
    nv = gp.bloco_b4([], [], vin, [], HOJE)["ne_verificar"]
    assert [x["documento"] for x in nv["lista"]] == ["D1"] and nv["contagem"]["AMBIGUO"]["BCMS"] == 1
    t = json.dumps(nv, ensure_ascii=False)
    assert "FULANO" not in t and "segredo" not in t


# ----------------------------------------------------------------- HTML (portao 3 e 4)
def _dados_min():
    regs = [_reg("160321", 1, "1.000,00", "10/03/2026")]
    return {"meta": {"versao_motor": gp.VERSAO_MOTOR, "regra_vinculo": tr.VERSAO_REGRA, "hoje": "2026-11-07", "fase": "A",
                     "fontes": [{"nome": "t", "arquivo": "a</script><b>.csv", "sha256": "0" * 64, "data_dado": "2026-11-06"}]},
            "b1": gp.bloco_b1(regs, "2026-11-06"), "b3": {"fonte": "f", "data_dado": "2026-11-04", "processos": [],
            "resumo": {"processos": 0, "estimado": 0, "homologado": 0, "concluidos": 0, "atrasados": 0, "suspensos": 0,
                       "nao_publicados": 0}, "kpis_painel": {}},
            "b4": gp.bloco_b4([], [], [], [], HOJE)}


def test_html_embute_o_mesmo_json_e_o_hash_do_rodape():
    dados = _dados_min()
    pagina = gp.render_html(dados)
    m = re.search(r'<script type="application/json" id="dados">(.*?)</script>', pagina, re.S)
    assert m, "bloco de dados nao encontrado (fechou o <script> antes da hora?)"
    embutido = json.loads(m.group(1).replace("<\\/", "</"))
    assert embutido == dados
    h = hashlib.sha256(gp.json_canonico(dados).encode("utf-8")).hexdigest()
    assert h in pagina and "__HASH__" not in pagina and "__DADOS__" not in pagina
    assert "http://" not in pagina and "https://" not in pagina  # nenhum pedido externo


# ----------------------------------------------------------------- recalculo contra as evidencias reais
EVID = Path(os.environ.get("GCALC_PROJETO_ONEDRIVE", r"C:\Users\marce\OneDrive\Documentos\claude\projects\GCALC BaApLog 2025_2026")) / "02_EVIDENCIAS_E_REGISTROS"


def test_fase_a_real_reproduz_log_120_e_o_painel():
    csvs = sorted(EVID.glob("TG_2026-11-06_PILOTO_*/*CSV_completo_ATRIBUTOS_NE_06nov2026.csv")) if EVID.exists() else []
    cart = EVID / "PAINEL_FASE_A_2026-11-07" / "carteira_controle_processos_2026-11-07.csv"
    if len(csvs) != 6 or not cart.exists():
        pytest.skip("evidencias do projeto nao acessiveis")
    b1 = gp.bloco_b1([r for c in csvs for r in tr.ler_csv_tg(c)], "2026-11-06")
    assert b1["ne"] == 3032 and b1["total"] == 63990398.67
    r = gp.bloco_b3(gp.ler_carteira(cart), {})["resumo"]
    assert (r["processos"], r["estimado"], r["homologado"]) == (12, 75312730.52, 19117236.67)


# ----------------------------------------------------------------- v0.2: extrato sem pessoa (o que roda na nuvem)
def test_extrato_sem_pessoa_reproduz_o_b1_e_o_vinculo():
    regs = [_reg("160321", 1, "1.234,56", "10/03/2026"), _reg("167321", 2, "10,00", "05/10/2026"),
            _reg("160246", 3, "1.000.000,01", "01/06/2026")]
    fichas = [{"pregao": "PE 90023/2025", "numero_pncp": "90023", "ano_pncp": "2025", "numeros_alternativos": [],
               "uasg": "160246", "fornecedores": {}, "fornecedores_nomes": {tr.norm_nome("FULANO DE TAL LTDA ME")},
               "atas": [], "primeira_assinatura": None, "homologado": 1.0}]
    regs[2]["observacao"] = "PREGAO 90023/2025 - AQUISICAO"
    ext = gp.gerar_extrato(regs, fichas, "2026-11-06", [])
    t = json.dumps(ext, ensure_ascii=False)
    assert "FULANO" not in t and "texto" not in t and "PREGAO 90023" not in t  # nem favorecido nem descricao
    regs2, vin2 = gp.ler_extrato(ext)
    assert gp.bloco_b1(regs2, "2026-11-06") == gp.bloco_b1(regs, "2026-11-06")
    assert [(v["documento"], v["nivel"]) for v in vin2] == [(v["documento"], v["nivel"]) for v in tr.vincular(regs, fichas)]


def test_formato_br_ida_e_volta():
    for v in (0.0, 0.01, 1234.56, 1000000.01, 63990398.67):
        assert tr._num(gp._br(v)) == v


def test_encerramento_conta_dias_uteis_sem_feriado_de_20nov():
    import datetime as dt

    from motor import gof_painel as g
    e = g.bloco_encerramento(dt.date(2026, 11, 10))
    assert e["marcos"][0]["data"] == "2026-11-25"
    assert e["dias_uteis_ate_limite_ne"] == 10  # 11 a 25/11, sem sábados, domingos e 20/11
    assert e["ne60"] is None
    depois = g.bloco_encerramento(dt.date(2026, 11, 26), {"total": {"mais60_valor": 1.0}, "por_omds": {}, "ne": [{"ne": "x"}] * 12})
    assert depois["marcos"][0]["vencido"] is True and depois["marcos"][1]["vencido"] is False
    assert len(depois["ne60"]["maiores"]) == 10


def test_capacidade_soma_as_omds_e_separa_registro_por_valor():
    from motor import gof_painel as g
    cap = {"data_coleta": "2026-11-10T17:05:12", "extrato_tg": "2026-11-09", "limite": "carona sem NE não aparece",
           "itens_nao_lidos": [1, 2],
           "saldo": {"versao": "0.2", "resumo": {
               "A": {"registrado": 100.0, "empenhado_tg": 40.0, "saldo_proprio": 60.0, "vence_ate_31dez": 5.0,
                     "saldo_por_natureza": {"POR_QUANTIDADE": 50.0, "POR_VALOR": 10.0},
                     "maiores_itens": [{"ata": "1/2026", "compra": "9/2025", "gerenciadora": "160307", "descricao": "X" * 200,
                                        "natureza": "POR_VALOR", "saldo_proprio": 10.0}] * 5},
               "B": {"registrado": 30.0, "empenhado_tg": 0.0, "saldo_proprio": 30.0, "saldo_por_natureza": {"POR_QUANTIDADE": 30.0}}},
               "empenhado_fora_da_coleta": {"valor": 7.5, "itens": 3, "por_classe": {"CONTRATO_ATIVO": {"itens": 3, "valor": 7.5}}}}}
    c = g.bloco_capacidade(cap)
    assert c["total"] == {"registrado": 130.0, "empenhado_tg": 40.0, "saldo": 90.0, "por_quantidade": 80.0, "por_valor": 10.0,
                          "vence_ate_31dez": 5.0}
    assert len(c["por_omds"]["A"]["maiores"]) == 3 and len(c["por_omds"]["A"]["maiores"][0]["descricao"]) == 70
    assert c["fora_da_coleta"] == {"valor": 7.5, "itens": 3, "por_classe": {"CONTRATO_ATIVO": 7.5}} and c["itens_nao_lidos"] == 2
    assert g.bloco_capacidade(None) is None and g.bloco_capacidade({"saldo": {}}) is None


def test_capacidade_real_fecha_com_o_saldo_publicado():
    import json

    from motor import gof_painel as g
    c = g.bloco_capacidade(json.load(open("dados/capacidade/ultimo.json", encoding="utf-8")))
    t = c["total"]
    assert set(c["por_omds"]) == {"Cmdo BaApLog", "DC Mun", "BMSA", "1º D Sup", "ECT", "BCMS"}
    assert round(t["por_quantidade"] + t["por_valor"], 2) == t["saldo"]
    assert round(t["registrado"] - t["empenhado_tg"], 2) == t["saldo"]


def test_dispensa_reconta_acima_do_teto_e_nao_traz_pessoa():
    import json

    from motor import gof_painel as g
    d = g.bloco_dispensa({"teto": {"I": 130984.2, "II": 65492.11}, "subitens_acima_do_teto": 99, "por_omds": {
        "A": {"acima_70pct": [{"pct_teto": 152.7}, {"pct_teto": 92.8}]}, "B": {"acima_70pct": [{"pct_teto": 100.0}]}}})
    assert d["subitens_acima_do_teto"] == 1
    assert g.bloco_dispensa(None) is None
    real = json.load(open("dados/dispensa/ultimo.json", encoding="utf-8"))
    r = g.bloco_dispensa(real)
    assert r["subitens_acima_do_teto"] == real["subitens_acima_do_teto"] >= 1
    for om in real["por_omds"].values():
        for a in om["acima_70pct"] + om["maiores"]:
            assert set(a) == {"ug", "inciso", "subitem", "nome", "valor", "pct_teto"}
            assert round(100 * a["valor"] / real["teto"][a["inciso"]], 1) == a["pct_teto"]

