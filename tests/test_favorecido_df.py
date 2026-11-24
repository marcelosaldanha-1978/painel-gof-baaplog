"""Ordem do usuário de 24/11/2026 (PAINEL GOF DF, LOG-033): na DF, a página mostra para quem os recursos vão.
Só o config da OM libera (dados_pessoais); a BaApLog continua sem favorecido. CPF mascarado salvo «completo»."""
import copy
import datetime as dt
import json
from pathlib import Path

import gof_config as cfg
import gof_contratos as C
import gof_rp_por_ano as R
import pytest
import verificar_config as vc
import verificar_saida as VS
from test_contratos import HOJE, reg
from test_rp_por_ano import LINHAS, REGUA

RAIZ = Path(__file__).resolve().parent.parent
REF = cfg.carregar(RAIZ / "tests" / "dados" / "baaplog" / "om.json")
DF = RAIZ / "config" / "exemplos" / "df" / "om.json"
REF_P = RAIZ / "tests" / "dados" / "baaplog" / "om.json"


def _df_cfg(tmp_path, dados_pessoais, prefixo=None):
    om = json.loads(DF.read_text(encoding="utf-8"))
    if dados_pessoais is not None:
        om["dados_pessoais"] = dados_pessoais
    if prefixo is not None:
        om["assinaturas_tg"]["prefixo_assunto"] = prefixo
    p = tmp_path / "om.json"
    p.write_text(json.dumps(om, ensure_ascii=False), encoding="utf-8")
    for nome in ("calendario", "metas", "brasoes"):
        if om.get(nome):
            destino = tmp_path / om[nome]
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(cfg._resolver(DF.parent, om[nome]).read_bytes())
    return p


def _com(favorecido=True, cpf="mascarado"):
    om = copy.deepcopy(REF)
    om["dados_pessoais"] = {"favorecido": favorecido, "cpf": cpf}
    return om


def test_mascara_cpf_e_preserva_cnpj():
    assert cfg.mascarar_cpf("123.456.789-01") == "***.456.789-**"
    assert cfg.mascarar_cpf("JOAO FICTICIO 12345678901") == "JOAO FICTICIO ***.456.789-**"
    assert cfg.mascarar_cpf("12.345.678/0001-90") == "12.345.678/0001-90"
    assert cfg.mascarar_cpf("12345678000190") == "12345678000190"
    assert cfg.mascarar_cpf("123.456.789-01", "completo") == "123.456.789-01"


def test_padrao_sem_favorecido_e_df_com():
    assert cfg.dados_pessoais(REF) == {"favorecido": False, "cpf": "mascarado"}
    assert cfg.dados_pessoais(DF) == {"favorecido": True, "cpf": "mascarado"}


def test_contratos_com_fornecedor_e_cpf_mascarado():
    pj = reg("1/2026", "2027-01-01", forn="EMPRESA FICTICIA LTDA")
    pf = reg("2/2026", "2027-02-01", forn="PESSOA FICTICIA")
    pf["fornecedor"]["cnpj_cpf_idgener"] = "123.456.789-01"
    pf["objeto"] = "SERVICO PRESTADO POR 123.456.789-01"
    cs = C.vigentes([pj, pf], HOJE, pessoais={"favorecido": True, "cpf": "mascarado"})
    assert (cs[0]["fornecedor"], cs[0]["documento"]) == ("EMPRESA FICTICIA LTDA", "00.000.000/0001-00")
    assert (cs[1]["fornecedor"], cs[1]["documento"]) == ("PESSOA FICTICIA", "***.456.789-**")
    assert "123.456.789-01" not in json.dumps(cs) and "***.456.789-**" in cs[1]["objeto"]


def test_contratos_sem_permissao_seguem_sem_fornecedor():
    cs = C.vigentes([reg("1/2026", "2027-01-01")], HOJE)
    assert "fornecedor" not in cs[0] and "documento" not in cs[0]


CAB_FAV = ('T\n\n"UG Executora"\t\t"NE CCor"\t"NE CCor - Favorecido"\t"Conta Contábil"\t"531110100"\t"531210000"\t"631100000"'
           '\t"631300000"\t"631400000"\t"631510000"\t"631980000"\n'
           ' \t\t \t \t \t"= I"\t"= R"\t"= AL"\t"= LP"\t"= P"\t"= B"\t"= C"\n'
           ' \t\t \t \t"NE - Dia"\t"M"\t"M"\t"M"\t"M"\t"M"\t"M"\t"M"\n')


