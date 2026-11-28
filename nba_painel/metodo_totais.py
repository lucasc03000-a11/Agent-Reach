#!/usr/bin/env python3
"""Método de análise de totais (acima/abaixo da linha) e teste em duas temporadas.

Uso:  python3 metodo_totais.py

Para cada jogo, usa só o que se sabia ANTES dele (teste "dia a dia", sem olhar o futuro):
  1. Linha de fechamento das casas (ponto de partida).
  2. Projeção própria: média móvel de pontos feitos e sofridos de cada time,
     separada em casa e fora, mais o ritmo dos últimos 5 jogos.
  3. Descanso: jogo em noites seguidas (B2B) para cada time.
  4. Viés recente da liga: quanto os jogos dos últimos 14 dias ficaram acima
     ou abaixo das linhas.
Uma regressão logística, retreinada a cada dia só com jogos anteriores, converte
esses sinais na chance de o jogo passar da linha. O método só "aposta" quando a
chance fica longe de 50% (limiares testados abaixo).
"""
import datetime as dt
import math
import statistics as st
from collections import defaultdict, deque

import numpy as np

import algoritmo as A

ALFA = 0.15


def carregar():
    jogos = [g for g in A.carregar() if g["total_linha"] is not None and g["total"] != g["total_linha"]]
    return sorted(jogos, key=lambda g: (g["data"], g["jogo_id"]))


def montar_sinais(jogos):
    """Calcula, para cada jogo, os sinais conhecidos antes dele."""
    ef = defaultdict(lambda: 114.0)       # média móvel de pontos feitos
    es = defaultdict(lambda: 114.0)       # média móvel de pontos sofridos
    ult = defaultdict(lambda: deque(maxlen=5))   # totais dos últimos 5 jogos
    ultimo_dia = {}
    n = defaultdict(int)
    residuos = deque()                    # (data, total - linha) da liga
    temporada = None
    linhas = []
    for g in jogos:
        if g["temporada"] != temporada:   # nova temporada: recomeça as médias
            temporada = g["temporada"]
            ef.clear(); es.clear(); ult.clear(); ultimo_dia.clear(); n.clear(); residuos.clear()
        d = dt.date.fromisoformat(g["data"])
        h, v = g["mandante"], g["visitante"]
        proj = (ef[h] + es[v]) / 2 + (ef[v] + es[h]) / 2
        rec = (st.mean(ult[h]) if ult[h] else proj) / 2 + (st.mean(ult[v]) if ult[v] else proj) / 2
        b2b = sum(1 for t in (h, v) if t in ultimo_dia and (d - ultimo_dia[t]).days == 1)
        while residuos and (d - residuos[0][0]).days > 14:
            residuos.popleft()
        vies = st.mean(r for _, r in residuos) if len(residuos) >= 20 else 0.0
        pronto = n[h] >= 5 and n[v] >= 5
        linhas.append({
            "g": g, "pronto": pronto,
            "x": [proj - g["total_linha"], rec - g["total_linha"], b2b, vies],
            "y": 1 if g["total"] > g["total_linha"] else 0,
        })
        for t, f, s in ((h, g["pts_m"], g["pts_v"]), (v, g["pts_v"], g["pts_m"])):
            ef[t] += ALFA * (f - ef[t]); es[t] += ALFA * (s - es[t])
            ult[t].append(g["total"]); ultimo_dia[t] = d; n[t] += 1
        residuos.append((d, g["total"] - g["total_linha"]))
    return linhas


def treinar(X, y, l2=1.0, iters=300, lr=0.1):
    """Regressão logística simples (com regularização), por descida de gradiente."""
    X = np.asarray(X, float); y = np.asarray(y, float)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]
    w = np.zeros(Z.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Z @ w))
        grad = Z.T @ (p - y) / len(y) + l2 * np.r_[0, w[1:]] / len(y)
        w -= lr * grad * 10
    return w, mu, sd


def prever(modelo, x):
    w, mu, sd = modelo
    z = np.r_[1, (np.asarray(x, float) - mu) / sd]
    return 1 / (1 + math.exp(-z @ w))


def testar():
    linhas = carregar_e_montar()
    dias = sorted({l["g"]["data"] for l in linhas})
    previsoes = []
    for dia in dias:
        treino = [l for l in linhas if l["g"]["data"] < dia and l["pronto"]]
        hoje = [l for l in linhas if l["g"]["data"] == dia and l["pronto"]]
        if len(treino) < 200 or not hoje:
            continue
        modelo = treinar([l["x"] for l in treino], [l["y"] for l in treino])
        for l in hoje:
            previsoes.append((l["g"]["temporada"], prever(modelo, l["x"]), l["y"], l["g"]))
    return previsoes


def carregar_e_montar():
    return montar_sinais(carregar())


def relatorio(previsoes):
    nomes = {"2026": "Temporada passada (2025-26)", "2027": "Temporada atual (2026-27)"}
    for temp in ("2026", "2027"):
        P = [p for p in previsoes if p[0] == temp]
        if not P:
            continue
        print(f"\n{nomes[temp]}")
        print("  confiança mínima | apostas | acertos | erros | % acerto | lucro por R$100 a odd 1,85")
        for lim in (0.50, 0.53, 0.55, 0.57, 0.60):
            sel = [(p, y) for _, p, y, _ in P if abs(p - 0.5) >= lim - 0.5]
            if not sel:
                continue
            ok = sum((p > 0.5) == bool(y) for p, y in sel)
            lucro = 100 * (ok * 0.85 - (len(sel) - ok)) / len(sel)
            print(f"  {lim:>15.0%} | {len(sel):>7} | {ok:>7} | {len(sel) - ok:>5} | {ok / len(sel):>7.1%} | {lucro:+.1f}")
        base = sum(y for _, _, y, _ in P)
        print(f"  (referência: {base} jogos passaram da linha e {len(P) - base} ficaram abaixo)")


if __name__ == "__main__":
    relatorio(testar())
