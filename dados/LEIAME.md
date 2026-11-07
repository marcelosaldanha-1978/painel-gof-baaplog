# dados/

Estado persistente do painel (histórico por data, nunca force push). Gravado pelos workflows (`montagem.yml`, `fichas-pncp.yml`) ou por sessão a pedido (carteira, KPI, pendências — até o passo 5 do PLANO v2.4).

- `execucao/<data>/extrato.json` + `ultimo.json` — extrato sem pessoa (ver `execucao/LEIAME.md`).
- `pncp/<data>/pncp_12_processos.json` + `ultimo.json` — fichas PNCP.
- `painel/<data>/` + `ultimo/` — montagens.
- `carteira_processos.json`, `kpis_painel.json` — planilha GCALC (`lido_em` = data da leitura).
- `pendencias_coordenador.json` — `{"editado_em", "editado_por", "fonte", "itens": [...]}`.

Migrado em 07/11/2026 do ramo `gof-dados` do `claude-projects` (fichas de 07/11, extrato de 06/11, montagem de 07/11).
