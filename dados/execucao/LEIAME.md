# Execução (TG) — extrato SEM PESSOA

Uma linha por NE: documento, UG, data de emissão, valor (conta 522920101, Movim. Líquido > 0), modalidade e o resultado
do vínculo NE -> pregão (nível, pregão, candidatos). **Não traz favorecido nem a descrição da NE** (D6/D7: o CSV do TG
com pessoa fica fora do repositório). É a entrada do painel na nuvem (workflow «GOF - painel»).

- 2026-11-06: gerado em 07/11/2026 a partir dos 6 CSV do TG exportados em 06/11 (pasta do projeto, LOG-127), com as
  fichas PNCP de 07/11 (vínculo v1.2). Os sha256 dos CSV de origem estão no campo `origem`.
- Alvo (PLANO v2.1, passo 4): a subscrição diária do R1 no TG chega ao Drive pela ponte e o extrato é gerado lá, sem PC.
