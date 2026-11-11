# dados/dispensa

Leitura SEM PESSOA do empenhado em dispensa por valor (Lei nº 14.133/2021, art. 75, I e II), por UG e por subitem da natureza de despesa, comparado com o teto do ano. `ultimo.json` é lido pelo `gof_painel.py` (bloco «Limite de dispensa por subitem»). Publicação decidida pelo coordenador em 11/11/2026.

**De onde vem (desde 11/11/2026).** Só do Tesouro Gerencial: relatório próprio «GOF-BaApLog-CONF-Dispensa por NE e subitem com valor», com item 29 (despesas empenhadas), saldo, modalidade de licitação 06 (dispensa), por NE, natureza, subitem e amparo legal (lei, artigo e inciso). Filtro, valor e inciso saem do próprio TG; não há mais cruzamento com dados abertos (a versão de 10/11 cruzava a consulta do 1º CGCFEx com o empenhado por NE e com o Compras.gov.br). O CSV do TG fica fora do repositório; aqui fica o hash (`csv_sha256`).

**O que é e o que não é.** É indício: subitem não é «ramo de atividade». Não há favorecido, CPF, CNPJ nem texto de NE neste arquivo. Os limites da leitura vão no campo `limites` e aparecem no painel.

**Posição do SIAFI (`posicao_siafi`).** A linha «Dados do DW refletem o SIAFI até …» do relatório, não a hora da execução.

**Atualização.** Manual, a cada exportação do TG, até a ponte do passo 7.
