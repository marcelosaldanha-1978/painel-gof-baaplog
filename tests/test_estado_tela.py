"""Etiqueta do crédito em tela pela data da Portaria (decisão de 26/11/2026): casos antes, no dia e depois do recolhimento."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "motor"))
import gof_estado_tela as et  # noqa: E402

D = dt.date
MARCOS = [("2026-11-25", "ev. 6 e 7", "Data-limite para a UGE emitir NE"),
          ("2026-11-26", "ev. 8", "A UGR recolhe todo o crédito que restar em tela"),
          ("2026-12-03", "ev. 10", "Data-limite de NE dos créditos remanejados")]
REC = D(2026, 11, 26)


def ug(tela, piso=0.0, teto=0.0, no_prazo=0.0, ate=None):
    return {"em_tela": tela, "vencido_piso": piso, "vencido_teto": teto, "tela_no_prazo": no_prazo, "prazo_ate": ate}


def est(x, hoje, dado, prorr=None):
    return et.estado_ug(x, hoje, dado, REC, prorr)


def test_data_recolhimento_vem_do_calendario():
    assert et.data_recolhimento(MARCOS) == REC


def test_zerada_e_residuo():
    assert est(ug(0.0), D(2026, 11, 27), D(2026, 11, 26))["cod"] == "TELA_ZERADA"
    r = est(ug(0.40), D(2026, 11, 27), D(2026, 11, 26))
    assert (r["cod"], r["nivel"], r["cor"]) == ("RESIDUO", 1, "gray")


def test_antes_do_prazo():
    assert est(ug(5000, 1000, 3000), D(2026, 11, 24), D(2026, 11, 21))["rotulo"] == "Recolher até 26/11"
    r = est(ug(5000, 0, 3000), D(2026, 11, 24), D(2026, 11, 21))
    assert (r["cod"], r["valor"], r["faixa"]) == ("VERIFICAR", 3000, [0, 3000])
    r = est(ug(5000), D(2026, 11, 24), D(2026, 11, 21))
    assert (r["cod"], r["rotulo"]) == ("NO_PRAZO", "No prazo até 26/11")


def test_dia_do_recolhimento_cobra_todo_o_saldo_sem_prazo_futuro():
    # caso real da DF em 26/11 (dado de 25/11): R$ 132 mil em tela, R$ 6,5 mil certamente vencidos
    r = est(ug(132170.22, 6500.16, 17802.66), REC, D(2026, 11, 25))
    assert (r["cod"], r["rotulo"], r["valor"], r["material"]) == ("PRAZO_HOJE", "Prazo hoje: recolher", 132170.22, True)
    r = est(ug(5000, 0, 0, 5000, "2026-12-03"), REC, D(2026, 11, 25))
    assert (r["cod"], r["rotulo"]) == ("NO_PRAZO", "No prazo até 03/12")


def test_depois_do_prazo_vira_fora_da_portaria():
    r = est(ug(978.69, 978.69, 978.69), D(2026, 11, 27), D(2026, 11, 26))
    assert (r["cod"], r["nivel"], r["cor"], r["rotulo"]) == ("FORA", 5, "red", "Fora da Portaria há 1 dia")
    r = est(ug(20000, 0, 0, 15000, "2026-12-03"), D(2026, 11, 30), D(2026, 11, 27))
    assert (r["cod"], r["valor"], r["rotulo"]) == ("FORA", 5000, "Fora da Portaria há 4 dias")
    # dado atrasado (ainda de antes do prazo) também vira fora quando o prazo já passou
    assert est(ug(5000), D(2026, 11, 30), D(2026, 11, 25))["cod"] == "FORA"
    # tudo com prazo escrito futuro: no prazo
    assert est(ug(5000, 0, 0, 5000, "2026-12-03"), D(2026, 11, 30), D(2026, 11, 27))["cod"] == "NO_PRAZO"


def test_prorrogacao_registrada_e_vencida():
    r = est(ug(5000, 5000, 5000), D(2026, 11, 30), D(2026, 11, 27), D(2026, 12, 2))
    assert (r["cod"], r["rotulo"], r["motivo"]) == ("NO_PRAZO", "No prazo até 02/12", "prorrogação da UGR")
    assert est(ug(5000, 5000, 5000), D(2026, 12, 3), D(2026, 12, 2), D(2026, 12, 2))["cod"] == "FORA"


def test_omds_pega_a_pior_ug_e_conta():
    regua = {"data_dado": "2026-11-26", "por_omds": {
        "AGR": {"por_ug": {"160285": ug(22458.45, 22318.45, 22318.45), "167285": ug(978.69, 978.69, 978.69)}},
        "DF": {"por_ug": {"160336": ug(0.0), "167336": ug(0.0)}}}}
    et.aplicar(regua, D(2026, 11, 27), MARCOS, [])
    a, d = regua["por_omds"]["AGR"], regua["por_omds"]["DF"]
    assert (a["estado"]["cod"], a["estado"]["n_ug"], a["estado"]["de_ug"], a["semaforo"]) == ("FORA", 2, 2, "VERMELHO")
    assert a["estado"]["valor"] == 23437.14
    assert (d["estado"]["cod"], d["semaforo"]) == ("TELA_ZERADA", "VERDE")
    assert regua["total"]["fora_portaria"] == 23437.14
