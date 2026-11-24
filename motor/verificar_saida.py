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
# CPF inteiro com separador (ponto, espaço, travessão, hífen ou barra antes do DV): vale para o texto todo
RE_CPF_INTEIRO = re.compile(r"(?<![\d*])\d{3}[\s.\u2013\u2014]\d{3}[\s.\u2013\u2014]\d{3}[\s.\-\u2013\u2014/]\d{2}(?![\d*])")
# CPF inteiro também sem separador: só nos campos de texto (no resto, 11 dígitos podem ser hash)
RE_CPF_SO_DIGITOS = cfg._RE_CPF
CAMPOS_PESSOA = ("favorecido", "fornecedor", "documento", "objeto", "ressalva", "ressalvas", "ressalva_favorecido",
                 "texto", "nome", "avisos", "regra")
# onde a chave «favorecido» pode aparecer quando o config libera (detalhes por NE e contratos)
CAMINHOS_FAVORECIDO = (("liquidacao", "por_ne"), ("rp_por_ano", "por_ne"))


def textos_de_pessoa(obj, acc, dentro=False):
    """Textos dos campos de pessoa e de ressalva (onde CPF sem separador também conta)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            alvo = dentro or k in CAMPOS_PESSOA
            if alvo and isinstance(v, str):
                acc.append(v)
            textos_de_pessoa(v, acc, alvo)
    elif isinstance(obj, list):
        for v in obj:
            if dentro and isinstance(v, str):
                acc.append(v)
            textos_de_pessoa(v, acc, dentro)
    return acc


def favorecido_fora_do_lugar(obj, caminho=()):
    """Caminhos onde a chave «favorecido» aparece fora dos detalhes autorizados."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == "favorecido" and caminho[:2] not in CAMINHOS_FAVORECIDO:
                out.append("/".join(caminho + (k,)))
            out += favorecido_fora_do_lugar(v, caminho + (k,))
    elif isinstance(obj, list):
        for v in obj:
            out += favorecido_fora_do_lugar(v, caminho)
    return out
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
    for nome, txt in (("dados.json", dados_txt), ("index.html", pagina)):
        if (RE_CPF_INTEIRO if dp["favorecido"] else RE_CPF).search(txt):
            falhas.append("%s contém padrão de CPF" % nome)
    if dp["favorecido"] and any(RE_CPF_SO_DIGITOS.search(x) for x in textos_de_pessoa(dados, [])):
        falhas.append("dados.json tem CPF inteiro (sem máscara) em campo de texto")
    if dp["favorecido"]:
        fora = favorecido_fora_do_lugar(dados)
        if fora:
            falhas.append("chave favorecido fora dos detalhes autorizados: " + ", ".join(fora[:5]))
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
    pessoal = "favorecido liberado pelo config; CPF mascarado" if dp["favorecido"] else "sem dado pessoal"
    print("VERIFICACAO: ok (%s; JSON embutido e hash conferem; sem pedido externo; %d bytes)" % (pessoal, tam))
    return 0


if __name__ == "__main__":
    sys.exit(main())
