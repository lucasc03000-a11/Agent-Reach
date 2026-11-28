#!/usr/bin/env python3
"""Baixa o histórico de jogos da NBA (ESPN) para testar o algoritmo de apostas.

Uso:  python3 historico.py [--inicio AAAA-MM-DD] [--fim AAAA-MM-DD]

Grava historico/jogos.csv com uma linha por jogo encerrado da temporada regular:
placar final, pontos por quarto e as linhas de fechamento (handicap, total e
moneyline) publicadas pela ESPN. Jogos já baixados não são baixados de novo.
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
AQUI = pathlib.Path(__file__).resolve().parent
ARQ = AQUI / "historico" / "jogos.csv"
CAMPOS = ["jogo_id", "data", "temporada", "visitante", "mandante", "pts_v", "pts_m",
          "q1_v", "q2_v", "q3_v", "q4_v", "q1_m", "q2_m", "q3_m", "q4_m", "prorrogacao",
          "linha_mandante", "total_linha", "ml_mandante", "ml_visitante"]


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nba-painel/1.0"})
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception:
            if tentativa == 2:
                raise


def do_dia(dia):
    """Jogos encerrados da temporada regular em um dia (sem as linhas)."""
    try:
        d = baixar(f"{SITE}/scoreboard?dates={dia:%Y%m%d}")
    except Exception:
        return []
    saida = []
    for e in d.get("events") or []:
        if (e.get("season") or {}).get("type") != 2 or e["status"]["type"]["state"] != "post":
            continue
        comp = e["competitions"][0]
        lado = {c["homeAway"]: c for c in comp["competitors"]}
        v, m = lado["away"], lado["home"]
        qv = [int(x.get("value") or 0) for x in v.get("linescores") or []]
        qm = [int(x.get("value") or 0) for x in m.get("linescores") or []]
        if len(qv) < 4 or len(qm) < 4:
            continue
        saida.append({
            "jogo_id": e["id"], "data": f"{dia:%Y-%m-%d}", "temporada": e["season"]["year"],
            "visitante": v["team"]["abbreviation"], "mandante": m["team"]["abbreviation"],
            "pts_v": int(v["score"]), "pts_m": int(m["score"]),
            "q1_v": qv[0], "q2_v": qv[1], "q3_v": qv[2], "q4_v": qv[3],
            "q1_m": qm[0], "q2_m": qm[1], "q3_m": qm[2], "q4_m": qm[3],
            "prorrogacao": int(len(qv) > 4),
        })
    return saida


def com_linhas(jogo):
    """Acrescenta handicap, total e moneyline de fechamento."""
    jogo.update(linha_mandante="", total_linha="", ml_mandante="", ml_visitante="")
    try:
        p = (baixar(f"{SITE}/summary?event={jogo['jogo_id']}").get("pickcenter") or [{}])[0]
    except Exception:
        return jogo
    jogo["linha_mandante"] = p.get("spread", "") if p.get("spread") is not None else ""
    jogo["total_linha"] = p.get("overUnder", "") if p.get("overUnder") is not None else ""
    jogo["ml_mandante"] = (p.get("homeTeamOdds") or {}).get("moneyLine", "") or ""
    jogo["ml_visitante"] = (p.get("awayTeamOdds") or {}).get("moneyLine", "") or ""
    return jogo


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inicio", default="2025-10-21")
    ap.add_argument("--fim", default=(dt.date.today() - dt.timedelta(days=1)).isoformat())
    a = ap.parse_args()
    ARQ.parent.mkdir(exist_ok=True)
    feitos = {}
    if ARQ.exists():
        feitos = {r["jogo_id"]: r for r in csv.DictReader(ARQ.open())}
    ini, fim = dt.date.fromisoformat(a.inicio), dt.date.fromisoformat(a.fim)
    dias = [ini + dt.timedelta(days=i) for i in range((fim - ini).days + 1)]
    with ThreadPoolExecutor(8) as ex:
        novos = [j for lista in ex.map(do_dia, dias) for j in lista if j["jogo_id"] not in feitos]
        for j in ex.map(com_linhas, novos):
            feitos[j["jogo_id"]] = j
    linhas = sorted(feitos.values(), key=lambda r: (r["data"], r["jogo_id"]))
    with ARQ.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(linhas)
    print(f"{len(linhas)} jogos no histórico ({len(novos)} novos)")


if __name__ == "__main__":
    main()
