# Execução (TG) — extrato SEM PESSOA

**Versão 2 (desde 09/11/2026, LOG-181; P-063 e P-064):** o campo `valor` é o **empenhado LÍQUIDO** (contas 6229201xx =
item 23 «despesas empenhadas» do TG: emissão + reforço − anulação) e `valor_emitido` é a emissão bruta (522920101).
O total líquido é conferido ao centavo com o item 23 na geração (`motor/gof_extrato_tg.py`) e de novo no recálculo
independente (`total_item23`). O vínculo NE → pregão vem da **chave SIASG** da NE (campo «NE - Informação Complementar»,
regra 2.0, `motor/vinculo_siasg.py`); o campo `chave` traz UASG-modalidade-número/ano da compra (dado público do SIASG).
- 2026-11-09: 3.045 NE das 12 UG; líquido R$ 49.900.235,86; emitido R$ 64.053.671,89; 465 NE anuladas por inteiro;
  185 NE com chave de 6 pregões da carteira (R$ 492.252,09 líquidos). Origem: os dois CSV do TG de 09/11 (sha256 em `origem`).

**Versão 1 (até 06/11/2026), mantida no histórico:** `valor` era a conta 522920101 (emissão bruta), não o empenhado.

Uma linha por NE: documento, UG, data de emissão, valor (conta 522920101, Movim. Líquido > 0), modalidade e o resultado
do vínculo NE -> pregão (nível, pregão, candidatos). **Não traz favorecido nem a descrição da NE** (D6/D7: o CSV do TG
com pessoa fica fora do repositório). É a entrada do painel na nuvem (workflow «GOF - painel»).

- 2026-11-06: gerado em 07/11/2026 a partir dos 6 CSV do TG exportados em 06/11 (pasta do projeto, LOG-127), com as
  fichas PNCP de 07/11 (vínculo v1.2). Os sha256 dos CSV de origem estão no campo `origem`.
- Alvo (PLANO v2.1, passo 4): a subscrição diária do R1 no TG chega ao Drive pela ponte e o extrato é gerado lá, sem PC.
