"""Salvaguarda de 24/11/2026 (PAINEL GOF DF, LOG-029): a DF roda nas mesmas contas Google e GitHub da BaApLog.
As duas cadeias não podem se cruzar: pasta do Drive e prefixo das assinaturas próprios, conferidos no portão 0."""
import datetime as dt
import json
from pathlib import Path

import gof_config as cfg
import gof_ponte_tg as pt
import pytest
import verificar_config as vc

RAIZ = Path(__file__).resolve().parent.parent
DF = RAIZ / "config" / "exemplos" / "df" / "om.json"
REF = RAIZ / "tests" / "dados" / "baaplog" / "om.json"
HOJE = dt.date(2026, 11, 24)


def test_baaplog_mantem_a_pasta_historica():
    assert cfg.pasta_ponte(REF) == "PONTE_TG_SEM_PESSOA" == pt.PASTA


def test_df_tem_pasta_propria():
    assert cfg.pasta_ponte(DF) == "PONTE_TG_SEM_PESSOA_DF"


def _df_alterado(tmp_path, **atg):
    om = json.loads(DF.read_text(encoding="utf-8"))
    om["assinaturas_tg"] = atg
    p = tmp_path / "om.json"
    p.write_text(json.dumps(om, ensure_ascii=False), encoding="utf-8")
    for nome in ("calendario", "metas", "brasoes"):
        if om.get(nome):
            alvo = cfg._resolver(DF.parent, om[nome])
            destino = tmp_path / om[nome]
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(alvo.read_bytes())
    return p


def test_outra_om_sem_pasta_propria_reprova(tmp_path):
    erros = vc.verificar(_df_alterado(tmp_path, prefixo_assunto="PAINEL-DF-CONF-"), hoje=HOJE)
    assert any("pasta_drive" in e for e in erros)


def test_outra_om_com_prefixo_da_baaplog_reprova(tmp_path):
    erros = vc.verificar(_df_alterado(tmp_path, prefixo_assunto="GOF-BaApLog-CONF-", pasta_drive="X_DF"), hoje=HOJE)
    assert any("se confunde com o da OM de referência" in e for e in erros)


def test_listar_pasta_usa_o_nome_do_config(monkeypatch):
    pedidos = []

    def falso_get(url, tok):
        pedidos.append(url)
        if "in+parents" in url or "%27+in+parents" in url or "in%20parents" in url:
            return json.dumps({"files": [{"id": "a1", "name": "2026-11-24_emissao_sem_pessoa.tsv"}]}).encode()
        return json.dumps({"files": [{"id": "P1", "name": "PONTE_TG_SEM_PESSOA_DF"}]}).encode()

    monkeypatch.setattr(pt, "_get", falso_get)
    arqs = pt.listar_pasta("tok", nome="PONTE_TG_SEM_PESSOA_DF")
    assert "PONTE_TG_SEM_PESSOA_DF" in pedidos[0].replace("+", " ").replace("%27", "'")
    assert arqs == {"2026-11-24_emissao_sem_pessoa.tsv": "a1"}


def test_duas_pastas_com_o_mesmo_nome_reprova(monkeypatch):
    monkeypatch.setattr(pt, "_get", lambda u, t: json.dumps({"files": [{"id": "1"}, {"id": "2"}]}).encode())
    with pytest.raises(RuntimeError, match="2 encontradas"):
        pt.listar_pasta("tok", nome="PONTE_TG_SEM_PESSOA_DF")


def test_listar_pasta_sem_nome_le_o_config_da_om(monkeypatch):
    monkeypatch.setenv("GOF_CONFIG", str(DF))
    pedidos = []

    def falso_get(url, tok):
        pedidos.append(url)
        return json.dumps({"files": [{"id": "P1", "name": "x"}]}).encode()

    monkeypatch.setattr(pt, "_get", falso_get)
    pt.listar_pasta("tok")
    assert "PONTE_TG_SEM_PESSOA_DF" in pedidos[0].replace("+", " ").replace("%27", "'")


def test_prefixo_vazio_reprova(tmp_path):
    assert any("prefixo_assunto vazio" in e for e in vc.verificar(_df_alterado(tmp_path, prefixo_assunto="", pasta_drive="X_DF"), hoje=HOJE))


@pytest.mark.parametrize("prefixo", ["GOF-", "gof-baaplog-conf-", "GOF-BaApLog-CONF-X"])
def test_prefixo_que_se_confunde_com_o_da_baaplog_reprova(tmp_path, prefixo):
    erros = vc.verificar(_df_alterado(tmp_path, prefixo_assunto=prefixo, pasta_drive="X_DF"), hoje=HOJE)
    assert any("se confunde" in e for e in erros)


@pytest.mark.parametrize("pasta", ["ponte_tg_sem_pessoa", "X_DF ", "X'DF"])
def test_pasta_igual_sem_caixa_ou_com_espaco_ou_aspas_reprova(tmp_path, pasta):
    erros = vc.verificar(_df_alterado(tmp_path, prefixo_assunto="PAINEL-DF-CONF-", pasta_drive=pasta), hoje=HOJE)
    assert any("pasta_drive" in e for e in erros)


def test_id_da_baaplog_em_outra_om_reprova(tmp_path):
    om = json.loads(_df_alterado(tmp_path, prefixo_assunto="PAINEL-DF-CONF-", pasta_drive="X_DF").read_text(encoding="utf-8"))
    om["id"] = "baaplog"
    p = tmp_path / "om.json"
    p.write_text(json.dumps(om, ensure_ascii=False), encoding="utf-8")
    assert any("reservado à OM de referência" in e for e in vc.verificar(p, hoje=HOJE))


@pytest.mark.dados_baaplog
def test_baaplog_continua_aprovada_com_a_regra_de_isolamento():
    assert vc.verificar(REF, hoje=HOJE) == []
