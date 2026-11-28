#!/bin/bash
# Análise completa do dia: descobre os jogos no site, baixa as odds e roda analise_dia.py.
# Uso: ./rodar_dia.sh AAAAMMDD PASTA_SAIDA
set -e
DIA=$1; OUT=$2; mkdir -p "$OUT"
cd "$(dirname "$0")"
SLUGS=$(node descobrir_jogos.js)
echo "jogos no site: $SLUGS"
node odds_site.js "$OUT" $SLUGS
python3 historico.py >/dev/null
python3 coletor.py --hoje "$DIA" >/dev/null 2>&1 || true
python3 analise_dia.py "$OUT" "$DIA"
