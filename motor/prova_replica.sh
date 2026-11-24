#!/usr/bin/env bash
# prova_replica.sh <om.json da outra OM> <pasta da copia> [hoje] — v2.3 (replicavel).
# Monta uma COPIA deste repositorio como ficaria para outra OM (config/om.json trocado, dados/ vazio) e roda o portao 0
# (config), a suite, os portoes 3 a 5 com o extrato vazio e valido (tests/dados/extrato_vazio.json) e, salvo
# REPLICA_NAVEGADOR=0, o navegador headless. Prova que o codigo-mae e replicavel antes de alguem copiar (licao do
# Segundo Cerebro de 24/11/2026: o teste de ouro prova a OM de origem, nao a replica). Nada aqui publica.
set -euo pipefail
CONFIG="$(cd "$(dirname "${1:?om.json da outra OM}")" && pwd)/$(basename "$1")"
DEST="${2:?pasta da copia}"
HOJE="${3:-$(TZ=America/Sao_Paulo date +%Y-%m-%d)}"
cd "$(dirname "$0")/.."
mkdir -p "$DEST"
git ls-files | grep -v '^dados/' | tar -cf - -T - | tar -xf - -C "$DEST"
cp "$CONFIG" "$DEST/config/om.json"
mkdir -p "$DEST/dados"
cd "$DEST"
python motor/verificar_config.py --hoje "$HOJE"
python -m pytest tests -q -rs
PORTAO_EXTRATO=tests/dados/extrato_vazio.json bash motor/portao.sh prova "$HOJE"
if [ "${REPLICA_NAVEGADOR:-1}" = "1" ]; then python motor/prova_navegador.py --saida prova; fi
echo "REPLICA: ok ($(python -c "import json;print(json.load(open('config/om.json',encoding='utf-8'))['id'])"), dados/ vazio, hoje $HOJE)"
