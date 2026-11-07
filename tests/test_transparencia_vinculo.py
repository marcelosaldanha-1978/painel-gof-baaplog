# -*- coding: utf-8 -*-
"""
Testes da regra de vinculo NE -> pregao (gcalc_transparencia v1.2, 07/11/2026; v1.1 de 06/11; LOG-121 e LOG-130 do projeto GOF-BaApLog).

O que se trava aqui:
- colisao de numero de pregao (cada UASG do EB reinicia 900xx/ano) NAO vincula sem favorecido de ata;
- a UASG gerenciadora NAO e exigida no texto (o EB escreve a UG da NC depois do numero);
- o NUP da NE nao e chave;
- as UG 167xxx fazem parte da coleta (regra viva de 05/11/2026);
- o CSV exportado do TG traz subtotais e totais: so linhas com o padrao da NE entram, e a soma nao dobra;
- v1.2: a UASG so conta como citada se for numero isolado (nao dentro do numero da NC);
- v1.2: PROVAVEL ou CONFIRMADO em mais de um pregao vira AMBIGUO e nao entra na soma de nenhum;
- totais reais por OMDS recalculados contra os CSV sem pessoa da pasta de evidencias (quando acessivel).
"""
import os
from pathlib import Path

import gcalc_transparencia as tr
import pytest

# ----------------------------------------------------------------- fichas sinteticas
FICHAS = [
    {"pregao": "PE 90023/2025", "numero_pncp": "90023", "ano_pncp": "2025", "numeros_alternativos": [], "uasg": "160246",
     "ugg": "DCMun", "fornecedores": {"11111111000191": "ALFA MATERIAIS LTDA"}, "fornecedores_nomes": {tr.norm_nome("ALFA MATERIAIS LTDA")},
     "atas": [], "primeira_assinatura": "2026-04-17", "homologado": 1000.0},
    {"pregao": "PE 90315/2026", "numero_pncp": "90315", "ano_pncp": "2026", "numeros_alternativos": [], "uasg": "160238",
     "ugg": "BaApLog", "fornecedores": {"22222222000172": "BETA GRAFICA LTDA"}, "fornecedores_nomes": {tr.norm_nome("BETA GRAFICA LTDA")},
     "atas": [], "primeira_assinatura": "2026-05-15", "homologado": 500.0},
    {"pregao": "PE 108/2026", "numero_pncp": "108", "ano_pncp": "2026", "numeros_alternativos": ["92"], "uasg": "160307",
     "ugg": "1oDSup", "fornecedores": {"33333333000153": "GAMA MOVEIS LTDA"}, "fornecedores_nomes": {tr.norm_nome("GAMA MOVEIS LTDA")},
     "atas": [], "primeira_assinatura": None, "homologado": None},
]


def _ne(obs, fav_cod="", fav_nome="", ug="160246", valor="100,00", modalidade="12", nup="", data="17/06/2026"):
    return {"documento": ug + "000012026NE000001", "observacao": obs, "codigoFavorecido": fav_cod, "favorecido": fav_nome,
            "numeroProcesso": nup, "valor": valor, "modalidade": modalidade, "data": data, "_ug": ug, "_nome": tr.UGS.get(ug, ug)}


# ----------------------------------------------------------------- regra nova
def test_padrao_do_eb_sem_uasg_gerenciadora_confirma_com_favorecido_de_ata():
    # texto real do EB: depois do numero vem a UG da NC, nao a UASG do pregao
    e = _ne("AQUISICAO DE MATERIAL DE EXPEDIENTE E LIMPEZA - PREGAO:90023/2025 - 1602462026NC011459 - 17JUN26 - 160073SI:.16 ALMOX.",
            fav_cod="11.111.111/0001-91")
    v = tr.vincular([e], FICHAS)
    assert len(v) == 1 and v[0]["nivel"] == "CONFIRMADO" and v[0]["pregao"] == "PE 90023/2025"


def test_colisao_de_numero_nao_vincula_sem_favorecido_de_ata():
    # "90315/2026" citado no DCMun e copa e cozinha de outra UASG, nao a grafica do GCALC (LOG-121)
    e = _ne("AQUISICAO DE MATERIAL DE COPA E COZINHA - PREGAO: 90315/2026 1602982026NC000015 - 06AGO26 - 160504SI:21",
            fav_cod="99.999.999/0001-00", fav_nome="DELTA UTENSILIOS LTDA")
    v = tr.vincular([e], FICHAS)
    assert len(v) == 1 and v[0]["nivel"] == "CITADO_SEM_ATA"
    assert tr.resumo(v, FICHAS)["PE 90315/2026"]["confirmado"] == 0.0


