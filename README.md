# Painel GOF-BaApLog

Painel de **Gestão Orçamentária e Financeira da BaApLog**: execução orçamentária das 6 OMDS (BaApLog, BCMS, BMSA, ECT, DCMun e 1º D Sup) com o módulo GCALC (carteira de licitações, Lei 14.133/2021). Publicado automaticamente pelo GitHub Actions no GitHub Pages, sem computador ligado e sem pessoa na rotina.

**Página:** `https://marcelosaldanha-1978.github.io/painel-gof-baaplog/` · histórico das montagens em `historico/`.

## Como funciona

| Etapa | Workflow | Quando |
|---|---|---|
| Montagem e publicação | `montagem.yml` | todo dia às 07:33 e 12:33 (Brasília), ou por disparo |
| Fichas PNCP (pregões, atas, fornecedores) | `fichas-pncp.yml` | segunda 07:17 |
| Vigia (montagem parada, dado parado, lembrete do TG em outubro) | `vigia.yml` | segunda e quinta 08:41 |
| Confronto planilha × PNCP/Compras.gov (só leitura) | `conferencia.yml` | segunda 08:03 |
| Capacidade imediata de empenho (atas, saldo por item e contratos por API pública) | `capacidade.yml` | semanal, ou por disparo |
| Portão (CI) | `ci.yml` | a cada push |

A montagem só publica se passar nos **portões**: suíte de testes, lint, auditoria dos workflows (zizmor), recálculo independente de todos os números (tolerância R$ 0,01), verificador de saída (nenhum dado pessoal, JSON embutido = `dados.json`, hash do rodapé, sem pedido externo, < 2 MB) e navegador headless (0 erro de JS, sem rolagem lateral a 390 px).

## Fontes e dados (`dados/`)

- `liquidacao/ultimo.json` — empenhado, liquidado, a liquidar e +60 dias por UG e OMDS (mesma ponte do B1).
- `execucao/` — **extrato sem pessoa** da execução, **gerado todo dia útil pela ponte do TG (P-041, desde 23/11/2026)**: as assinaturas do TG chegam por e-mail; o Apps Script `v2PonteTG` do GOF (06h e 11h) grava na pasta privada `PONTE_TG_SEM_PESSOA` do Drive (sem favorecido); a montagem lê o par mais recente (`motor/gof_ponte_tg.py`), confere líquido = item 23 e gera o extrato. Execução (TG, conta 522920101, UG 160xxx e 167xxx): NE, UG, data, valor, modalidade e o nível do vínculo com os pregões. O CSV do Tesouro Gerencial, que tem favorecido, nunca entra neste repositório.
- `pncp/` — fichas dos 12 processos da carteira (PNCP e Compras.gov), semanais.
- `carteira_processos.json`, `kpis_painel.json` — carteira e KPI do Painel da planilha GCALC, relidos a cada montagem pela conta de serviço só de leitura (`gof_planilha.py`).
- `portal/` — extrato sem pessoa do Portal da Transparência (janela de 10 dias úteis por dia; carga desde 01/01), reserva do B1.
- `conferencia/` — confronto semanal planilha × portais (`ultimo.json` entra no B4); a gravação do que o portal prova é feita fora daqui, pela tarefa semanal do Claude.
- `pendencias_coordenador.json` — pendências do coordenador, com a data da última edição visível no painel.
- `capacidade/` — capacidade imediata de empenho das 6 UASG por fontes oficiais (Compras.gov.br, módulo ARP, e Contratos.gov.br), sem listas das SALC. O saldo de ata é calculado aqui: registrado × preço − empenhado no TG (`insumo_tg.json`, sem pessoa). Desde a v0.2 separa o item registrado **por valor** (preço unitário até R$ 1,00) do registrado por quantidade, lista os 5 maiores itens por OMDS e classifica o empenhado fora da coleta em 5 classes. **Ainda não entra no painel.**
- `encerramento/` — **`regua.json`: crédito em tela, vencido (piso e teto) e RPNP por UG e por OMDS, gerado todo dia útil desde 23/11/2026** (3 assinaturas do TG: «REGUA CREDITO E RPNP POR UG», «CREDITO EM TELA POR NC» — ZIP, o CSV cruzado tem 62 MB — e «CREDITO POR NC MOVIMENTO 2026»; o `v2PonteTG` copia para a pasta privada e `motor/gof_regua_tg.py` calcula). Trava: a soma das células por NC tem de fechar com o crédito disponível da régua em cada UG; se não fechar, mantém a régua anterior. Vencido = prazo escrito na NC anterior à data de referência («empenho imediato» conta como vencido); o piso não rastreia ajuste de ND da própria UG até a NC de origem (mais conservador que a auditoria manual). `ultimo.json` (+60/+90 dias, RPNP por ano, irrisórios) continua manual, a cada exportação; `referencia_1rm` (planilha da 1ª RM de 10/11) é fixa.
- `dispensa/` — leitura **sem pessoa** do empenhado em dispensa por valor (Lei nº 14.133/2021, art. 75, I e II), por UG e subitem da natureza de despesa, contra o teto do ano (`ultimo.json`; origem e limites em `dispensa/LEIAME.md`). Atualização manual a cada exportação do TG.
- `painel/<data>/` — cada montagem (dados.json, index.html, atas do PNCP, SHA256SUMS); `painel/ultimo/` é a vigente.

