# Double Insight PRO — Blitz4 LAB v0.2

Protótipo de pesquisa, com resultados do Excel da Blitz4 embutidos no HTML. NÃO é um serviço de sinais ao vivo ou ferramenta de apostas automáticas. Nenhuma promessa de acerto.

## Publicar com GitHub + Railway
1. Crie um repositório privado **double-insight-blitz4-web** no GitHub (não utilize o repositório da Blaze).
2. Envie estes arquivos para a raiz do novo repositório: `index.html`, `server.py`, `railway.json`, `requirements.txt`, `README.md`.
3. No projeto Railway **Double Insight PRO Blitz4 LAB**, adicione um serviço a partir do GitHub e conecte `double-insight-blitz4-web` (branch `main`).
4. Em Networking, gere o domínio público do serviço depois do primeiro deploy.

## Testar localmente
`python server.py`, depois abra http://localhost:8080.

## Limitações
- Simulação de padrões experimentais, não implementação exata da extensão da Blaze.
- Histórico estático de 19/10/2026, sem atualização automática em tempo real.
- Sem login/ADM ainda: **não publique dados privados ou senhas neste serviço**.
- Fonte de dados ao vivo requer autorização e validação independente.
