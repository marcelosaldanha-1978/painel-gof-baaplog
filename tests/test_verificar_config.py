"""Etapa A (v2.2): portão da configuração (verificar_config.py) e prova de que a configuração de exemplo da DF monta
sem os blocos do GCALC, com dados FICTÍCIOS marcados (tests/dados/exemplo_df)."""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import gof_config as cfg
import pytest
import verificar_config as vc

RAIZ = Path(__file__).resolve().parent.parent
MOTOR = RAIZ / "motor"
DF = RAIZ / "config" / "exemplos" / "df" / "om.json"
EXTRATO_DF = RAIZ / "tests" / "dados" / "exemplo_df" / "extrato_ficticio.json"
HOJE = dt.date(2026, 11, 24)



def test_config_do_repositorio_passa_no_verificador():
    # v2.3: o config/om.json do repositório (BaApLog aqui; a OM da cópia numa réplica) passa no portão 0, com os dados dela
    assert vc.verificar(cfg.PASTA_CONFIG / "om.json", hoje=HOJE) == []


@pytest.mark.dados_baaplog
def test_config_baaplog_passa_no_verificador():
    assert vc.verificar(cfg.caminho_om(), hoje=HOJE) == []


def test_config_exemplo_df_passa_no_verificador_e_tem_as_6_ug():
    assert vc.verificar(DF, hoje=HOJE) == []
    om = json.loads(DF.read_text(encoding="utf-8"))
    ugs = {u for o in om["omds"] for u in (o["ug160"], o["ug167"])}
    assert ugs == {"160336", "167336", "160285", "167285", "160529", "167529"}
    assert not any(om["blocos"].values())  # sem carteira GCALC, atas PNCP, capacidade nem dispensa
    assert om["assinaturas_tg"]["prefixo_assunto"] == "PAINEL-DF-CONF-"


def test_verificador_reprova_config_ruim(tmp_path):
    om = json.loads(DF.read_text(encoding="utf-8"))
    om["omds"][1]["ug160"] = om["omds"][0]["ug160"]  # UG repetida
    om["omds"][2]["ug167"] = "1675299"  # fora do padrão
    om["omds"][0]["ug167"] = "167999"  # sufixo diferente da UG 160
    om["blocos"]["carteira_gcalc"] = True  # ligado sem os dados (raiz vazia)
    p = tmp_path / "om.json"
    p.write_text(json.dumps(om, ensure_ascii=False), encoding="utf-8")
    texto = " | ".join(vc.verificar(p, hoje=HOJE, raiz_dados=tmp_path))
    assert "UG repetida" in texto
    assert "fora do padrão" in texto
    assert "sufixos diferentes" in texto
    assert "carteira_gcalc ligado sem o arquivo" in texto


def test_verificador_reprova_calendario_de_outro_exercicio_e_avisa_vencido(tmp_path):
    om = json.loads(DF.read_text(encoding="utf-8"))
    om["exercicio"] = 2027  # calendário e eventos são de 2026
    p = tmp_path / "om.json"
    p.write_text(json.dumps(om, ensure_ascii=False), encoding="utf-8")
    assert any("outro exercício" in e for e in vc.verificar(p, hoje=HOJE))
    avisos = []
    assert vc.verificar(DF, hoje=dt.date(2027, 1, 5), avisos=avisos) == []
    assert any("vencido" in a for a in avisos)


def _rodar(args, env):
    r = subprocess.run([sys.executable, *args], cwd=RAIZ, env=env, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def test_exemplo_df_monta_sem_blocos_do_gcalc(tmp_path):
    env = {**os.environ, "GOF_CONFIG": str(DF), "PYTHONUTF8": "1"}
    saida = tmp_path / "saida"
    nada = str(tmp_path / "inexistente.json")
    out = _rodar([str(MOTOR / "gof_painel.py"), "--extrato", str(EXTRATO_DF), "--saida", str(saida), "--hoje", HOJE.isoformat(),
                  "--encerramento", nada, "--liquidacao", nada, "--regua", nada], env)
    assert "B3 e B4 desligados" in out
    dados = json.loads((saida / "dados.json").read_text(encoding="utf-8"))
    assert dados["b3"] is None and dados["b4"] is None and dados["capacidade"] is None and dados["dispensa"] is None
    assert [o["omds"] for o in dados["b1"]["omds"]] == ["DF", "AGR", "AGSP"]
    assert dados["b1"]["total"] == 7030.74 and dados["b1"]["ne"] == 6  # uma NE fictícia anulada por inteiro
    assert dados["b1"]["rotulo_total"] == "Empenhado líquido nas 3 OMDS"
    pagina = (saida / "index.html").read_text(encoding="utf-8")
    assert "<title>Painel GOF-DF</title>" in pagina
    assert 'var NOME={DF:"DF",AGR:"AGR",AGSP:"AGSP"};' in pagina
    assert '<p class="eyebrow">DF · 3 UG executoras · UG 160 e 167</p>' in pagina
    assert "1ª RM" not in pagina  # sem referência regional no exemplo da DF
    _rodar([str(MOTOR / "recalculo_independente.py"), "--dados", str(saida / "dados.json"), "--extrato", str(EXTRATO_DF),
            "--hoje", HOJE.isoformat()], env)
    _rodar([str(MOTOR / "verificar_saida.py"), "--saida", str(saida)], env)


def test_exemplo_df_monta_com_extrato_vazio_e_mostra_as_6_ug(tmp_path):
    # v2.3 (P-012 do PAINEL GOF DF): copia nova, antes do 1º par da ponte; a CI prova com o extrato vazio e válido
    env = {**os.environ, "GOF_CONFIG": str(DF), "PYTHONUTF8": "1"}
    saida = tmp_path / "saida"
    nada = str(tmp_path / "inexistente.json")
    vazio = RAIZ / "tests" / "dados" / "extrato_vazio.json"
    _rodar([str(MOTOR / "gof_painel.py"), "--extrato", str(vazio), "--saida", str(saida), "--hoje", HOJE.isoformat(),
            "--encerramento", nada, "--liquidacao", nada, "--regua", nada], env)
    dados = json.loads((saida / "dados.json").read_text(encoding="utf-8"))
    assert dados["b1"]["total"] == 0 and dados["b1"]["ne"] == 0
    assert [(o["ug160"], o["ug167"]) for o in dados["b1"]["omds"]] == [("160336", "167336"), ("160285", "167285"),
                                                                        ("160529", "167529")]
    _rodar([str(MOTOR / "recalculo_independente.py"), "--dados", str(saida / "dados.json"), "--extrato", str(vazio),
            "--hoje", HOJE.isoformat()], env)
    _rodar([str(MOTOR / "verificar_saida.py"), "--saida", str(saida)], env)
