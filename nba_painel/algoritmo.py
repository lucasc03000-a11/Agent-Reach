#!/usr/bin/env python3
"""Algoritmo de duplas e triplas da NBA, testado contra o histórico.

Uso:
  python3 algoritmo.py teste              # mede o índice de acerto no histórico
  python3 algoritmo.py hoje [AAAAMMDD]    # sugere pernas, duplas e triplas do dia

Ideia: a linha de fechamento das casas é a melhor previsão disponível de margem
e de total. O algoritmo parte dela, mede no histórico o quanto os jogos se
afastam da linha e, com isso, calcula a chance de uma linha alternativa "com
folga" bater. Um modelo próprio (médias móveis de ataque e defesa de cada time)
cobre os quartos, para os quais não há linha histórica, e desempata o lado.
Rode historico.py antes, para atualizar historico/jogos.csv.
"""
import csv
import itertools
import json
import math
import pathlib
import statistics as st
import sys
import urllib.request
from collections import defaultdict

AQUI = pathlib.Path(__file__).resolve().parent
SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ALFA = 0.12        # peso do jogo mais recente nas médias móveis
MIN_JOGOS = 5      # jogos na temporada antes de confiar no modelo próprio
ALVO_PERNA = 0.80  # chance mínima de cada perna sugerida


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def carregar():
    jogos = []
    for r in csv.DictReader((AQUI / "historico" / "jogos.csv").open()):
        g = {k: r[k] for k in ("jogo_id", "data", "temporada", "visitante", "mandante")}
        for k in ("pts_v", "pts_m", "q1_v", "q2_v", "q3_v", "q4_v", "q1_m", "q2_m", "q3_m", "q4_m", "prorrogacao"):
            g[k] = int(r[k])
        for k in ("linha_mandante", "total_linha", "ml_mandante", "ml_visitante"):
            g[k] = float(r[k]) if r[k] != "" else None
        if g["linha_mandante"] is None or g["total_linha"] is None:
            g["linha_mandante"] = g["total_linha"] = None
        g["margem"] = g["pts_m"] - g["pts_v"]          # do mandante
        g["total"] = g["pts_m"] + g["pts_v"]
        g["q1"] = g["q1_m"] + g["q1_v"]
        g["t1"] = g["q1"] + g["q2_m"] + g["q2_v"]      # primeiro tempo
        jogos.append(g)
    return sorted(jogos, key=lambda g: (g["data"], g["jogo_id"]))


class Modelo:
    """Médias móveis de pontos feitos e sofridos por time (jogo, 1º quarto e 1º tempo)."""

    def __init__(self):
        self.t = {}
        self.liga = {"jogo": 114.0, "q1": 28.5, "t1": 57.0}
        self.mando = 2.5
        self.n = defaultdict(int)

    def _time(self, s):
        if s not in self.t:
            self.t[s] = {k: {"f": v, "s": v} for k, v in self.liga.items()}
        return self.t[s]

    def prever(self, vis, man):
        v, m = self._time(vis), self._time(man)
        out = {}
        for k, peso in (("jogo", 1.0), ("q1", 0.25), ("t1", 0.5)):
            pm = m[k]["f"] + v[k]["s"] - self.liga[k] + self.mando * peso / 2
            pv = v[k]["f"] + m[k]["s"] - self.liga[k] - self.mando * peso / 2
            out[k] = (pv, pm)
        out["pronto"] = min(self.n[vis], self.n[man]) >= MIN_JOGOS
        return out

    def aprender(self, g):
        v, m = self._time(g["visitante"]), self._time(g["mandante"])
        obs = {"jogo": (g["pts_v"], g["pts_m"]), "q1": (g["q1_v"], g["q1_m"]),
               "t1": (g["q1_v"] + g["q2_v"], g["q1_m"] + g["q2_m"])}
        for k, (pv, pm) in obs.items():
            v[k]["f"] += ALFA * (pv - v[k]["f"]); v[k]["s"] += ALFA * (pm - v[k]["s"])
            m[k]["f"] += ALFA * (pm - m[k]["f"]); m[k]["s"] += ALFA * (pv - m[k]["s"])
            self.liga[k] += 0.01 * ((pv + pm) / 2 - self.liga[k])
        self.n[g["visitante"]] += 1
        self.n[g["mandante"]] += 1

    def nova_temporada(self):
        self.n = defaultdict(int)


