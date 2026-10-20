# Coletor Blitz4 24H (experimental, desativado)

Este script é um **adaptador**, não uma fonte de resultados. O coletor Nex consulta a **Blaze**; não conecte essa API aqui. Nenhuma API Blitz4 válida foi confirmada.

Requisitos antes de executar:
- Obter uma API **autorizada** que realmente forneça resultados do jogo Blitz4 Double.
- Validar o contrato da API (ID único por rodada, número 0–14, timestamp oficial em UTC e jogo correto).
- Adaptar `parse_rounds` ao formato real da API somente após validação.
- Definir secretamente no serviço separado: `BLITZ4_RESULTS_URL`, `BLITZ4_INGEST_URL`, `BLITZ_INGEST_KEY`.
- Não incluir segredos no GitHub. Não habilitar em produção antes de verificar continuidade e atrasos de 50 rodadas.

`blitz4_collector.py` está **deliberadamente inativo** sem essas variáveis. Não mexe no Nex nem no robô atual.

Atenção: atualmente o `server.py` do Insight usa `UNIQUE ts` e retorna 409 em certos conflitos. É necessário validar IDs oficiais, entrega fora de ordem e replay antes de ativar um novo coletor. 
