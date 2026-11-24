# -*- coding: utf-8 -*-
"""
verificar_saida.py (v1, 07nov2026) — portões 4 e 5 do PLANO v2.4 (D7 revista, D12 revista).

Verifica a saída de uma montagem antes de publicar:
  5. nenhum dado pessoal: nenhum CPF (formatado ou só dígitos com máscara), nenhuma chave `favorecido`, nenhum
     texto de NE (`observacao`), nenhum contato da planilha (`contato`, `telefone`, `email`);
  4. o JSON embutido no index.html é idêntico ao dados.json e o hash do rodapé é o sha256 do JSON canônico;
  -  a página não faz pedido externo (nenhum http:// ou https:// fora do JSON embutido) e tem menos de 2 MB.
Sai com código 1 em qualquer falha. Uso: python verificar_saida.py --saida <pasta com dados.json e index.html>
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gof_config as cfg  # noqa: E402

RE_CPF = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)|(?<!\d)\*{3}\.\d{3}\.\d{3}-\*{2}(?!\d)")
RE_CPF_INTEIRO = re.compile(r"(?<![\d*])\d{3}\.\d{3}\.\d{3}-\d{2}(?![\d*])")
RE_CPF_SO_DIGITOS = re.compile(r"(?<![\d*])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\d*])")
CAMPOS_PESSOA = ("favorecido", "fornecedor", "documento", "objeto")


def textos_de_pessoa(obj, acc):
    """Valores dos campos de pessoa, onde CPF sem pontuação também conta (no resto da página, 11 dígitos podem ser hash)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in CAMPOS_PESSOA and isinstance(v, str):
                acc.append(v)
            textos_de_pessoa(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            textos_de_pessoa(v, acc)
    return acc
CHAVES_PROIBIDAS = ("favorecido", "codigoFavorecido", "observacao", "contato", "telefone", "email", "cpf")
LIMITE_BYTES = 2 * 1024 * 1024


def chaves(obj, acc):
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(str(k))
            chaves(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            chaves(v, acc)
    return acc


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", required=True)
    o = ap.parse_args(argv)
    s = Path(o.saida)
    dados_txt = (s / "dados.json").read_text(encoding="utf-8")
    pagina = (s / "index.html").read_text(encoding="utf-8")
    dados = json.loads(dados_txt)
    falhas = []
    # 5. dado pessoal (o config da OM pode liberar o favorecido; CPF inteiro só com «cpf: completo»)
    dp = cfg.dados_pessoais()
    padrao = None if (dp["favorecido"] and dp["cpf"] == "completo") else (RE_CPF_INTEIRO if dp["favorecido"] else RE_CPF)
    for nome, txt in (("dados.json", dados_txt), ("index.html", pagina)):
        m = padrao.search(txt) if padrao else None
        if m:
            falhas.append("%s contém padrão de CPF" % nome)
    if dp["favorecido"] and dp["cpf"] != "completo" and any(RE_CPF_SO_DIGITOS.search(x) for x in textos_de_pessoa(dados, [])):
        falhas.append("dados.json tem CPF inteiro (sem máscara) em campo de pessoa")
    proibidas = {c.lower() for c in CHAVES_PROIBIDAS} - ({"favorecido"} if dp["favorecido"] else set())
    ruins = sorted(k for k in chaves(dados, set()) if k.lower() in proibidas)
    if ruins:
        falhas.append("dados.json tem chave proibida: " + ", ".join(ruins))
    # 4. JSON embutido = dados.json; hash do rodape
    m = re.search(r'<script type="application/json" id="dados">(.*?)</script>', pagina, re.S)
    if not m:
        falhas.append("index.html sem o bloco de dados embutido")
    else:
        emb = json.loads(m.group(1).replace("<\\/", "</"))
        if emb != dados:
            falhas.append("JSON embutido difere do dados.json")
        canon = json.dumps(dados, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        h = hashlib.sha256(canon.encode("utf-8")).hexdigest()
        if h not in pagina:
            falhas.append("hash do rodapé não é o sha256 do JSON canônico")
    # pedido externo e tamanho
    fora = re.sub(r'<script type="application/json" id="dados">.*?</script>', "", pagina, flags=re.S)
    if "http://" in fora or "https://" in fora:
        falhas.append("index.html faz referência externa (http/https) fora do JSON")
    tam = (s / "index.html").stat().st_size
    if tam > LIMITE_BYTES:
        falhas.append("index.html com %d bytes (limite %d)" % (tam, LIMITE_BYTES))
    if falhas:
        print("VERIFICACAO: %d falha(s)" % len(falhas))
        for f in falhas:
            print("  - " + f)
        return 1
    pessoal = ("favorecido liberado pelo config; CPF %s" % dp["cpf"]) if dp["favorecido"] else "sem dado pessoal"
    print("VERIFICACAO: ok (%s; JSON embutido e hash conferem; sem pedido externo; %d bytes)" % (pessoal, tam))
    return 0


if __name__ == "__main__":
    sys.exit(main())