def passar(jogos):
    """Percorre o histórico em ordem: prevê cada jogo só com o que veio antes."""
    mod, temporada = Modelo(), None
    for g in jogos:
        if g["temporada"] != temporada:
            temporada = g["temporada"]
            mod.nova_temporada()
        p = mod.prever(g["visitante"], g["mandante"])
        g["m_margem"] = p["jogo"][1] - p["jogo"][0]
        g["m_total"] = p["jogo"][0] + p["jogo"][1]
        g["m_q1"] = sum(p["q1"]); g["m_q1_margem"] = p["q1"][1] - p["q1"][0]
        g["m_t1"] = sum(p["t1"])
        g["pronto"] = p["pronto"]
        mod.aprender(g)
    return mod


def desvios(jogos):
    """Quanto os jogos se afastam da previsão (desvio-padrão dos erros)."""
    com = [g for g in jogos if g["total_linha"] is not None]
    pr = [g for g in jogos if g["pronto"]]
    return {
        "total": st.pstdev([g["total"] - g["total_linha"] for g in com]),
        "margem": st.pstdev([g["margem"] + g["linha_mandante"] for g in com]),
        "q1": st.pstdev([g["q1"] - g["m_q1"] for g in pr]),
        "t1": st.pstdev([g["t1"] - g["m_t1"] for g in pr]),
        "m_total": st.pstdev([g["total"] - g["m_total"] for g in pr]),
        "m_margem": st.pstdev([g["margem"] - g["m_margem"] for g in pr]),
    }


def pernas(g, dv, alvo=ALVO_PERNA):
    """Pernas com folga para um jogo: (descrição, chance estimada, função que confere)."""
    z = st.NormalDist().inv_cdf(alvo)
    out = []
    v, m = g["visitante"], g["mandante"]
    if g.get("total_linha") is not None:
        L, S = g["total_linha"], -g["linha_mandante"]   # S = margem esperada do mandante
        ft, fm = z * dv["total"], z * dv["margem"]
        lean_t = (g["m_total"] - L) if g["pronto"] else 0.0
        lean_m = (g["m_margem"] - S) if g["pronto"] else 0.0
        lo, hi = math.floor(L - ft) + 0.5, math.ceil(L + ft) - 0.5
        out.append((f"{v} @ {m}: total acima de {lo}", phi((L - lo) / dv["total"]), lambda r, x=lo: r["total"] > x, "total", lean_t))
        out.append((f"{v} @ {m}: total abaixo de {hi}", phi((hi - L) / dv["total"]), lambda r, x=hi: r["total"] < x, "total", -lean_t))
        hm = math.ceil(-S + fm) - 0.5      # handicap dado ao mandante
        hv = math.ceil(S + fm) - 0.5       # handicap dado ao visitante
        out.append((f"{v} @ {m}: {m} {hm:+.1f}", phi((S + hm) / dv["margem"]), lambda r, x=hm: r["margem"] + x > 0, "handicap", lean_m))
        out.append((f"{v} @ {m}: {v} {hv:+.1f}", phi((hv - S) / dv["margem"]), lambda r, x=hv: -r["margem"] + x > 0, "handicap", -lean_m))
        p_m = phi(S / dv["margem"])
        fav, p_f, ganha = (m, p_m, lambda r: r["margem"] > 0) if p_m >= 0.5 else (v, 1 - p_m, lambda r: r["margem"] < 0)
        if p_f >= alvo:
            out.append((f"{v} @ {m}: {fav} vence", p_f, ganha, "vencedor", 0.0))
    if g["pronto"]:
        for k, nome in (("q1", "1º quarto"), ("t1", "1º tempo")):
            mu, f = g["m_" + k], z * dv[k]
            lo, hi = math.floor(mu - f) + 0.5, math.ceil(mu + f) - 0.5
            out.append((f"{v} @ {m}: {nome} acima de {lo}", phi((mu - lo) / dv[k]), lambda r, x=lo, kk=k: r[kk] > x, k, 0.0))
            out.append((f"{v} @ {m}: {nome} abaixo de {hi}", phi((hi - mu) / dv[k]), lambda r, x=hi, kk=k: r[kk] < x, k, 0.0))
    return out


def melhores(lista, n):
    """As n pernas de maior chance, no máximo uma por jogo.

    No empate, vale a ordem em que os mercados se saíram melhor no teste: vencedor,
    handicap, total. O modelo próprio não desempata: quando ele discorda da linha
    das casas, erra mais do que acerta.
    """
    ordem = {"vencedor": 0, "handicap": 1, "total": 2}
    escolhidas, usados = [], set()
    for jogo_id, p in sorted(lista, key=lambda x: (-round(x[1][1], 2), ordem.get(x[1][3], 9))):
        if jogo_id not in usados:
            escolhidas.append((jogo_id, p)); usados.add(jogo_id)
        if len(escolhidas) == n:
            break
    return escolhidas if len(escolhidas) == n else None


