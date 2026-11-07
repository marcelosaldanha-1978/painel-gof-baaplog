# Segurança — painel-gof-baaplog

- **Segredos:** nenhum neste momento. Pelo plano (D14), no máximo dois: a chave de uma conta de serviço Google **só de leitura** (planilha GCALC e a pasta do Drive da subscrição) e a chave da API do Portal da Transparência. Nunca token pessoal do GitHub, nunca chave do Composio, nunca a conta de serviço de escrita.
- **Workflows:** actions fixadas por SHA; `permissions: contents: read` no topo e escrita só no job que grava; `persist-credentials: false`; entradas por `env`; zizmor a cada push (persona pedantic sem achados). Workflow novo não entra sem zizmor.
- **Dado pessoal:** a saída publicada não tem CPF, favorecido nem texto de NE (`motor/verificar_saida.py` barra). O CSV do Tesouro Gerencial com pessoa nunca entra no repositório, em artefato ou em log.
- **Histórico público:** o que for publicado fica no histórico do git. Só entram extratos sem pessoa e dados de gestão já admitidos pelo usuário (decisão D13).
- **Reportar:** abra uma issue sem incluir o dado sensível; descreva onde está.
