# Leitor HTML Blitz4 — laboratório local

**Estado:** protótipo isolado. **Não é uma extensão instalada e não envia dados ao Insight.**

Com `https://blitz4.casino/pt/games/double` aberto, use o Console do DevTools (F12) e cole o conteúdo de `blitz4_dom_lab.js` apenas se quiser realizar teste local. Não utilize a consola para compartilhar tokens ou executar comandos de sites desconhecidos.

- Seletores observados nas capturas: `#roulette-recent .entries.main > .entry`, `.roulette-tile`, `.number`.
- Identifica 1 a 14 numericamente, 0 quando confirmado. Branco representado apenas por ícone não é inferido automaticamente.
- Mantém referência inicial, compara sobreposição das listas e evita inventar pedras quando a sequência fica ambígua.
- Nenhuma escrita ou conexão no servidor; dados ficam apenas na memória do navegador.
- `blitzLab.report()` mostra dados e lacunas. `blitzLab.stop()` encerra a observação.
- **Limitacões:** o histórico DOM pode reordenar, duplicar ou mudar de estrutura; não temos ID oficial nem horário da rodada, apenas da observação. Sobreposição com números repetidos pode ser ambígua. Falta validar a estrutura do branco e testar 50 rodadas.

Próximo passo: validar branco 0 pelo HTML e 50 sequências observadas; só então desenhar transporte confiável e implantação separada.