def teste():
    jogos = carregar()
    passar(jogos)
    meio = len(jogos) // 2
    dv = desvios(jogos[:meio])                     # calibra na 1ª metade, confere na 2ª
    aval = jogos[meio:]
    print(f"Histórico: {len(jogos)} jogos; calibração nos {meio} primeiros, teste nos {len(aval)} seguintes")
    print("Desvios (pontos):", {k: round(x, 1) for k, x in dv.items()})

    com = [g for g in jogos if g["total_linha"] is not None]
    print("\nA linha das casas contra o modelo próprio (erro médio absoluto, jogos com linha e modelo pronto):")
    c2 = [g for g in com if g["pronto"]]
    print("  total : casas", round(st.mean(abs(g["total"] - g["total_linha"]) for g in c2), 1),
          "| modelo", round(st.mean(abs(g["total"] - g["m_total"]) for g in c2), 1))
    print("  margem: casas", round(st.mean(abs(g["margem"] + g["linha_mandante"]) for g in c2), 1),
          "| modelo", round(st.mean(abs(g["margem"] - g["m_margem"]) for g in c2), 1))
    dis = [g for g in c2 if abs(g["m_total"] - g["total_linha"]) >= 6]
    ok = sum((g["total"] > g["total_linha"]) == (g["m_total"] > g["total_linha"]) for g in dis if g["total"] != g["total_linha"])
    print(f"  quando o modelo discorda do total das casas em 6+ pontos, ele acerta o lado em {ok}/{len(dis)} = {ok/len(dis):.0%}")

    print("\nAcerto real por folga em relação à linha (todos os jogos com linha):")
    print("  folga | total (acima/abaixo com folga) | handicap com folga")
    for c in (0, 4, 6, 8, 10, 12, 15, 18):
        t = st.mean([(g["total"] > g["total_linha"] - c) for g in com] + [(g["total"] < g["total_linha"] + c) for g in com])
        h = st.mean([(g["margem"] + g["linha_mandante"] + c > 0) for g in com] + [(-(g["margem"] + g["linha_mandante"]) + c > 0) for g in com])
        print(f"  {c:>5} | {t:>30.1%} | {h:.1%}")

    for alvo in (0.75, 0.80, 0.85, 0.90):
        res = defaultdict(list)
        dias = defaultdict(list)
        for g in aval:
            for p in pernas(g, dv, alvo):
                res[p[3]].append(p[2](g))
                dias[g["data"]].append((g["jogo_id"], p, p[2](g)))
        print(f"\nPernas com chance estimada de {alvo:.0%} — acerto real no período de teste:")
        for k, v in res.items():
            print(f"  {k:<9} {st.mean(v):.1%}  ({len(v)} pernas)")
        for n, nome in ((2, "duplas"), (3, "triplas")):
            hits = []
            for d, lst in dias.items():
                # só mercados com linha das casas, que são os mais bem calibrados
                cand = [(j, p) for j, p, _ in lst if p[3] in ("total", "handicap", "vencedor")]
                esc = melhores(cand, n)
                if esc:
                    byid = {x["jogo_id"]: x for x in aval}
                    hits.append(all(p[2](byid[j]) for j, p in esc))
            if hits:
                print(f"  {nome}: {sum(hits)}/{len(hits)} dias = {st.mean(hits):.1%}  (cotação mínima para empatar: {1/st.mean(hits):.2f})")
    teste_favoritos(jogos)


def decimal(americana):
    return 1 + (americana / 100 if americana > 0 else 100 / -americana)


