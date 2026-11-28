# Lições dos palpites (atualizado em 24/11/2026)

Registro completo em `registro_palpites.csv` (61 palpites de 13 a 23/11; 28 certos, 46%).

## Acerto por método

| Método | Acertos | Leitura |
|---|---|---|
| Médias de 1º quarto ("abaixo") | 5 de 6 | Bom, mas o padrão perdeu força depois de 16/11 (48% em 25 jogos) |
| Frequência do jogador na temporada | 3 de 6 | Apostas com 80%+ de acerto no histórico: 2 de 2. Com 70% a 77%: 1 de 3 |
| Tendência dos times em totais | 7 de 15 | Sem valor: teste em 134 jogos desta temporada mostrou que times que ficam "abaixo" em 65%+ das vezes ficaram abaixo em só 43% no jogo seguinte |
| Favorito pela linha | 11 de 24 | Abaixo do esperado (~65%); azar contribui, mas favorito não é aposta segura |
| Handicap com margem | 1 de 4 | Não usar sem cotação conferida |
| Ritmo ao vivo | 1 de 3 | Jogos apertados no fim aceleram com faltas; não confiar no ritmo do 4º quarto |

## Regras daqui para a frente

1. **Totais por tendência dos times: não indicar.** Tratar a linha da casa como 50/50 e só falar de total quando a 1win oferecer linha com 4+ pontos de margem a uma cotação acima da mínima.
2. **Jogadores: só indicar "acima" quando o jogador passou da linha em 80% ou mais dos jogos da temporada e também em 8 dos últimos 10**, com minutos estáveis (30+ por jogo). Descartar quem oscila de minutos (Hachimura) ou depende de arremesso de 3 contra defesa forte (Porter Jr.).
3. **Não apostar contra um jogador em boa fase só porque a média está perto da linha** (McDaniels fez 50 em pontos + rebotes + assistências).
4. **Favoritos: nunca chamar de "seguro".** Mesmo com 75% de chance, perdem 1 em cada 4; em dupla, perdem quase metade das vezes.
5. **Ao vivo:** em jogo apertado no fim, somar uns 8 a 10 pontos ao ritmo, por causa das faltas.
6. **Antes de indicar, conferir lesões perto do horário do jogo** (Wembanyama, Fox, Zion, Towns e Anunoby mudaram linhas em cima da hora).
7. **Registrar cada palpite e o resultado em `registro_palpites.csv`** para medir de novo a cada semana.

## Método de totais (`metodo_totais.py`), testado em 24/11/2026

Teste dia a dia, sem olhar o futuro, em 875 jogos com linha (695 da temporada passada e 180 desta):

| Temporada | Acertos | Erros | % acerto |
|---|---|---|---|
| 2025-26 | 370 | 325 | 53,2% |
| 2026-27 | 98 | 82 | 54,4% |
| Total | 468 | 407 | 53,5% |

- Para empatar a odd 1,85 é preciso 54,1%; o método fica praticamente no empate.
- Filtrar só os jogos de "mais confiança" não melhorou de forma consistente (ruído).
- O que o modelo aprendeu: jogos de times com totais altos nos últimos 5 tendem a voltar para baixo; times em noites seguidas (B2B) puxam para cima; a tendência da liga nos últimos 14 dias continua.
- A projeção simples pelas médias dos times, sozinha, acertou só 48,7%.

## Placar por tipo de aposta (24 a 27/11, R$ 100 cada, odds do VelvetSpin)

| Tipo | Apostas | Acertos | Resultado |
|---|---|---|---|
| Totais pelo método (linha principal) | 10 | 9 | +R$ 709 |
| Lado favorito indicado | 5 | 5 | +R$ 191 |
| Jogadores pela regra de 80% | 14 | 9 | ≈ R$ 0 |
| Jogadores fora da regra | 7 | 3 | −R$ 201 |
| 1º quarto / 1º tempo | 3 | 1 | −R$ 115 |

Regras novas (aplicadas em `analise_dia.py`, rodado por `rodar_dia.sh AAAAMMDD PASTA`):
- Totais: só na linha principal e só quando o método passa de 54% para um lado.
- Lado favorito: vencedor ou handicap que aumenta a chance do favorito, com odd 1,30+, o de melhor valor.
- Jogadores: 80%+ na temporada, 8+ nos últimos 10, 28+ minutos nos últimos 5 jogos e odd 1,60+ (corta os "abaixo de 1,5 roubos" a 1,40, que um único lance derruba).
- Preferir apostas simples a múltiplas grandes.
