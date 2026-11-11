# dados/encerramento

Leitura SEM PESSOA de NE de 2026 a liquidar há mais de 60 dias (Portaria SEF/C Ex nº 399/2026, Diretriz 6.d.1), por OMDS, tirada do TG por relatório próprio. `ultimo.json` é lido pelo `gof_painel.py` (bloco «Encerramento do exercício»). Atualização: manual, a cada exportação do TG, até a ponte do passo 7.

**Posição do SIAFI (`posicao_siafi`).** É a data e a hora que o próprio TG imprime no relatório («Dados do DW refletem o SIAFI até …»), não a hora em que o relatório foi executado. Nos relatórios executados em 10/11/2026 a linha diz «SIAFI até 10/11/2026 00:10:04»: o movimento vai até 09/11/2026. Até 11/11/2026 este arquivo trazia «10/11/2026 08:10», que era a hora da execução; os valores não mudaram, só o rótulo (retificação registrada no LOG-218 do projeto). Ao atualizar o `ultimo.json`, copiar a linha do TG.
