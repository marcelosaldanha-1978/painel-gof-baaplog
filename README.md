# Painel GOF-BaApLog

Painel de **Gestão Orçamentária e Financeira da BaApLog**: execução orçamentária das 6 OMDS (BaApLog, BCMS, BMSA, ECT, DCMun e 1º D Sup) com o módulo GCALC (carteira de licitações, Lei 14.133/2021). Publicado automaticamente pelo GitHub Actions no GitHub Pages, sem computador ligado e sem pessoa na rotina.

**Página:** `https://marcelosaldanha-1978.github.io/painel-gof-baaplog/` · histórico das montagens em `historico/`.

## Como funciona

| Etapa | Workflow | Quando |
|---|---|---|
| Montagem e publicação | `montagem.yml` | todo dia às 07:33 e 12:33 (Brasília), ou por disparo |
| Fichas PNCP (pregões, atas, fornecedores) | `fichas-pncp.yml` | segunda 07:17 |
| Vigia (montagem parada, dado parado, lembrete do TG em outubro) | `vigia.yml` | segunda e quinta 08:41 |
| Portão (CI) | `ci.yml` | a cada push |

A montagem só publica se passar nos **portões**: suíte de testes, lint, auditoria dos workflows (zizmor), recálculo independente de todos os números (tolerância R$ 0,01), verificador de saída (nenhum dado pessoal, JSON embutido = `dados.json`, hash do rodapé, sem pedido externo, < 2 MB) e navegador headless (0 erro de JS, sem rolagem lateral a 390 px).

## Fontes e dados (`dados/`)

- `execucao/` — **extrato sem pessoa** da execução (TG, conta 522920101, UG 160xxx e 167xxx): NE, UG, data, valor, modalidade e o nível do vínculo com os pregões. O CSV do Tesouro Gerencial, que tem favorecido, nunca entra neste repositório.
- `pncp/` — fichas dos 12 processos da carteira (PNCP e Compras.gov), semanais.
- `carteira_processos.json`, `kpis_painel.json` — carteira e KPI do Painel da planilha GCALC (cópia manual até o passo 5 do plano: leitura pela conta de serviço só de leitura).
- `pendencias_coordenador.json` — pendências do coordenador, com a data da última edição visível no painel.
- `painel/<data>/` — cada montagem (dados.json, index.html, atas do PNCP, SHA256SUMS); `painel/ultimo/` é a vigente.

## Regras que o código cumpre

- **Vínculo NE → pregão (regra v1.2):** CONFIRMADO, PROVÁVEL, AMBÍGUO (fora das somas), CITADO SEM ATA e ALERTA; nunca somados entre si.
- **Fonte do B1:** Tesouro Gerencial; o Portal da Transparência entra como reserva declarada quando o TG parar mais de 2 dias úteis e estiver mais atual (passo 5).
- **Idade do dado em dias úteis** (seg a sex, sem feriados), na faixa de cada bloco; a faixa fica vermelha com o B1 parado.
- **Sem dado pessoal por construção;** o verificador barra CPF, favorecido e texto de NE.

## Rodar localmente

```bash
pip install -r requirements.txt
PORTAO_ATAS_OFFLINE=1 bash motor/portao.sh saida 2026-11-07   # montagem + recálculo + verificador, sem rede
python -m pytest tests -q
```

Governança, decisões (D1 a D20) e plano vivem na pasta do projeto (OneDrive, PLANO v2.4); este repositório é a fonte única do **código** do painel.
