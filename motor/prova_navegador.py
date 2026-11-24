# -*- coding: utf-8 -*-
"""
prova_navegador.py (v1, 07nov2026) — portao 6 do PLANO v2.4: abre o index.html num Chromium headless (Playwright) e exige
0 erro de JS, 0 pedido externo, nenhuma rolagem lateral a 390 px, pagina < 2 MB e os 3 blocos renderizados.
Uso: python prova_navegador.py --saida <pasta com index.html>
"""
import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gof_config as cfg  # noqa: E402

# UG esperadas no bloco das OMDS: as duas de cada OMDS da OM (config/om.json); 12 na BaApLog
N_UG = len(cfg.ug_para_chave_intercalado())
N_OMDS = len(cfg.chaves_omds())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", required=True)
    o = ap.parse_args(argv)
    pagina = Path(o.saida).resolve() / "index.html"
    falhas = []
    if pagina.stat().st_size > 2 * 1024 * 1024:
        falhas.append("pagina com mais de 2 MB")
    with sync_playwright() as p:
        nav = p.chromium.launch()
        for largura in (390, 1280):
            ctx = nav.new_context(viewport={"width": largura, "height": 844})
            pg = ctx.new_page()
            erros, externos = [], []

            def _erro(e, _lista=erros):
                _lista.append(str(e))

            def _pedido(r, _lista=externos):
                if not r.url.startswith("file:"):
                    _lista.append(r.url)

            pg.on("pageerror", _erro)
            pg.on("request", _pedido)
            pg.goto(pagina.as_uri())
            pg.wait_for_timeout(300)
            if erros:
                falhas.append("%dpx: erro de JS: %s" % (largura, erros[0][:160]))
            if externos:
                falhas.append("%dpx: pedido externo: %s" % (largura, externos[0][:120]))
            sw, cw = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            if sw > cw:
                falhas.append("%dpx: rolagem lateral (%d > %d)" % (largura, sw, cw))
            # v2 (23/11/2026): página do encerramento do exercício — prazos, resumo e as 6 OMDS uma a uma (UG 160 e 167)
            for bloco in ("prazos", "resumo", "omds"):
                if not pg.evaluate("(document.getElementById('%s')||{innerHTML:''}).innerHTML.length > 100" % bloco):
                    falhas.append("%dpx: bloco %s vazio" % (largura, bloco))
            if pg.evaluate("document.querySelectorAll('#omds .ug').length") < N_UG:
                falhas.append("%dpx: menos de %d UG (%d OMDS x UG 160 e 167) no bloco das OMDS" % (largura, N_UG, N_OMDS))
            if not pg.evaluate("document.getElementById('status').textContent.includes('Fonte:')"):
                falhas.append("%dpx: cabeçalho sem a fonte dos dados" % largura)
            ctx.close()
        nav.close()
    if falhas:
        print("NAVEGADOR: %d falha(s)" % len(falhas))
        for f in falhas:
            print("  - " + f)
        return 1
    print("NAVEGADOR: ok a 390 e 1280 px (0 erro de JS, 0 pedido externo, sem rolagem lateral, blocos renderizados)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
