<p align="center">
  <img src="docs/img/seguranca.svg" alt="Segurança do painel GOF-BaApLog: zero dado pessoal, só leitura, actions fixadas, sete portões" width="100%">
</p>

<p align="center">
  <img alt="Segredos" src="https://img.shields.io/badge/segredos-2%20%C2%B7%20s%C3%B3%20leitura-30d158">
  <img alt="Actions" src="https://img.shields.io/badge/actions-16%2F16%20fixadas%20por%20SHA-0a84ff">
  <img alt="Permissões" src="https://img.shields.io/badge/permiss%C3%B5es-contents%3A%20read%20no%20topo-6e6e73">
  <img alt="Dado pessoal" src="https://img.shields.io/badge/dado%20pessoal-zero%20por%20constru%C3%A7%C3%A3o-30d158">
</p>

> Este repositório e a página são **públicos por desenho**. A proteção não depende de esconder o código: depende de **o dado pessoal nunca chegar aqui** e de **nada ser publicado sem passar pelos portões**.

---

## 🛡️ Defesa em camadas

```mermaid
flowchart TB
    subgraph C1["1 · Na origem — Google, conta do usuário"]
      A["Assinaturas do Tesouro Gerencial<br/>(CSV com favorecido)"] --> B["⚙️ Apps Script v2PonteTG<br/><b>corta favorecido e CPF/CNPJ</b>"]
    end
    subgraph C2["2 · Na passagem — Drive privado"]
      D[("🔒 PONTE_TG_SEM_PESSOA<br/>compartilhada só com a conta de serviço,<br/>papel Leitor")]
    end
    subgraph C3["3 · No runner — GitHub Actions"]
      E["Conta de serviço com escopos<br/><code>spreadsheets.readonly</code> e <code>drive.readonly</code>"] --> F["Saída só por UG e OMDS:<br/>valores, sem nome e sem texto de NE"]
    end
    subgraph C4["4 · Antes de publicar — portões"]
      G["verificar_saida.py<br/>barra CPF e chaves proibidas"] --> H["recálculo ao centavo<br/>+ navegador headless"]
    end
    I["🌐 Página pública + histórico no git"]
    B --> D --> E
    F --> G
    H -->|tudo passa| I
    H -.->|algo reprova| J["⛔ nada publicado;<br/>fica a versão anterior"]
    style B fill:#0a84ff,color:#fff,stroke:#0a84ff
    style D fill:#1d1d1f,color:#fff,stroke:#1d1d1f
    style I fill:#30d158,color:#fff,stroke:#30d158
    style J fill:#ff453a,color:#fff,stroke:#ff453a
```

**Onde o dado pessoal morre:** no Apps Script, dentro da conta Google do usuário, **antes** de qualquer arquivo ir ao Drive compartilhado. As colunas de favorecido (nome e CPF/CNPJ) nunca chegam ao GitHub, nem em artefato, nem em log.

---

## 🔑 Segredos

| Segredo (GitHub) | O que é | Alcance | Usado em |
|---|---|---|---|
| `GOOGLE_SA_JSON` | chave da conta de serviço `gof-painel-leitura` | **Leitor** da planilha GCALC e da pasta `PONTE_TG_SEM_PESSOA`; escopos só de leitura | `montagem.yml`, `conferencia.yml` |
| `PORTAL_TRANSPARENCIA_API_KEY` | chave da API do Portal da Transparência | consulta pública (reserva do B1) | `montagem.yml` |

**Nunca aqui:** token pessoal do GitHub, chave do Composio, conta de serviço com escrita. O teto (decisão D14) é de **dois** segredos, ambos de leitura. Os dois foram cadastrados em 07/11/2026.

---

## ⚙️ Workflows endurecidos

| Regra | Estado conferido |
|---|---|
| Actions fixadas por SHA de 40 caracteres | **16 de 16** |
| `permissions: contents: read` no topo | **6 de 6** workflows |
| Escrita só no job que grava | `contents: write` nos jobs que gravam histórico (montagem, fichas, conferência, capacidade); `pages: write` só na publicação; `issues: write` só no vigia |
| `persist-credentials: false` no checkout | **6 de 6** |
| Entradas externas só por `env` (sem `${{ }}` em `run`) | auditado pelo zizmor |
| `zizmor` a cada push (persona pedantic) | portão 7 do CI; workflow novo não entra sem ele |

```mermaid
flowchart LR
    P["push"] --> Z["zizmor<br/>pedantic"] --> R["ruff"] --> T["pytest"] --> M["montagem de prova<br/>recálculo · verificador · navegador"] --> OK(["✅ aprovado"])
    Z -.->|achado| X(["⛔ bloqueia"])
    style OK fill:#30d158,color:#fff,stroke:#30d158
    style X fill:#ff453a,color:#fff,stroke:#ff453a
```

---

## 🚫 Dado pessoal: o que barra o quê

| Trava | Onde | O que impede |
|---|---|---|
| Corte de colunas | `PonteTG.gs` (Apps Script do GOF) | favorecido e CPF/CNPJ saírem do Gmail |
| Saída agregada | `gof_regua_tg.py`, `gof_ponte_tg.py` | texto de NC/NE ir à página (só UG, OMDS e valores) |
| Verificador | `motor/verificar_saida.py` | padrão de CPF (formatado ou mascarado) e chaves `favorecido`, `codigoFavorecido`, `observacao`, `contato`, `telefone`, `email`, `cpf` |
| Histórico público | decisão D13 | só extratos sem pessoa e dados de gestão admitidos pelo usuário entram no git |

> **O que for publicado fica no histórico do git.** Por isso o corte é na origem e o verificador roda antes de cada publicação, não depois.

---

## 📅 Ciclo de vida das credenciais

```mermaid
timeline
    title Credenciais do painel
    07 nov 2026 : conta de serviço gof-painel-leitura e chave do Portal cadastradas (D14)
    23 nov 2026 : pasta PONTE_TG_SEM_PESSOA compartilhada só com a conta de serviço
                : projeto encerrado — operação mínima
    jan 2027    : 1ª carga do TG de 2027
                : revogar a conta de serviço · apagar a pasta da ponte
                : cancelar as assinaturas · arquivar o repositório
```

---

## 📣 Reportar um problema

1. Abra uma **issue** descrevendo **onde** está o problema (arquivo, linha, URL).
2. **Não** cole o dado sensível na issue, nem em print.
3. Se for vazamento de dado pessoal na página: a correção é tirar da saída **e** avaliar a reescrita do histórico com o responsável (o histórico é público).

<sub>Normas de referência: Lei nº 13.709/2018 (LGPD) para o tratamento de dado pessoal; Lei nº 12.527/2011 (LAI) para a publicidade dos dados de gestão.</sub>
