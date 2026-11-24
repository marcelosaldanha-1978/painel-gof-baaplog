"""Etapa A (v2.2): as tabelas derivadas de config/om.json são idênticas às constantes fixas da v2.1 (inventário v1.0, §3),
inclusive na ordem."""
import datetime as dt

import gof_config as cfg

# valores fixos da release v2.1-encerramento (commit ea7aaea), copiados do código
V21_REGUA_OM = {"238": "Cmdo BaApLog", "246": "DC Mun", "304": "BMSA", "307": "1º D Sup", "321": "ECT", "329": "BCMS"}
V21_REGUA_ORDEM = ["Cmdo BaApLog", "BCMS", "BMSA", "ECT", "DC Mun", "1º D Sup"]
V21_RECALC_UGS = {"160238": "BaApLog", "167238": "BaApLog", "160329": "BCMS", "167329": "BCMS", "160304": "BMSA",
                  "167304": "BMSA", "160321": "ECT", "167321": "ECT", "160246": "DCMun", "167246": "DCMun",
                  "160307": "1oDSup", "167307": "1oDSup"}
V21_PAINEL_OMDS = ["BaApLog", "BCMS", "BMSA", "ECT", "DCMun", "1oDSup"]
V21_PAINEL_ROTULO = {"1oDSup": "1º D Sup"}
V21_PONTE_ROTULO = {"BaApLog": "Cmdo BaApLog", "BCMS": "BCMS", "BMSA": "BMSA", "ECT": "ECT", "DCMun": "DC Mun",
                    "1oDSup": "1º D Sup"}
V21_CAPACIDADE = {"160238": "Cmdo BaApLog", "160246": "DC Mun", "160304": "BMSA", "160307": "1º D Sup", "160321": "ECT",
                  "160329": "BCMS"}
V21_CONFERENCIA = {"160238": "BaApLog", "160329": "BCMS", "160304": "BMSA", "160321": "ECT", "160246": "DCMun",
                   "160307": "1oDSup"}
V21_TR_UGS = {"160238": "BaApLog", "160329": "BCMS", "160304": "BMSA", "160321": "ECT", "160246": "DCMun",
              "160307": "1oDSup", "167238": "BaApLog", "167329": "BCMS", "167304": "BMSA", "167321": "ECT",
              "167246": "DCMun", "167307": "1oDSup"}
V21_FERIADOS = {dt.date(2026, 11, 20), dt.date(2026, 12, 25)}
V21_FER_ANO = {dt.date(2026, 1, 1), dt.date(2026, 2, 16), dt.date(2026, 2, 17), dt.date(2026, 4, 3), dt.date(2026, 4, 21),
               dt.date(2026, 5, 1), dt.date(2026, 6, 4), dt.date(2026, 9, 7), dt.date(2026, 10, 12), dt.date(2026, 11, 2),
               dt.date(2026, 11, 15), dt.date(2026, 11, 20), dt.date(2026, 12, 25)}
V21_NOME_JS = 'var NOME={BaApLog:"Cmdo BaApLog",BCMS:"BCMS",BMSA:"BMSA",ECT:"ECT",DCMun:"DC Mun","1oDSup":"1º D Sup"};'
V21_ORDEM_JS = 'var ORDEM=["Cmdo BaApLog","BCMS","BMSA","ECT","DC Mun","1º D Sup"];'
V21_UGNOME_JS = 'var UGNOME={"160238":"Cmdo, Cia Cmdo e HCmp"};'


def _itens(d):
    return list(d.items())  # compara também a ordem


def test_tabelas_derivadas_iguais_as_da_v21():
    assert _itens(cfg.rotulo_por_sufixo()) == _itens(V21_REGUA_OM)
    assert cfg.ordem_rotulos() == V21_REGUA_ORDEM
    assert _itens(cfg.ug_para_chave_intercalado()) == _itens(V21_RECALC_UGS)
    assert cfg.chaves_omds() == V21_PAINEL_OMDS
    assert cfg.rotulos_curtos_diferentes() == V21_PAINEL_ROTULO
    assert _itens(cfg.rotulo_por_chave()) == _itens(V21_PONTE_ROTULO)
    assert _itens(cfg.uasg_para_rotulo_numerico()) == _itens(V21_CAPACIDADE)
    assert _itens(cfg.uasg_para_chave()) == _itens(V21_CONFERENCIA)
    assert _itens(cfg.ug_para_chave_160_depois_167()) == _itens(V21_TR_UGS)
    assert cfg.feriados() == V21_FERIADOS
    assert cfg.feriados_ano() == V21_FER_ANO
    assert cfg.exercicio() == 2026


def test_grafia_js_identica_ao_modelo_v21():
    assert "var NOME=%s;" % cfg.js_objeto(cfg.rotulo_por_chave()) == V21_NOME_JS
    assert "var ORDEM=%s;" % cfg.js_lista(cfg.ordem_rotulos()) == V21_ORDEM_JS
    assert "var UGNOME=%s;" % cfg.js_objeto(cfg.ug_nome()) == V21_UGNOME_JS


def test_modulos_usam_o_config():
    import gcalc_transparencia as tr
    import gof_capacidade as cap
    import gof_conferencia as conf
    import gof_painel as gp
    import gof_ponte_tg as ponte
    import gof_regua_tg as regua
    import recalculo_independente as rec
    assert regua.OM == V21_REGUA_OM and regua.ORDEM == V21_REGUA_ORDEM and regua.FER == V21_FER_ANO
    assert rec.UGS == V21_RECALC_UGS
    assert gp.OMDS == V21_PAINEL_OMDS and gp.ROTULO_OMDS == V21_PAINEL_ROTULO and gp.FERIADOS == V21_FERIADOS
    assert ponte.OMDS_ROTULO == V21_PONTE_ROTULO
    assert cap.OMDS == V21_CAPACIDADE
    assert conf.UASGS == V21_CONFERENCIA
    assert _itens(tr.UGS) == _itens(V21_TR_UGS)
