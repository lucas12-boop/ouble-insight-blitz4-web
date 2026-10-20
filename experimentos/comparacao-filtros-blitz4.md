# Comparação dos filtros do Insight Blitz4 — somente LAB

Nenhum filtro foi removido do motor em produção.

## Problemas distintos

1. Sem recebimento de pedra nova: **NENHUM** perfil pode liberar sinal.
2. Dados com lacuna, atraso ou múltiplas rodadas acumuladas: cancelar pontuação retroativa.
3. Dados íntegros e atuais, mas sem consenso: avaliar perfil abaixo.

## Perfis para replay prospectivo (sem usar o resultado futuro na decisão)

| Perfil | Predominância 50 | Horizontes de acordo | Mínimo histórico Casas Fortes | Veto Casas Fortes |
|---|---:|---:|---:|---|
| Atual | 56% | 3/4 | 70 | Cor escolhida >=43% |
| Intermediário | 54% | 2/4 | 70 | Não; usar só para relatório |
| Flexível | 52% | 2/4 | 70 | Não; usar só para relatório |

Observações:
- Com 2/4, empate entre horizontes é possível. Manter votação ponderada como desempate, **não** usar pedras posteriores à entrada.
- Testar janelas 20/50/1200/7D, com a base de sete dias limitada ao período ANTERIOR à rodada simulada, evitando vazamento temporal.
- Medir número de entradas, SG, G1, G2, LOSS, taxa geral, SG+G1, lacunas e amostragem por hora.
- Comparar em pelo menos 50 oportunidades **fora da amostra de calibração**. Não escolher perfil somente pelo maior número de GREENs.
- Não pontuar sinais criados depois do fechamento da rodada.
- Preservar proteção quando a API não recebe pedra nova ou a observação estiver atrasada.

## Próximo passo

Obter um JSON de diagnóstico atual do Insight e o histórico de resultados por data com sequência e timestamps. Construir replay rigoroso em laboratório, gerar comparação verificável e selecionar perfil somente após os testes.

Nenhum ajuste de 54% / 2/4 está ativado no Insight de clientes ou proprietário.
