"""Ordem do usuário de 24/11/2026 (PAINEL GOF DF, LOG-033): na DF, a página mostra para quem os recursos vão.
Só o config da OM libera (dados_pessoais); a BaApLog continua sem favorecido. CPF mascarado salvo «completo»."""
import copy
import json
from pathlib import Path

import gof_config as cfg
import gof_contratos as C
import gof_rp_por_ano as R
import pytest
import verificar_saida as VS
from test_contratos import HOJE, reg
from test_rp_por_ano import LINHAS, REGUA

RAIZ = Path(__file__).resolve().parent.parent
REF = cfg.carregar(RAIZ / "tests" / "dados" / "baaplog" / "om.json")
DF = RAIZ / "config" / "exemplos" / "df" / "om.json"


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
    dados = {"x": [{"favorecido": "PESSOA FICTICIA", "documento": doc}]}
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
