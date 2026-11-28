#!/usr/bin/env python3
"""Análise do dia: cruza as odds do site com a linha da ESPN, o método de totais
e o histórico dos jogadores.

Uso:  python3 analise_dia.py PASTA_DAS_ODDS AAAAMMDD

PASTA_DAS_ODDS tem, para cada jogo, main_<slug>.txt e players_<slug>.txt (texto da
página do site, salvo por odds_site.js). Regras aplicadas (ver LICOES.md):
  - totais: só o lado indicado pelo método de totais;
  - totais: só na linha principal e quando o método passa de 54% para um lado;
  - lado favorito: vencedor ou handicap a favor do favorito (odd 1,30+), o de melhor valor;
  - jogadores: só quando o lado bateu em 80%+ dos jogos da temporada e em 8+ dos
    últimos 10, com 28+ minutos nos últimos 5 jogos e odd 1,60+.
"""
import glob
import json
import os
import re
import statistics as st
import sys
import unicodedata
import urllib.request
from statistics import NormalDist

import algoritmo as A
import metodo_totais as M

P = NormalDist().cdf
SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
GAMELOG = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{}/gamelog"
MERCADOS = {"individual total": "PTS", "Três pontos. individual total": "3PM", "Rebotes. individual total": "REB",
            "Assistências. individual total": "AST", "Bolas recuperadas. individual total": "STL"}
NOMES = {"PTS": "pontos", "3PM": "bolas de 3", "REB": "rebotes", "AST": "assistências", "STL": "roubos"}


def baixar(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "nba-painel/1.0"}), timeout=40))


def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().replace(".", "").strip()


def linhas_txt(caminho):
    return [l.strip() for l in open(caminho, encoding="utf-8") if l.strip() not in ("", "Bet Builder")]


def escada_total(L):
    """Linhas de total do jogo: [(linha, odd acima, odd abaixo)]."""
    idx = [k for k, l in enumerate(L) if l == "Total"]
    for i in idx:
        v = []
        for l in L[i + 1:]:
            if l in ("Mais", "Menos"):
                continue
            try:
                v.append(float(l))
            except ValueError:
                break
        trios = [(v[j], v[j + 1], v[j + 2]) for j in range(0, len(v) - 2, 3) if v[j] > 150]
        if trios:
            return trios
    return []


def vencedor(L):
    i = L.index("Vencedor (incl. prolongamento)")
    nums = [float(x) for x in L[i + 1:i + 6] if re.match(r"^\d+\.\d+$", x)]
    return nums[0], nums[1]   # (mandante, visitante) — o site lista o mandante primeiro


def handicaps(L):
    """Escada de handicap do jogo: [(lado '1' mandante / '2' visitante, linha, odd)]."""
    i = L.index("Handicap", L.index("Vencedor (incl. prolongamento)")) if "Handicap" in L else -1
    out = []
    for k in range(i + 1, min(i + 120, len(L))):
        m = re.match(r"^([12])\(([-+]?[\d.]+)\)$", L[k])
        if m and re.match(r"^\d+\.\d+$", L[k - 1]):
            out.append((m.group(1), float(m.group(2)), float(L[k - 1])))
        elif out and not re.match(r"^[\d.]+$", L[k]) and not re.match(r"^[12]\(", L[k]):
            break
    return out


def props(L):
    out, cur, i = [], None, 0
    while i < len(L):
        l = L[i]
        if l in MERCADOS:
            cur = MERCADOS[l]; i += 1; continue
        if l.endswith("individual total") or l.endswith(". Resultado (1X2)"):
            cur = None; i += 1; continue   # mercado que não analisamos (tocos, etc.)
        if cur and i + 3 < len(L) and all(re.match(r"^[\d.]+$", L[i + k]) for k in (1, 2, 3)) and not re.match(r"^[\d.]+$", l):
            out.append((l, cur, float(L[i + 1]), float(L[i + 2]), float(L[i + 3]))); i += 4; continue
        i += 1
    return out