def test_mesmo_numero_em_outra_uasg_com_uasg_explicita_vira_alerta():
    e = _ne("PREGAO 90023/2025 UASG 160246 - AQUISICAO", fav_cod="99.999.999/0001-00")
    v = tr.vincular([e], FICHAS)
    assert v[0]["nivel"] == "ALERTA"


def test_nup_da_ne_nao_e_chave():
    # NUP preenchido com o processo da propria OM e texto sem citar pregao: nada vincula pelo NUP
    e = _ne("AQUISICAO DE MATERIAL PROFESP - 160246 2026NC002024 - 28ABR26", fav_cod="99.999.999/0001-00",
            nup="64449.001234/2026-11")
    assert tr.vincular([e], FICHAS) == []


def test_favorecido_de_ata_sem_citar_numero_e_provavel():
    e = _ne("AQUISICAO DE MATERIAL DE LIMPEZA - 160246 2026NC002024 - 28ABR26", fav_cod="11.111.111/0001-91")
    v = tr.vincular([e], FICHAS)
    assert v[0]["nivel"] == "PROVAVEL"


def test_favorecido_por_nome_quando_nao_ha_cnpj_como_no_csv_do_tg():
    e = _ne("AQUISICAO - PREGAO 90023/2025 - 1602462026NC011459", fav_cod="", fav_nome="Alfa Materiais Ltda.")
    assert tr.vincular([e], FICHAS)[0]["nivel"] == "CONFIRMADO"


def test_modalidade_diferente_de_pregao_vira_alerta():
    e = _ne("AQUISICAO - PREGAO 90023/2025 - 1602462026NC011459", fav_cod="11.111.111/0001-91", modalidade="06")
    assert tr.vincular([e], FICHAS)[0]["nivel"] == "ALERTA"


def test_relancamento_pe_92_para_108_vincula_pelo_numero_antigo():
    e = _ne("MOBILIARIO - PREGAO 92/2026 - 1603072026NC000100", fav_cod="33.333.333/0001-53", ug="160307")
    assert tr.vincular([e], FICHAS)[0]["pregao"] == "PE 108/2026"


def test_ne_com_valor_zero_confirmada_vira_zerado():
    e = _ne("PREGAO 90023/2025 - 1602462026NC011459", fav_cod="11.111.111/0001-91", valor="0,00")
    assert tr.vincular([e], FICHAS)[0]["nivel"] == "ZERADO"


# ----------------------------------------------------------------- UG 167xxx
def test_ugs_incluem_a_secundaria_167_de_cada_omds():
    for ug in ("160238", "160329", "160304", "160321", "160246", "160307"):
        assert "167" + ug[3:] in tr.UGS and tr.UGS["167" + ug[3:]] == tr.UGS[ug]
    assert all(ug in tr.UGS_ALVO for ug in tr.UGS)


# ----------------------------------------------------------------- CSV do TG
CSV_TG = (
    "GOF-BaApLog-TESTE-Empenho por NE\n"
    "\n"
    '"UG Executora"\t\t"UG Responsável"\t\t"NE CCor"\t"NE CCor - Favorecido"\t"NE - Modalidade Licitação"\t\t"Conta Contábil"\t\t"522920101"\n'
    ' \t\t \t\t \t \t \t\t \t\t"= EMISSAO DE EMPENHOS"\n'
    '"160246"\t"DEPOSITO CENTRAL DE MUNICAO"\t"110407"\t"DEPARTAMENTO"\t"160246000012026NE000140"\t"ALFA MATERIAIS LTDA"\t"12"\t"PREGAO"\t"522920101"\t"EMISSAO"\t"3.114,59"\n'
    '"160246"\t"DEPOSITO CENTRAL DE MUNICAO"\t"110407"\t"DEPARTAMENTO"\t"160246000012026NE000187"\t"BETA GRAFICA LTDA"\t"06"\t"DISPENSA"\t"522920101"\t"EMISSAO"\t"25.200,00"\n'
    '"160246"\t"DEPOSITO CENTRAL DE MUNICAO"\t"110407"\t"DEPARTAMENTO"\t"Total"\t""\t""\t""\t""\t""\t"28.314,59"\n'
    '"167246"\t"DEPOSITO CENTRAL DE MUNICAO"\t"110407"\t"DEPARTAMENTO"\t"167246000012026NE000016"\t"ALFA MATERIAIS LTDA"\t"12"\t"PREGAO"\t"522920101"\t"EMISSAO"\t"1.445,00"\n'
    '"167246"\t"DEPOSITO CENTRAL DE MUNICAO"\t"110407"\t"DEPARTAMENTO"\t"Total"\t""\t""\t""\t""\t""\t"1.445,00"\n'
    '"Total"\t""\t""\t""\t""\t""\t""\t""\t""\t""\t"29.759,59"\n'
)