def _com_favorecido():
    out = []
    for i, ln in enumerate(LINHAS.strip("\n").split("\n")):
        c = ln.split("\t")
        nome = '"EMPRESA FICTICIA %d LTDA"' % i if i else '"PESSOA FICTICIA 12345678901"'
        out.append("\t".join(c[:3] + [nome] + c[3:]))
    return (CAB_FAV + "\n".join(out) + "\n").encode("cp1252")


def test_rp_por_ano_detalhe_por_ne_com_favorecido():
    r = R.calcular(_com_favorecido(), REGUA, "2026-11-23", config=_com())
    det = {d["ne"]: d for d in r["por_ne"]}
    assert set(det) == {"160321000012025NE000001", "167321000012024NE000002"}  # só NE com saldo a liquidar
    assert det["160321000012025NE000001"]["favorecido"] == "PESSOA FICTICIA ***.456.789-**"
    assert det["160321000012025NE000001"]["a_liquidar"] == 400.0
    assert "12345678901" not in json.dumps(r, ensure_ascii=False)


def test_rp_por_ano_sem_permissao_recusa_favorecido():
    with pytest.raises(ValueError, match="P-RP-4"):
        R.calcular(_com_favorecido(), REGUA, "2026-11-23", config=REF)


def _saida(tmp_path, dados):
    import hashlib
    txt = json.dumps(dados, ensure_ascii=False)
    canon = json.dumps(dados, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    (tmp_path / "dados.json").write_text(txt, encoding="utf-8")
    (tmp_path / "index.html").write_text('<script type="application/json" id="dados">%s</script><p>%s</p>' % (txt, h),
                                         encoding="utf-8")
    return str(tmp_path)


@pytest.mark.parametrize("config,doc,ok", [
    (DF, "***.456.789-**", True),          # DF: favorecido e CPF mascarado passam
    (DF, "123.456.789-01", False),         # DF: CPF inteiro reprova
    (None, "***.456.789-**", False),       # referência: nem mascarado
])
def test_verificar_saida_segue_o_config(tmp_path, monkeypatch, config, doc, ok):
    if config:
        monkeypatch.setenv("GOF_CONFIG", str(config))
    dados = {"liquidacao": {"por_ne": [{"favorecido": "PESSOA FICTICIA", "documento": doc}]}}
    rc = VS.main(["--saida", _saida(tmp_path, dados)])
    assert (rc == 0) == ok


def test_b1_liquidacao_com_favorecido_por_ne():
    import gof_ponte_tg as pt
    from test_ponte_tg import NE1, NE2, emissao
    txt = emissao(["160238", "BASE", NE1, "02/01/2026", "1000,00", "0", "0", "600,00", "0", "400,00", "0"],
                  ["160238", "BASE", NE2, "02/10/2026", "500,00", "0", "0", "0", "0", "500,00", "0"])
    favs = pt.ler_favorecidos('"%s"\t"PESSOA FICTICIA 12345678901"\t"123.456.789-01"\n' % NE1)
    r = pt.liquidacao(pt.agregar_emissao(txt), "2026-11-23", favorecidos=favs)
    assert [x["ne"] for x in r["por_ne"]] == [NE1]  # só NE com saldo a liquidar
    x = r["por_ne"][0]
    assert x["favorecido"] == "PESSOA FICTICIA ***.456.789-**" and x["documento"] == "***.456.789-**"
    assert x["a_liquidar"] == 600.0 and x["dias"] == 325
    assert "por_ne" not in pt.liquidacao(pt.agregar_emissao(txt), "2026-11-23")  # sem permissão, nada muda


def test_nome_de_mei_com_cpf_e_mascarado_no_contratado():
    pf = reg("3/2026", "2027-03-01", forn="NOME FICTICIO 12345678901")
    pf["fornecedor"]["cnpj_cpf_idgener"] = "12.345.678/0001-90"
    cs = C.vigentes([pf], HOJE, pessoais={"favorecido": True, "cpf": "mascarado"})
    assert cs[0]["fornecedor"] == "NOME FICTICIO ***.456.789-**" and cs[0]["documento"] == "12.345.678/0001-90"


def test_verificar_saida_df_reprova_cpf_sem_pontuacao_em_campo_de_pessoa(tmp_path, monkeypatch):
    monkeypatch.setenv("GOF_CONFIG", str(DF))
    dados = {"x": [{"fornecedor": "NOME FICTICIO 12345678901"}]}
    assert VS.main(["--saida", _saida(tmp_path, dados)]) == 1


def test_recalculo_confere_o_detalhe_por_ne(monkeypatch):
    import recalculo_independente as RI
    monkeypatch.setenv("GOF_CONFIG", str(DF))
    base = {"por_ug": [{"omds": "DF", "ug": "160336", "ano": 2025, "a_liquidar": 100.0, "inscrito": 100.0, "liquidado": 0.0,
                        "cancelado": 0.0, "em_liquidacao": 0.0, "bloqueado": 0.0, "excetuado": 0.0}],
            "por_omds": [], "data_dado": "2026-11-23",
            "por_ne": [{"ug": "160336", "a_liquidar": 100.0, "favorecido": "EMPRESA FICTICIA LTDA"}]}
    fn = RI.conferir_v24
    assert fn({"rp_por_ano": base}) == []
    ruim = copy.deepcopy(base)
    ruim["por_ne"][0].update(a_liquidar=90.0, favorecido="NOME FICTICIO 12345678901")
    falhas = fn({"rp_por_ano": ruim})
    assert any("detalhe por NE" in f for f in falhas) and any("CPF inteiro" in f for f in falhas)


def test_cpf_completo_nao_vale_na_pagina_publica(tmp_path):
    om = _com(cpf="completo")
    assert cfg.dados_pessoais(om)["cpf"] == "mascarado"
    erros = vc.verificar(_df_cfg(tmp_path, {"favorecido": True, "cpf": "completo"}), hoje=dt.date(2026, 11, 24))
    assert any("só aceita «mascarado»" in e for e in erros)


@pytest.mark.parametrize("bruto", ["123 456 789 01", "123.456.789–01", "123.456.789.01", "123.456.789/01", "12345678901"])
def test_mascara_com_outros_separadores(bruto):
    assert cfg.mascarar_cpf("X " + bruto) == "X ***.456.789-**"


def test_favorecido_fora_do_lugar_reprova(tmp_path, monkeypatch):
    monkeypatch.setenv("GOF_CONFIG", str(DF))
    assert VS.main(["--saida", _saida(tmp_path, {"portal": {"favorecido": "EMPRESA FICTICIA"}})]) == 1


def test_cpf_sem_separador_em_ressalva_reprova(tmp_path, monkeypatch):
    monkeypatch.setenv("GOF_CONFIG", str(DF))
    assert VS.main(["--saida", _saida(tmp_path, {"liquidacao": {"ressalva_favorecido": "PESSOA 12345678901"}})]) == 1


def test_recalculo_confere_o_detalhe_do_b1(monkeypatch):
    import recalculo_independente as RI
    monkeypatch.setenv("GOF_CONFIG", str(DF))
    lq = {"por_omds": {"DF": {"por_ug": {"160336": {"a_liquidar": 600.0}}}},
          "por_ne": [{"ug": "160336", "a_liquidar": 600.0, "favorecido": "EMPRESA FICTICIA LTDA", "documento": ""}]}
    assert RI.conferir_v24({"liquidacao": lq}) == []
    lq["por_ne"][0].update(a_liquidar=1e9, documento="123.456.789-01")
    f = RI.conferir_v24({"liquidacao": lq})
    assert any("detalhe por NE" in x for x in f) and any("CPF inteiro" in x for x in f)


def test_prefixo_que_contem_o_da_baaplog_e_clone_fora_do_repo(tmp_path, monkeypatch):
    erros = vc.verificar(_df_cfg(tmp_path, None, prefixo="X GOF-BaApLog-CONF-"), hoje=dt.date(2026, 11, 24))
    assert any("se confunde" in e for e in erros)
    monkeypatch.setenv("GITHUB_REPOSITORY", "dono/painel-gof-df")
    assert any("repositório que não é o dela" in e for e in vc.verificar(REF_P, hoje=dt.date(2026, 11, 24), raiz_dados=tmp_path))


def test_favorecido_do_b1_ausente_ou_cp1252_nao_derruba(monkeypatch):
    import gof_ponte_tg as pt
    favs, fonte = pt.carregar_favorecidos({}, "2026-11-24", "tok")
    assert favs == {} and "indisponível" in fonte["ressalva"]
    ne = "160336000012026NE000001"
    linha = '"%s"' % ne + chr(9) + '"JOSÉ FICTICIO 12345678901"' + chr(9) + '""' + chr(10)
    monkeypatch.setattr(pt, "_get", lambda u, t: linha.encode("cp1252"))
    favs, fonte = pt.carregar_favorecidos({"2026-11-24_favorecido_por_ne.tsv": "id"}, "2026-11-24", "tok")
    assert favs[ne]["favorecido"] == "JOSÉ FICTICIO ***.456.789-**" and len(fonte["sha256"]) == 64


def test_rp_sem_coluna_de_favorecido_avisa():
    linhas, avisos = R.ler(_com_favorecido().replace(b"NE CCor - Favorecido", b"Coluna X"), permitir_favorecido=True,
                           config=_com(), guardar_favorecido=True)
    assert avisos.get("coluna de favorecido não encontrada no cabeçalho") == 1
