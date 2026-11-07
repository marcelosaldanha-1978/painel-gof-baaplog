# -*- coding: utf-8 -*-
"""
Recalculo contra o EXTRATO PUBLICO (sem pessoa) de 06/11/2026 e as fichas PNCP de 07/11 — versionados em dados/.
Substitui, na nuvem, os testes que dependiam dos CSV com pessoa do OneDrive (esses continuam, pulados fora do PC).
Travas: LOG-120 (3.032 NE, R$ 63.990.398,67 nas 6 OMDS) e LOG-131 (vinculo v1.2: 85/1/83/34/196).
Tambem: dias uteis (D17 revista), pendencias com data (D20), vigia (D18) e verificador de saida (portoes 4 e 5).
"""
import collections
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import gof_painel as gp
import gof_vigia as vg
import pytest

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / "dados"
EXTRATO = DADOS / "execucao" / "2026-11-06" / "extrato.json"
FICHAS = DADOS / "pncp" / "ultimo.json"
HOJE = dt.date(2026, 11, 7)


@pytest.fixture(scope="module")
def extrato():
    return json.load(open(EXTRATO, encoding="utf-8"))


def test_extrato_publico_nao_tem_pessoa(extrato):
    t = json.dumps(extrato, ensure_ascii=False)
    assert "favorecido" not in t and "observacao" not in t
    assert set(extrato["campos"]) == set(gp.CAMPOS_EXTRATO)


def test_extrato_publico_reproduz_o_log_120(extrato):
    regs, _ = gp.ler_extrato(extrato)
    b1 = gp.bloco_b1(regs, extrato["data_execucao"])
    assert (b1["ne"], b1["total"]) == (3032, 63990398.67)
    por = {o["omds"]: (o["ne"], o["total"]) for o in b1["omds"]}
    assert por["DCMun"] == (537, 4867896.06) and por["BCMS"] == (467, 14227680.04)


def test_extrato_publico_reproduz_o_log_131(extrato):
    _, vin = gp.ler_extrato(extrato)
    n = collections.Counter(v["nivel"] for v in vin)
    assert (n["CONFIRMADO"], n["ALERTA"], n["CITADO_SEM_ATA"], n["AMBIGUO"], n["PROVAVEL"]) == (85, 1, 83, 34, 196)


def test_carteira_json_reproduz_o_painel():
    r = gp.bloco_b3(gp.ler_carteira_json(DADOS / "carteira_processos.json"), {})["resumo"]
    assert (r["processos"], r["estimado"], r["homologado"]) == (12, 75312730.52, 19117236.67)


# ----------------------------------------------------------------- D17 revista: dias uteis
def test_dias_uteis_pula_fim_de_semana():
    sex, seg, ter = dt.date(2026, 11, 6), dt.date(2026, 11, 9), dt.date(2026, 11, 10)
    assert gp.dias_uteis(sex, dt.date(2026, 11, 7)) == 0  # sabado
    assert gp.dias_uteis(sex, seg) == 1  # TG de sexta continua fresco na segunda
    assert gp.dias_uteis(sex, ter) == 2
    assert gp.dias_uteis(sex, dt.date(2026, 11, 11)) == 3  # ai passa do limite
    assert gp.dias_uteis(seg, sex) == 0  # ordem invertida nao e negativa


# ----------------------------------------------------------------- D20: pendencias com data
def test_pendencias_aceitam_formato_novo_e_lista_nua():
    novo = gp.ler_pendencias({"editado_em": "2026-11-01", "itens": [{"id": "X"}]})
    assert novo["editado_em"] == "2026-11-01" and novo["itens"] == [{"id": "X"}]
    nua = gp.ler_pendencias([{"id": "Y"}])
    assert nua["editado_em"] is None and nua["itens"] == [{"id": "Y"}]


def test_pendencias_versionadas_tem_data():
    p = json.load(open(DADOS / "pendencias_coordenador.json", encoding="utf-8"))
    dt.date.fromisoformat(p["editado_em"])
    assert p["itens"] and all({"id", "grau", "texto", "desde"} <= set(i) for i in p["itens"])


# ----------------------------------------------------------------- montagem completa a partir dos dados publicos
@pytest.fixture(scope="module")
def saida(tmp_path_factory, extrato):
    s = tmp_path_factory.mktemp("saida")
    atas = DADOS / "painel" / "2026-11-07" / "atas_pncp_2026-11-07.json"
    rc = gp.main(["--extrato", str(EXTRATO), "--fichas", str(FICHAS), "--carteira", str(DADOS / "carteira_processos.json"),
                  "--data-carteira", "2026-11-07", "--kpis", str(DADOS / "kpis_painel.json"), "--atas", str(atas),
                  "--pendencias", str(DADOS / "pendencias_coordenador.json"), "--saida", str(s), "--hoje", HOJE.isoformat()])
    assert rc == 0
    return s


def test_montagem_publica_tem_meta_da_v03(saida):
    d = json.load(open(saida / "dados.json", encoding="utf-8"))
    assert d["meta"]["versao_motor"] == gp.VERSAO_MOTOR and d["meta"]["fonte_b1"] == "tg"
    assert d["meta"]["idade_b1_dias_uteis"] == 0 and d["meta"]["b1_fresco"] is True  # 06/11 sex -> 07/11 sab
    assert d["b4"]["pendencias"]["editado_em"] == "2026-11-07" and d["b4"]["pendencias"]["dias"] == 0


def _run(script, *args):
    return subprocess.run([sys.executable, str(RAIZ / "motor" / script), *args], capture_output=True, text=True)


def test_recalculo_independente_confere(saida):
    r = _run("recalculo_independente.py", "--dados", str(saida / "dados.json"), "--extrato", str(EXTRATO),
             "--carteira", str(DADOS / "carteira_processos.json"), "--atas", str(DADOS / "painel" / "2026-11-07" / "atas_pncp_2026-11-07.json"))
    assert r.returncode == 0, r.stdout + r.stderr


def test_recalculo_independente_pega_numero_adulterado(saida, tmp_path):
    d = json.load(open(saida / "dados.json", encoding="utf-8"))
    d["b1"]["total"] += 0.02
    (tmp_path / "dados.json").write_text(json.dumps(d), encoding="utf-8")
    r = _run("recalculo_independente.py", "--dados", str(tmp_path / "dados.json"), "--extrato", str(EXTRATO),
             "--carteira", str(DADOS / "carteira_processos.json"), "--atas", str(DADOS / "painel" / "2026-11-07" / "atas_pncp_2026-11-07.json"))
    assert r.returncode == 1 and "B1 total" in r.stdout


def test_verificador_de_saida_aprova_e_reprova(saida, tmp_path):
    assert _run("verificar_saida.py", "--saida", str(saida)).returncode == 0
    (tmp_path / "dados.json").write_text((saida / "dados.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "index.html").write_text((saida / "index.html").read_text(encoding="utf-8").replace("Painel", "CPF 123.456.789-09"), encoding="utf-8")
    r = _run("verificar_saida.py", "--saida", str(tmp_path))
    assert r.returncode == 1 and "CPF" in r.stdout


# ----------------------------------------------------------------- D18: vigia
def test_vigia_em_dias_uteis(saida):
    d = json.load(open(saida / "dados.json", encoding="utf-8"))
    assert vg.avaliar(d, dt.date(2026, 11, 9), 2)["ok"]  # segunda: montagem de sabado (1 util), B1 de sexta (1 util)
    r = vg.avaliar(d, dt.date(2026, 11, 12), 2)  # quinta: 4 e 4 dias uteis
    assert not r["ok"] and not r["b1_ok"] and not r["montagem_ok"]
