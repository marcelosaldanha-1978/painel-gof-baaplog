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

- `execucao/` — **extrato sem pessoa** da execução (TG, conta 522920101, UG 160xxx e 167xxx): NE, UG, data, valor, modalidade e o nível do vínculo com os pregões. O CSV do Tesouro Gerencial, que tem favorecido, nunca entra neste repositório.
- `pncp/` — fichas dos 12 processos da carteira (PNCP e Compras.gov), semanais.
- `carteira_processos.json`, `kpis_painel.json` — carteira e KPI do Painel da planilha GCALC, relidos a cada montagem pela conta de serviço só de leitura (`gof_planilha.py`).
- `portal/` — extrato sem pessoa do Portal da Transparência (janela de 10 dias úteis por dia; carga desde 01/01), reserva do B1.
- `conferencia/` — confronto semanal planilha × portais (`ultimo.json` entra no B4); a gravação do que o portal prova é feita fora daqui, pela tarefa semanal do Claude.
- `pendencias_coordenador.json` — pendências do coordenador, com a data da última edição visível no painel.
- `capacidade/` — capacidade imediata de empenho das 6 UASG por fontes oficiais (Compras.gov.br, módulo ARP, e Contratos.gov.br), sem listas das SALC. O saldo de ata é calculado aqui: registrado × preço − empenhado no TG (`insumo_tg.json`, sem pessoa). Desde a v0.2 separa o item registrado **por valor** (preço unitário até R$ 1,00) do registrado por quantidade, lista os 5 maiores itens por OMDS e classifica o empenhado fora da coleta em 5 classes. **Ainda não entra no painel.**
- `encerramento/` — leituras do fim do exercício tiradas do TG por relatórios próprios, **sem pessoa** (`ultimo.json`): NE de 2026 a liquidar há mais de 60 dias (Diretriz de Encerramento) e há mais de 90 dias (SAG), RPNP por ano de origem e bloqueio, crédito em tela por UGR, saldo a liquidar que não pode ir para RPNP (diárias; outras a confirmar pelo subitem) e saldos irrisórios. Atualização **manual**, a cada exportação do TG, até a ponte do passo 7 do plano: a data da posição aparece no bloco.
- `painel/<data>/` — cada montagem (dados.json, index.html, atas do PNCP, SHA256SUMS); `painel/ultimo/` é a vigente.

## Bloco «Encerramento do exercício»

Mostra os marcos da Portaria SEF/C Ex nº 399, de 24/09/2026 (Diretriz e Calendário para o Encerramento do Exercício Financeiro de 2026), com a contagem de **dias úteis** até cada um, descontados sábados, domingos e os feriados nacionais de 20/11 e 25/12: 25/11 (data-limite de NE da UGE), 26/11 (recolhimento pela UGR), 03/12 e 04/12 (crédito remanejado e última NC), 15/12 (fase interna do PCA 2027), 23/12 (fim da indicação de RPNP) e 30/12 (RPNP até 2023). Os marcos estão em `MARCOS_ENCERRAMENTO`, no `motor/gof_painel.py`; datas «estimadas» do calendário podem mudar por mensagem da D Cont e têm de ser revistas ali. Abaixo dos marcos vêm as leituras de `dados/encerramento/ultimo.json`.

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