## Blocos «Capacidade de empenho em atas (teto)» e «Limite de dispensa por subitem (indício)»

Publicados em 11/11/2026 por decisão do coordenador (`motor/gof_painel.py`: `bloco_capacidade` e `bloco_dispensa`; argumentos `--capacidade` e `--dispensa`, com os caminhos de `dados/` por padrão; sem o arquivo, o bloco não aparece).

- **Capacidade em atas:** saldo de ata por OMDS a partir de `dados/capacidade/ultimo.json` (registrado, empenhado no TG, saldo, registrado por quantidade e por valor, o que vence até 31/12), os três maiores saldos de item por OMDS e o empenhado do ano fora da coleta, por classe. O total é somado no motor a partir das OMDS. **É teto, não crédito**: saldo de ata não é recurso nem processo pronto; item registrado «por valor» infla o saldo e vai em coluna própria.
- **Limite de dispensa por subitem:** empenhado em dispensa do art. 75, I ou II, por UG e subitem, comparado com o teto do inciso; lista os subitens com 70% ou mais do teto. **É indício, não prova de fracionamento**: subitem não é ramo de atividade; manutenção de veículos tem regra própria (art. 75, § 7º); medido uma vez, sem conferência independente. O motor reconta os subitens acima do teto em vez de confiar no arquivo.
- Nenhum dos dois blocos traz favorecido, CPF, CNPJ ou texto de NE; o verificador de saída e a prova de navegador (390 e 1280 px) cobrem os dois.

## A página (v2.1, 23/11/2026 — «Encerramento do exercício de 2026»)

Organizada pela Portaria SEF/C Ex nº 399, de 24/09/2026 (Diretriz e Calendário do Encerramento do Exercício de 2026), em padrão visual Apple (tipografia do sistema, claro/escuro automático, cor só para estado e sempre com texto):

1. **Barra fixa** com atalhos para Prazos, «As seis juntas» e cada OMDS (ponto na cor da situação).
2. **Prazos** — marcos do Calendário com contagem de **dias úteis** (sem sábados, domingos e feriados nacionais); o próximo em destaque. Marcos em `MARCOS_ENCERRAMENTO` (`motor/gof_painel.py`); datas «estimadas» podem mudar por mensagem da D Cont.
3. **As seis OMDS juntas** (itens 6.a, 6.d e 6.b) — crédito em tela e vencido, % liquidado, a liquidar há +60 dias, RPNP; comparação com a 1ª RM recolhível.
4. **Cada OMDS, UG 160 e UG 167** — com o brasão (`motor/brasoes.json`, PNG 128 px embutidos); por UG: **crédito em tela** em destaque (vermelho se vencido ≥ R$ 1.000), empenhado (NE, % do recebido), liquidado (barra), a liquidar (+60 dias), restos a pagar. Cia Cmdo e H Cmp aparecem na UG 160238.
5. **Rodapé** — norma balizadora; «Fontes e método» recolhível (arquivos, sha256, regras, hash dos dados).

Suprimidos da página e mantidos no `dados.json`: carteira GCALC, atas, NE a verificar, confronto, pendências, capacidade em atas e dispensa.

## Para leitura por máquina

A página monta os números por JavaScript; quem lê sem executar script (agentes, busca, WebFetch) deve usar `https://marcelosaldanha-1978.github.io/painel-gof-baaplog/dados.json`, o mesmo JSON embutido na página (hash no rodapé).

## Regras que o código cumpre

- **Vínculo NE → pregão (regra v1.2):** CONFIRMADO, PROVÁVEL, AMBÍGUO (fora das somas), CITADO SEM ATA e ALERTA; nunca somados entre si.
- **Fonte do B1:** Tesouro Gerencial; o Portal da Transparência entra como reserva declarada quando o TG parar mais de 2 dias úteis e o Portal estiver mais atual. No Portal, `modalidade` é a de aplicação, não a de licitação.
- **Idade do dado em dias úteis** (seg a sex, sem feriados), na faixa de cada bloco; a faixa fica vermelha com o B1 parado.
- **Sem dado pessoal por construção;** o verificador barra CPF, favorecido e texto de NE.

## Rodar localmente

```bash
pip install -r requirements.txt
PORTAO_ATAS_OFFLINE=1 bash motor/portao.sh saida 2026-11-07   # montagem + recálculo + verificador, sem rede
python -m pytest tests -q
```

Governança, decisões (D1 a D20) e plano vivem na pasta do projeto (OneDrive, PLANO v2.4); este repositório é a fonte única do **código** do painel.
