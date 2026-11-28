# NBA Power Painel

Coletor de dados da NBA (API pública da ESPN) e a página do painel interativo.

- `coletor.py` — baixa jogos, box scores, classificação e médias dos jogadores e
  grava um JSON por tabela em `data/`. Só usa a biblioteca padrão do Python.
  `python3 coletor.py` (ou `--hoje AAAAMMDD` para uma data específica).
- `palpites_registrados.json` — palpites feitos antes dos jogos; o coletor
  preenche resultado e situação (Acertou / Errou / Em aberto).
- `painel/index.html` — a página do painel (abas Hoje, Rodada anterior, Times, Jogadores).

Modelo: chance de vitória pela diferença de saldo médio de pontos dos times,
mais 2,5 pontos para o mandante (desvio-padrão de 12 pontos). Pontos esperados
de um jogador = média na temporada × (pontos sofridos pelo adversário ÷ média da liga).