def test_ler_csv_tg_ignora_subtotais_e_nao_dobra_a_soma(tmp_path):
    p = tmp_path / "tg.csv"
    p.write_bytes(CSV_TG.encode("cp1252"))
    regs = tr.ler_csv_tg(p)
    assert [r["documento"][-6:] for r in regs] == ["000140", "000187", "000016"]
    assert round(sum(tr._num(r["valor"]) for r in regs), 2) == 29759.59  # e nao 59.519,18
    assert {r["_ug"] for r in regs} == {"160246", "167246"}
    assert regs[0]["favorecido"] == "ALFA MATERIAIS LTDA" and regs[0]["modalidade"] == "12" and regs[1]["modalidade"] == "06"


CSV_TG_COM_DATA = (
    "Relatorio\n\n"
    '"UG Executora"\t\t"NE CCor"\t"NE CCor - Favorecido"\t"NE - Modalidade Licitação"\t\t"NE - Descrição"\t"Conta Contábil"\t\t"522920101"\n'
    ' \t\t \t \t \t\t \t"NE - Dia Emissão"\t\t"Movim. Líquido"\n'
    '"160246"\t"DCMUN"\t"160246000012026NE000140"\t"ALFA MATERIAIS LTDA"\t"12"\t"PREGAO"\t"PREGAO 90023/2025 - 1602462026NC011459"\t"26/05/2026"\t"EMISSAO"\t"3.114,59"\n'
    '"Total"\t""\t""\t""\t""\t""\t""\t""\t""\t"3.114,59"\n'
)


def test_ler_csv_tg_acha_a_data_na_segunda_linha_do_cabecalho(tmp_path):
    # "NE - Dia Emissao" e atributo de coluna: o TG o escreve na 2a linha do cabecalho, nao na 1a
    p = tmp_path / "tg.csv"
    p.write_bytes(CSV_TG_COM_DATA.encode("cp1252"))
    regs = tr.ler_csv_tg(p)
    assert len(regs) == 1 and regs[0]["data"] == "26/05/2026" and "90023/2025" in regs[0]["observacao"]
    assert tr.vincular(regs, FICHAS)[0]["nivel"] == "CONFIRMADO"


def test_ler_csv_tg_sem_cabecalho_falha_alto(tmp_path):
    p = tmp_path / "x.csv"
    p.write_bytes(b"nada\n")
    with pytest.raises(RuntimeError):
        tr.ler_csv_tg(p)


# ----------------------------------------------------------------- recalculo contra os CSV sem pessoa (evidencias do projeto)
EVID = Path(os.environ.get("GCALC_PROJETO_ONEDRIVE", r"C:\Users\marce\OneDrive\Documentos\claude\projects\GCALC BaApLog 2025_2026")) / "02_EVIDENCIAS_E_REGISTROS"
# totais do LOG-120 (TG, conta 522920101, 2026, 160+167)
TOTAIS_LOG120 = {"BCMS": (467, 14227680.04), "BAAPLOG": (573, 4349063.66), "1DSUP": (548, 26176720.56), "BMSA": (611, 5056202.32), "DCMUN": (537, 4867896.06)}


@pytest.mark.parametrize("omds", sorted(TOTAIS_LOG120))
def test_totais_do_csv_completo_batem_com_o_log_120(omds):
    pasta = EVID / ("TG_2026-11-06_PILOTO_" + omds)
    arqs = sorted(pasta.glob("*CSV_completo_06nov2026.csv")) if pasta.exists() else []
    if not arqs:
        pytest.skip("evidencias do projeto nao acessiveis: %s" % pasta)
    regs = tr.ler_csv_tg(arqs[0])
    n, total = TOTAIS_LOG120[omds]
    assert len(regs) == n
    assert round(sum(tr._num(r["valor"]) for r in regs), 2) == total


def test_dcmun_real_reproduz_o_log_121():
    """Prova ponta a ponta: CSV real do DCMun com atributos + ficha gerada do PNCP = 56 NE CONFIRMADO, R$ 257.926,89 (LOG-121)."""
    import json
    csv = EVID / "TG_2026-11-06_PILOTO_DCMUN" / "tg_DCMun_conta522920101_2026_CSV_completo_ATRIBUTOS_NE_06nov2026.csv"
    conj = EVID / "PNCP_COMPRAS_2026-11-03" / "pncp_12_processos.json"
    if not (csv.exists() and conj.exists()):
        pytest.skip("evidencias do projeto nao acessiveis")
    fichas = tr.ficha_de_pncp(json.load(open(conj, encoding="utf-8")))
    vin = tr.vincular(tr.ler_csv_tg(csv), fichas)
    res = tr.resumo(vin, fichas)
    assert sum(r["n_confirmado"] for r in res.values()) == 56
    assert round(sum(r["confirmado"] for r in res.values()), 2) == 257926.89
    # colisoes medidas no LOG-121: 90009/2025 e 90003 citados no DCMun sao OUTROS pregoes -> nada confirmado
    assert res["PE 90009/2025"]["n_confirmado"] == 0 and res["PE 90003/2025"]["n_confirmado"] == 0


