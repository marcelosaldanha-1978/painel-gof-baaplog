# dados/dispensa

Leitura SEM PESSOA do empenhado em dispensa por valor (Lei nº 14.133/2021, art. 75, I e II), por UG e por subitem da natureza de despesa, comparado com o teto do ano. `ultimo.json` é lido pelo `gof_painel.py` (bloco «Limite de dispensa por subitem»). Publicação decidida pelo coordenador em 11/11/2026.

**De onde vem.** Relatório próprio do Tesouro Gerencial «GOF-BaApLog-CONF-Dispensas por subitem», cópia (com o ano trocado) da consulta que o 1º CGCFEx usa para o mesmo fim. O valor é o empenhado líquido de cada NE; o inciso vem da compra, pelos dados abertos do Compras.gov.br. O CSV do TG e o cruzamento ficam fora do repositório (têm texto de documento); aqui ficam só os hashes (`csv_sha256`, `derivado_sha256`).

**O que é e o que não é.** É indício: subitem não é «ramo de atividade». Não há favorecido, CPF, CNPJ nem texto de NE neste arquivo. Os limites da leitura vão no campo `limites` e aparecem no painel.

**Posição do SIAFI (`posicao_siafi`).** A linha «Dados do DW refletem o SIAFI até …» do relatório, não a hora da execução.

**Atualização.** Manual, a cada exportação do TG, até a ponte do passo 7.