def teste_favoritos(jogos):
    """Único mercado com cotação real no histórico: quanto rende apostar no favorito."""
    G = []
    for g in jogos:
        if g["ml_mandante"] is None or g["ml_visitante"] is None or g["linha_mandante"] is None:
            continue
        casa_fav = g["ml_mandante"] < g["ml_visitante"]
        G.append({"data": g["data"], "cot": decimal(g["ml_mandante"] if casa_fav else g["ml_visitante"]),
                  "ok": (g["margem"] > 0) == casa_fav, "hc": abs(g["linha_mandante"])})
    print(f"\nFavorito para vencer, com a cotação real de fechamento ({len(G)} jogos):")
    print("  handicap | jogos | favorito vence | cotação média | lucro por R$ 100")
    for lo, hi in ((0, 3), (3, 6), (6, 9), (9, 12), (12, 40)):
        x = [g for g in G if lo <= g["hc"] < hi]
        print(f"  {lo:>2} a {hi:<3}| {len(x):>5} | {st.mean(g['ok'] for g in x):>13.1%} | {st.mean(g['cot'] for g in x):>13.2f} | {100 * st.mean(g['cot'] * g['ok'] - 1 for g in x):+.1f}")
    dias = defaultdict(list)
    for g in G:
        dias[g["data"]].append(g)
    for n, nome in ((2, "Dupla"), (3, "Tripla")):
        for corte in (6, 9):
            res = []
            for lst in dias.values():
                esc = sorted([g for g in lst if g["hc"] >= corte], key=lambda g: g["cot"])[:n]
                if len(esc) == n:
                    res.append((all(g["ok"] for g in esc), math.prod(g["cot"] for g in esc)))
            print(f"  {nome} dos maiores favoritos do dia (handicap {corte}+): {len(res)} dias | acerto {st.mean(h for h, _ in res):.1%}"
                  f" | cotação média {st.mean(c for _, c in res):.2f} | lucro por R$ 100: {100 * st.mean(c * h - 1 for h, c in res):+.1f}")


def hoje(dia=None):
    jogos = carregar()
    mod = passar(jogos)
    dv = desvios(jogos)
    url = f"{SITE}/scoreboard" + (f"?dates={dia}" if dia else "")
    req = lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "nba-painel/1.0"}), timeout=40))
    cand = []
    for e in req(url).get("events") or []:
        if e["status"]["type"]["state"] != "pre":
            continue
        lado = {c["homeAway"]: c for c in e["competitions"][0]["competitors"]}
        v, m = lado["away"]["team"]["abbreviation"], lado["home"]["team"]["abbreviation"]
        p = mod.prever(v, m)
        g = {"jogo_id": e["id"], "visitante": v, "mandante": m, "pronto": p["pronto"],
             "m_margem": p["jogo"][1] - p["jogo"][0], "m_total": sum(p["jogo"]),
             "m_q1": sum(p["q1"]), "m_t1": sum(p["t1"]), "total_linha": None, "linha_mandante": None}
        pc = (req(f"{SITE}/summary?event={e['id']}").get("pickcenter") or [{}])[0]
        if pc.get("overUnder") is not None and pc.get("spread") is not None:
            g["total_linha"], g["linha_mandante"] = float(pc["overUnder"]), float(pc["spread"])
        print(f"\n{v} @ {m} | linha das casas: {m} {g['linha_mandante']} · total {g['total_linha']} | modelo: margem {m} {g['m_margem']:+.1f}, total {g['m_total']:.0f}")
        for p in sorted(pernas(g, dv), key=lambda x: -x[1]):
            print(f"   {p[1]:.0%}  cotação mínima {1/p[1]:.2f}  {p[0].split(': ')[1]}  [{p[3]}]")
            cand.append((g["jogo_id"], p))
    base = [(j, p) for j, p in cand if p[3] in ("total", "handicap", "vencedor")]
    for n, nome in ((2, "Dupla"), (3, "Tripla")):
        esc = melhores(base, n)
        if esc:
            prob = math.prod(p[1] for _, p in esc)
            print(f"\n{nome} sugerida — chance estimada {prob:.0%}, cotação mínima para valer {1/prob:.2f}:")
            for _, p in esc:
                print(f"   {p[0]}  ({p[1]:.0%})")
    if not cand:
        print("Nenhum jogo por começar nessa data.")


