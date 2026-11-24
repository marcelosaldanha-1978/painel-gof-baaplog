#!/usr/bin/env bash
# portao.sh <pasta_saida> [hoje] — monta o painel com os dados versionados e roda os portoes 3, 4 e 5 (PLANO v2.4, D12).
# Usado pelo CI (prova) e pela montagem diaria (antes de publicar). Sai com erro em qualquer portao reprovado.
# Se existir dados/portal/extrato_portal.json, passa-o ao motor como reserva do B1 (D17); o recalculo confere contra a
# fonte que o motor declarou em meta.fonte_b1.
set -euo pipefail
SAIDA="${1:?pasta de saida}"
HOJE="${2:-$(TZ=America/Sao_Paulo date +%Y-%m-%d)}"
cd "$(dirname "$0")/.."
mkdir -p "$SAIDA"
# portao 0: configuracao da OM (config/om.json ou GOF_CONFIG) completa e coerente; calendario vencido so avisa
python motor/verificar_config.py --hoje "$HOJE"
ATAS="$SAIDA/atas_pncp_${HOJE}.json"
if [ "${PORTAO_ATAS_OFFLINE:-}" = "1" ]; then
  # prova sem rede: reaproveita a ultima coleta de atas versionada
  cp "$(ls -1 dados/painel/*/atas_pncp_*.json | sort | tail -1)" "$ATAS"
fi
PORTAL=()
if [ -f dados/portal/extrato_portal.json ]; then PORTAL=(--extrato-portal dados/portal/extrato_portal.json); fi
if [ -f dados/conferencia/ultimo.json ]; then PORTAL+=(--conferencia dados/conferencia/ultimo.json); fi
# blocos do GCALC (carteira, atas, pendencias) so quando ligados no config da OM (config/om.json ou GOF_CONFIG)
GCALC="$(python -c "import sys;sys.path.insert(0,'motor');import gof_config as c;print(int(c.bloco_ligado('carteira_gcalc')))")"
CARTEIRA=()
RECALC_GCALC=()
if [ "$GCALC" = "1" ]; then
  DATA_CARTEIRA="$(python -c "import json;print(json.load(open('dados/carteira_processos.json'))['lido_em'])")"
  CARTEIRA=(--fichas dados/pncp/ultimo.json --carteira dados/carteira_processos.json --data-carteira "$DATA_CARTEIRA"
            --kpis dados/kpis_painel.json --pendencias dados/pendencias_coordenador.json --atas "$ATAS")
  RECALC_GCALC=(--carteira dados/carteira_processos.json --atas "$ATAS")
fi
python motor/gof_painel.py \
  --extrato dados/execucao/ultimo.json "${CARTEIRA[@]}" \
  --saida "$SAIDA" --hoje "$HOJE" "${PORTAL[@]}"
FONTE="$(python -c "import json;print(json.load(open('$SAIDA/dados.json'))['meta']['fonte_b1'])")"
EXTRATO=dados/execucao/ultimo.json
if [ "$FONTE" = "portal" ]; then EXTRATO=dados/portal/extrato_portal.json; fi
echo "fonte do B1: $FONTE ($EXTRATO)"
python motor/recalculo_independente.py --dados "$SAIDA/dados.json" --extrato "$EXTRATO" \
  "${RECALC_GCALC[@]}" --hoje "$HOJE"
python motor/verificar_saida.py --saida "$SAIDA"
