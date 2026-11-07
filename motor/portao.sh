#!/usr/bin/env bash
# portao.sh <pasta_saida> [hoje] — monta o painel com os dados versionados e roda os portoes 3, 4 e 5 (PLANO v2.4, D12).
# Usado pelo CI (prova) e pela montagem diaria (antes de publicar). Sai com erro em qualquer portao reprovado.
set -euo pipefail
SAIDA="${1:?pasta de saida}"
HOJE="${2:-$(TZ=America/Sao_Paulo date +%Y-%m-%d)}"
cd "$(dirname "$0")/.."
mkdir -p "$SAIDA"
ATAS="$SAIDA/atas_pncp_${HOJE}.json"
if [ "${PORTAO_ATAS_OFFLINE:-}" = "1" ]; then
  # prova sem rede: reaproveita a ultima coleta de atas versionada
  cp "$(ls -1 dados/painel/*/atas_pncp_*.json | sort | tail -1)" "$ATAS"
fi
DATA_CARTEIRA="$(python -c "import json;print(json.load(open('dados/carteira_processos.json'))['lido_em'])")"
python motor/gof_painel.py \
  --extrato dados/execucao/ultimo.json --fichas dados/pncp/ultimo.json \
  --carteira dados/carteira_processos.json --data-carteira "$DATA_CARTEIRA" \
  --kpis dados/kpis_painel.json --pendencias dados/pendencias_coordenador.json \
  --atas "$ATAS" --saida "$SAIDA" --hoje "$HOJE"
python motor/recalculo_independente.py --dados "$SAIDA/dados.json" --extrato dados/execucao/ultimo.json \
  --carteira dados/carteira_processos.json --atas "$ATAS" --hoje "$HOJE"
python motor/verificar_saida.py --saida "$SAIDA"