def exportar(dia):
    """Grava em data/ as tabelas do algoritmo para o painel."""
    import datetime as dt
    jogos = carregar()
    mod = passar(jogos)
    dv = desvios(jogos)
    req = lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "nba-painel/1.0"}), timeout=40))
    nomes = {"total": "Total do jogo", "handicap": "Handicap", "vencedor": "Vencedor", "q1": "1º quarto", "t1": "1º tempo"}
    linhas, cand = [], []
    for e in req(f"{SITE}/scoreboard?dates={dia}").get("events") or []:
        if e["status"]["type"]["state"] != "pre":
            continue
        lado = {c["homeAway"]: c for c in e["competitions"][0]["competitors"]}
        v, m = lado["away"]["team"]["abbreviation"], lado["home"]["team"]["abbreviation"]
        p = mod.prever(v, m)
        g = {"jogo_id": e["id"], "visitante": v, "mandante": m, "pronto": p["pronto"],
             "m_margem": p["jogo"][1] - p["jogo"][0], "m_total": sum(p["jogo"]),
             "m_q1": sum(p["q1"]), "m_t1": sum(p["t1"]), "total_linha": None, "linha_mandante": None}
        pc = (req(f"{SITE}/summary?event={e['id']}").get("pickcenter") or [{}])[0]
        if pc.get("overUnder") is not None and pc.get("spread") is not None:
            g["total_linha"], g["linha_mandante"] = float(pc["overUnder"]), float(pc["spread"])
        for i, pe in enumerate(sorted(pernas(g, dv), key=lambda x: -x[1])):
            linhas.append({"chave": f"{e['id']}-{i}", "jogo_id": e["id"], "jogo": f"{v} @ {m}",
                           "aposta": pe[0].split(": ")[1], "mercado": nomes[pe[3]],
                           "chance": round(pe[1] * 100), "cotacao_minima": round(1 / pe[1], 2),
                           "linha_casas": "" if g["total_linha"] is None else f"{m} {g['linha_mandante']:+.1f} · total {g['total_linha']}"})
            cand.append((e["id"], pe))
    combos = []
    base = [(j, pe) for j, pe in cand if pe[3] in ("total", "handicap", "vencedor")]
    for n, nome in ((2, "Dupla"), (3, "Tripla")):
        esc = melhores(base, n)
        if esc:
            prob = math.prod(pe[1] for _, pe in esc)
            combos.append({"chave": nome, "tipo": nome, "pernas": " + ".join(pe[0] for _, pe in esc),
                           "chance": round(prob * 100), "cotacao_minima": round(1 / prob, 2)})
    com = [g for g in jogos if g["total_linha"] is not None]
    folga = []
    for c in (0, 4, 6, 8, 10, 12, 15, 18):
        t = st.mean([(g["total"] > g["total_linha"] - c) for g in com] + [(g["total"] < g["total_linha"] + c) for g in com])
        h = st.mean([(g["margem"] + g["linha_mandante"] + c > 0) for g in com] + [(-(g["margem"] + g["linha_mandante"]) + c > 0) for g in com])
        folga.append({"chave": str(c), "folga": c, "acerto_total": round(t * 100, 1), "acerto_handicap": round(h * 100, 1), "jogos": len(com)})
    meio = len(jogos) // 2
    dvt, aval = desvios(jogos[:meio]), jogos[meio:]
    byid = {x["jogo_id"]: x for x in aval}
    teste_c = []
    for alvo in (0.75, 0.80, 0.85, 0.90):
        dias = defaultdict(list)
        for g in aval:
            for pe in pernas(g, dvt, alvo):
                if pe[3] in ("total", "handicap", "vencedor"):
                    dias[g["data"]].append((g["jogo_id"], pe))
        linha = {"chave": str(round(alvo * 100)), "chance_por_perna": round(alvo * 100)}
        for n, nome in ((2, "dupla"), (3, "tripla")):
            hits = [all(pe[2](byid[j]) for j, pe in esc) for esc in (melhores(l, n) for l in dias.values()) if esc]
            linha[f"acerto_{nome}"] = round(st.mean(hits) * 100, 1)
            linha[f"dias_{nome}"] = len(hits)
            linha[f"cotacao_minima_{nome}"] = round(1 / st.mean(hits), 2)
        teste_c.append(linha)
    meta = [{"label": "Fonte", "value": "Linhas de fechamento e placares da ESPN; cálculo de algoritmo.py"},
            {"label": "Histórico", "value": f"{len(jogos)} jogos, {len(com)} com linha"},
            {"label": "Gerado em (UTC)", "value": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")},
            {"label": "algoritmo.py", "value": pathlib.Path(__file__).read_text(), "type": "code", "lang": "python"}]
    saida = AQUI / "data"
    saida.mkdir(exist_ok=True)
    for nome, rows in (("alg_pernas", linhas), ("alg_combos", combos), ("alg_folga", folga), ("alg_teste", teste_c)):
        (saida / f"{nome}.json").write_text(json.dumps({"rows": rows, "meta": meta}, ensure_ascii=False))
        print(f"{nome}: {len(rows)} linhas")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "exportar":
        exportar(sys.argv[2])
        sys.exit()
    if len(sys.argv) > 1 and sys.argv[1] == "hoje":
        hoje(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        teste()
