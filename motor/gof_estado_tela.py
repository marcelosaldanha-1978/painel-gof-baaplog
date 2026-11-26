"""Estado do crédito em tela de cada UG pela regra da Portaria de encerramento (decisão do usuário de 26/11/2026).

A Portaria manda a UGR recolher todo o crédito que restar em tela na data do evento 8 (em 2026, 26/11). Depois dela,
qualquer saldo em tela é irregular, vencido ou não; só escapa o crédito com prazo escrito ainda futuro (remanejados com
NE até 03/12, NC tardia) ou com prorrogação formal da UGR registrada no config («prorrogacoes_tela»).

Escala, da mais grave para a mais tranquila (nivel):
  5 FORA          «Fora da Portaria há N dias»   saldo em tela depois da data de recolhimento, sem prazo futuro
  4 PRAZO_HOJE    «Prazo hoje: recolher»         hoje é a data de recolhimento e há saldo sem prazo futuro
  4 RECOLHER_ATE  «Recolher até dd/mm»           há vencido e a data de recolhimento ainda não chegou
  3 VERIFICAR     «Verificar»                    vencido certo zero, mas o possível (teto) passa de zero
  2 NO_PRAZO      «No prazo até dd/mm»           há saldo, todo dentro de prazo (escrito, prorrogado ou até o recolhimento)
  1 RESIDUO       «Resíduo a recolher»           menos de R$ 10 em tela
  0 TELA_ZERADA   «Tela zerada»                  cumpre a Portaria
A etiqueta da OMDS é a pior das suas UG; o valor vai sempre ao lado. Não há régua de valor (as antigas de R$ 1 mil,
10 mil e 100 mil caíram); valor a partir de MATERIAL sai em negrito, sem mudar o estado.
"""
import datetime as dt

RESIDUO = 10.0
MATERIAL = 100000.0
COR = {5: "red", 4: "orange", 3: "amber", 2: "blue", 1: "gray", 0: "green"}
SEMAFORO = {5: "VERMELHO", 4: "AMARELO", 3: "AMARELO", 2: "VERDE", 1: "VERDE", 0: "VERDE"}


def data_recolhimento(marcos):
    """Data do evento 8 («a UGR recolhe todo o crédito que restar em tela») no calendário do config."""
    for data, ev, texto in marcos:
        if ev.replace("ev. ", "").strip() == "8" or "recolhe todo o cr" in texto.lower():
            return dt.date.fromisoformat(data)
    return None


def _dbr(d):
    return d.strftime("%d/%m")