# ----------------------------------------------------------------- v1.2 (07/11/2026, LOG-130)
def test_uasg_dentro_do_numero_da_nc_nao_e_uasg_citada():
    # caso real do DCMun: "1602462026NC406185" contem 160246, mas e o numero da NC, nao a UASG do pregao
    e = _ne("AQUISICAO DE CILINDRO DE IMAGEM - PREGAO: 90023/2025 - 1602462026NC406185 - 30ABR26 - 160504SI:. 25", fav_cod="99.999.999/0001-00")
    assert tr.vincular([e], FICHAS)[0]["nivel"] == "CITADO_SEM_ATA"


def test_uasg_isolada_continua_alerta():
    e = _ne("PREGAO 90023/2025 160246 - AQUISICAO", fav_cod="99.999.999/0001-00")
    assert tr.vincular([e], FICHAS)[0]["nivel"] == "ALERTA"


FICHAS_AMB = FICHAS + [
    {"pregao": "PE 90008/2025", "numero_pncp": "90008", "ano_pncp": "2025", "numeros_alternativos": [], "uasg": "160329",
     "ugg": "BCMS", "fornecedores": {"11111111000191": "ALFA MATERIAIS LTDA"}, "fornecedores_nomes": {tr.norm_nome("ALFA MATERIAIS LTDA")},
     "atas": [], "primeira_assinatura": "2026-06-03", "homologado": 2000.0}]


def test_provavel_em_dois_pregoes_vira_ambiguo_e_nao_soma_em_nenhum():
    e = _ne("AQUISICAO DE MATERIAL", fav_cod="11.111.111/0001-91", valor="1.000,00")
    v = tr.vincular([e], FICHAS_AMB)
    assert v[0]["nivel"] == "AMBIGUO" and v[0]["pregao"] is None
    assert set(v[0]["candidatos"]) == {"PE 90023/2025", "PE 90008/2025"} and v[0]["versao_regra"] == "1.2"
    res = tr.resumo(v, FICHAS_AMB)
    assert res["PE 90023/2025"]["provavel"] == 0.0 and res["PE 90008/2025"]["provavel"] == 0.0
    assert res["PE 90023/2025"]["n_ambiguo"] == 1 and res["PE 90008/2025"]["ambiguo_informativo"] == 1000.0


def test_citar_um_dos_pregoes_desfaz_a_ambiguidade():
    e = _ne("PREGAO 90008/2025 - AQUISICAO", fav_cod="11.111.111/0001-91")
    v = tr.vincular([e], FICHAS_AMB)
    assert v[0]["nivel"] == "CONFIRMADO" and v[0]["pregao"] == "PE 90008/2025"


def test_seis_omds_reais_v12():
    """Recalculo das 6 OMDS com a v1.2 (LOG-130): CONFIRMADO igual ao LOG-127; 1 ALERTA; 83 citado sem ata; 34 AMBIGUO."""
    import collections
    import json
    conj = EVID / "PNCP_COMPRAS_2026-11-03" / "pncp_12_processos.json"
    csvs = sorted(EVID.glob("TG_2026-11-06_PILOTO_*/*CSV_completo_ATRIBUTOS_NE_06nov2026.csv")) if EVID.exists() else []
    if not (conj.exists() and len(csvs) == 6):
        pytest.skip("evidencias do projeto nao acessiveis")
    fichas = tr.ficha_de_pncp(json.load(open(conj, encoding="utf-8")))
    regs = [r for c in csvs for r in tr.ler_csv_tg(c)]
    assert len(regs) == 3032
    vin = tr.vincular(regs, fichas)
    n = collections.Counter(v["nivel"] for v in vin)
    assert (n["CONFIRMADO"], n["ALERTA"], n["CITADO_SEM_ATA"], n["AMBIGUO"], n["PROVAVEL"]) == (85, 1, 83, 34, 196)
    amb = [v for v in vin if v["nivel"] == "AMBIGUO"]
    assert round(sum(tr._num(v["valor"]) for v in amb), 2) == 203099.98