def main(pasta, dia):
    jogos = M.carregar()
    com = [g for g in A.carregar() if g["total_linha"] is not None]
    sdT = st.pstdev([g["total"] - g["total_linha"] for g in com])
    sdM = st.pstdev([g["margem"] + g["linha_mandante"] for g in com])
    jog = {norm(x["jogador"]): x for x in json.load(open(os.path.join(os.path.dirname(__file__), "data", "jogadores.json")))["rows"]}
    espn = {}
    for e in baixar(f"{SITE}/scoreboard?dates={dia}")["events"]:
        c = e["competitions"][0]; t = {x["homeAway"]: x["team"] for x in c["competitors"]}
        s = baixar(f"{SITE}/summary?event={e['id']}"); pc = (s.get("pickcenter") or [{}])[0]
        les = {b["team"]["abbreviation"]: [f"{i['athlete']['displayName']} ({'fora' if str(i.get('status')).startswith('Out') else 'dúvida'})"
                                           for i in b.get("injuries", [])] for b in s.get("injuries") or []}
        espn[norm(t["home"]["displayName"])] = dict(h=t["home"]["abbreviation"], v=t["away"]["abbreviation"],
                                                    S=pc.get("spread"), T=pc.get("overUnder"), les=les, hora=e["date"])
    # sinais do método de totais para os jogos do dia
    extra = [dict(jogo_id=f"x{k}", data="9999-12-31", temporada=jogos[-1]["temporada"], visitante=g["v"], mandante=g["h"],
                  pts_v=0, pts_m=0, total=0, total_linha=g["T"], linha_mandante=0.0, margem=0)
             for k, g in enumerate(espn.values()) if g["T"]]
    sinais = M.montar_sinais(jogos + extra)
    treino = [l for l in sinais if l["g"]["data"] < "9999" and l["pronto"]]
    modelo = M.treinar([l["x"] for l in treino], [l["y"] for l in treino])
    p_acima = {l["g"]["mandante"]: M.prever(modelo, l["x"]) for l in sinais if l["g"]["data"] == "9999-12-31"}
    cache, resumo = {}, []
    for arq in sorted(glob.glob(os.path.join(pasta, "main_*.txt"))):
        slug = os.path.basename(arq)[5:-4]
        L = linhas_txt(arq)
        nome_casa = norm(" ".join(slug.split("-")[:-1]))
        g = next((v for k, v in espn.items() if nome_casa.startswith(k) or k in nome_casa), None)
        if not g or g["T"] is None:
            continue
        h, v, mu, T = g["h"], g["v"], -g["S"], g["T"]
        print(f"\n=== {v} @ {h} | ESPN: {h} {g['S']:+} · total {T} | lesões: {g['les']}")
        ml = vencedor(L); pm = 1 - P(-mu / sdM)
        print(f"  vencedor: {h} {ml[0]} (chance {pm:.0%}, ev {(pm * ml[0] - 1) * 100:+.0f}%) | {v} {ml[1]} (chance {1 - pm:.0%}, ev {((1 - pm) * ml[1] - 1) * 100:+.0f}%)")
        # lado favorito: vencedor ou handicap a favor dele (mais chance), escolhendo o de melhor valor com odd >= 1.30
        fav, pf, oddf = (h, pm, ml[0]) if pm >= 0.5 else (v, 1 - pm, ml[1])
        opcoes = [(f"{fav} vence", pf, oddf)]
        for lado_h, x, odd in handicaps(L):
            time = h if lado_h == "1" else v
            margem = mu if lado_h == "1" else -mu          # margem esperada do time
            pr = 1 - P((-x - margem) / sdM)                # time + x > 0
            if time == fav and odd >= 1.30 and pr > pf:   # só linhas que aumentam a chance do favorito
                opcoes.append((f"{time} {x:+.1f}", pr, odd))
        melhor_v = max(opcoes, key=lambda o: o[1] * o[2])
        print(f"  lado favorito: melhor = {melhor_v[0]} a {melhor_v[2]} (chance {melhor_v[1]:.0%}, ev {(melhor_v[1] * melhor_v[2] - 1) * 100:+.0f}%)")
        resumo.append(("vencedor", f"{v} @ {h}", melhor_v[0], melhor_v[2], melhor_v[1]))
        pa = p_acima.get(h, 0.5); lado = "acima" if pa > 0.5 else "abaixo"
        melhor = None
        escada = escada_total(L)
        if escada:   # só a linha principal (odds mais parecidas dos dois lados): foi onde o método foi testado
            lin, oa, ob = min(escada, key=lambda t: abs(t[1] - t[2]))
            media = T + NormalDist().inv_cdf(pa) * sdT
            pr = (1 - P((lin - media) / sdT)) if lado == "acima" else P((lin - media) / sdT)
            melhor = (lin, pr, oa if lado == "acima" else ob)
        if melhor and max(pa, 1 - pa) >= 0.54:
            print(f"  total (método {pa:.0%} acima): melhor = {lado} de {melhor[0]} a {melhor[2]} (chance {melhor[1]:.0%}, ev {(melhor[1] * melhor[2] - 1) * 100:+.0f}%)")
            resumo.append(("total", f"{v} @ {h}", f"{lado} de {melhor[0]}", melhor[2], melhor[1]))
        pp = os.path.join(pasta, f"players_{slug}.txt")
        if not os.path.exists(pp):
            continue
        for nome, m, lin, oa, ob in props(linhas_txt(pp)):
            a = jog.get(norm(nome))
            if not a:
                continue
            if a["jogador_id"] not in cache:
                d = baixar(GAMELOG.format(a["jogador_id"])); n, ev, rows = d["names"], d["events"], []
                for t in d["seasonTypes"]:
                    if "Regular" not in t["displayName"]:
                        continue
                    for c in t["categories"]:
                        for e in c.get("events", []):
                            s = dict(zip(n, e["stats"]))
                            rows.append((ev[e["eventId"]]["gameDate"], {"PTS": int(s["points"]), "REB": int(s["totalRebounds"]),
                                         "AST": int(s["assists"]), "STL": int(s["steals"]),
                                         "3PM": int(s["threePointFieldGoalsMade-threePointFieldGoalsAttempted"].split("-")[0]),
                                         "MIN": float(s["minutes"])}))
                    break   # só a temporada mais recente
                rows.sort(key=lambda r: r[0]); cache[a["jogador_id"]] = [r[1] for r in rows]
            jg = cache[a["jogador_id"]]
            if len(jg) < 8:
                continue
            vals = [x[m] for x in jg]; minutos = st.mean(x["MIN"] for x in jg[-5:])
            for lado_p, odd in (("acima", oa), ("abaixo", ob)):
                ok = [(x > lin) if lado_p == "acima" else (x < lin) for x in vals]
                ps, r10 = sum(ok) / len(ok), sum(ok[-10:])
                if ps >= 0.8 and r10 >= 8 and minutos >= 28 and odd >= 1.60:
                    pr = 0.6 * ps + 0.4 * (1 / odd) / 1.05
                    print(f"  JOGADOR: {nome} {lado_p} de {lin} {NOMES[m]} a {odd} | temporada {sum(ok)}/{len(ok)}, últimos 10 {r10}/10, média {st.mean(vals):.1f}, {minutos:.0f} min")
                    resumo.append(("jogador", f"{v} @ {h}", f"{nome} {lado_p} de {lin} {NOMES[m]}", odd, pr))
    print("\n### RESUMO")
    for r in sorted(resumo, key=lambda r: -r[4] * r[3]):
        print(f"  [{r[0]}] {r[1]}: {r[2]} @ {r[3]} (chance ~{r[4]:.0%}, ev {(r[4] * r[3] - 1) * 100:+.0f}%)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