def estado_ug(x, hoje, data_dado, d_rec, prorrogada_ate=None):
    """x = linha da UG na régua (em_tela, vencido_piso, vencido_teto, tela_no_prazo, prazo_ate). -> dict do estado."""
    s = x.get("em_tela") or 0.0
    piso, teto = x.get("vencido_piso") or 0.0, x.get("vencido_teto") or 0.0
    no_prazo = min(s, x.get("tela_no_prazo") or 0.0)
    ate = dt.date.fromisoformat(x["prazo_ate"]) if x.get("prazo_ate") else None

    def e(cod, nivel, rotulo, valor, faixa=None, **extra):
        r = {"cod": cod, "nivel": nivel, "cor": COR[nivel], "rotulo": rotulo, "valor": round(valor, 2),
             "material": valor >= MATERIAL}
        if faixa:
            r["faixa"] = [round(faixa[0], 2), round(faixa[1], 2)]
        r.update(extra)
        return r

    if s <= 0.005:
        return e("TELA_ZERADA", 0, "Tela zerada", 0.0)
    if s < RESIDUO:
        return e("RESIDUO", 1, "Resíduo a recolher", s)
    if prorrogada_ate and prorrogada_ate >= hoje:
        return e("NO_PRAZO", 2, "No prazo até %s" % _dbr(prorrogada_ate), s, ate=prorrogada_ate.isoformat(),
                 motivo="prorrogação da UGR")
    if d_rec and data_dado >= d_rec:
        fora = s - no_prazo
        if fora >= RESIDUO:
            dias = max(1, (hoje - d_rec).days)
            return e("FORA", 5, "Fora da Portaria há %d dia%s" % (dias, "" if dias == 1 else "s"), fora, dias=dias)
        if fora > 0.005:
            return e("RESIDUO", 1, "Resíduo a recolher", fora)
        return e("NO_PRAZO", 2, "No prazo até %s" % _dbr(ate), s, ate=ate.isoformat(), motivo="prazo escrito na NC")
    if d_rec and hoje >= d_rec:  # dado de antes do prazo, mas o prazo é hoje ou já passou: todo saldo sem prazo futuro
        resta = s - no_prazo
        if resta >= RESIDUO:
            if hoje == d_rec:
                return e("PRAZO_HOJE", 4, "Prazo hoje: recolher", resta, (piso, teto) if teto > 0.005 else None)
            dias = (hoje - d_rec).days
            return e("FORA", 5, "Fora da Portaria há %d dia%s" % (dias, "" if dias == 1 else "s"), resta, dias=dias)
        if resta > 0.005:
            return e("RESIDUO", 1, "Resíduo a recolher", resta)
        return e("NO_PRAZO", 2, "No prazo até %s" % _dbr(ate), s, ate=ate.isoformat(), motivo="prazo escrito na NC")
    if piso > 0.005:
        return e("RECOLHER_ATE", 4, "Recolher até %s" % _dbr(d_rec) if d_rec else "Recolher", piso, (piso, teto))
    if teto > 0.005:
        return e("VERIFICAR", 3, "Verificar", teto, (0.0, teto))
    lim = min(d for d in (ate, d_rec) if d) if (ate or d_rec) else None
    return e("NO_PRAZO", 2, "No prazo até %s" % _dbr(lim) if lim else "No prazo", s,
             ate=lim.isoformat() if lim else None)


def aplicar(regua, hoje, marcos, prorrogacoes=()):
    """Acrescenta «estado» em cada UG e em cada OMDS da régua (e troca o «semaforo» da OMDS). Devolve a régua."""
    if not regua or not regua.get("por_omds"):
        return regua
    d_rec = data_recolhimento(marcos)
    data_dado = dt.date.fromisoformat(regua.get("data_dado") or hoje.isoformat())
    prorr = {str(p["ug"]): dt.date.fromisoformat(p["ate"]) for p in (prorrogacoes or [])}
    fora_total = 0.0
    for r in regua["por_omds"].values():
        piores = []
        for ug, x in (r.get("por_ug") or {}).items():
            x["estado"] = estado_ug(x, hoje, data_dado, d_rec, prorr.get(ug))
            piores.append(x["estado"])
            if x["estado"]["cod"] == "FORA":
                fora_total += x["estado"]["valor"]
        if not piores:
            continue
        top = max(p["nivel"] for p in piores)
        mesmo = [p for p in piores if p["nivel"] == top]
        est = dict(mesmo[0])
        est.update({"valor": round(sum(p["valor"] for p in mesmo), 2), "n_ug": len(mesmo), "de_ug": len(piores)})
        est["material"] = est["valor"] >= MATERIAL
        if len({p["rotulo"] for p in mesmo}) > 1:  # ex.: «Fora há 1 dia» e «há 2 dias»: fica o mais antigo
            est["rotulo"] = max(mesmo, key=lambda p: p.get("dias", 0))["rotulo"]
        r["estado"] = est
        r["semaforo"] = SEMAFORO[top]
    regua.setdefault("total", {})["fora_portaria"] = round(fora_total, 2)
    regua["regra_estado"] = ("etiqueta pela Portaria: a UGR recolhe todo o crédito em tela em %s; depois disso, saldo sem prazo "
                             "escrito futuro (ou prorrogação registrada) fica «fora da Portaria»; menos de R$ %d é resíduo"
                             % (_dbr(d_rec) if d_rec else "data do calendário", int(RESIDUO)))
    return regua
