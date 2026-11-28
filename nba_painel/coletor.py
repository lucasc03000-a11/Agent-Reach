#!/usr/bin/env python3
"""Coletor de dados da NBA para o painel (fonte: API pública da ESPN).

Uso:  python3 coletor.py [--ontem AAAAMMDD] [--hoje AAAAMMDD] [--saida PASTA]

Sem argumentos, "hoje" é a data atual no fuso do leste dos EUA e "ontem" o dia
anterior. Gera em PASTA (padrão: ./data) um JSON por tabela do painel:
jogos, projecoes, boxscore, times, jogadores, ultimos10, fotos, forma, estimativas,
ultimos_times, confrontos e palpites (este
último confere os palpites guardados em palpites_registrados.json contra os
resultados). Só usa a biblioteca padrão do Python; as fotos precisam do Pillow
(sem ele, a tabela de fotos sai vazia).
"""
import base64
import io
import argparse
import datetime as dt
import json
import math
import pathlib
import urllib.request
from zoneinfo import ZoneInfo

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
STAND = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
ATHL = ("https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/"
        "statistics/byathlete?region=us&lang=en&contentorigin=espn&isqualified=false"
        "&limit=50&sort=offensive.avgPoints%3Adesc&seasontype=2")
GAMELOG = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{}/gamelog"
FOTO = "https://a.espncdn.com/i/headshots/nba/players/full/{}.png"
MANDO = 2.5    # vantagem de jogar em casa, em pontos
DESVIO = 12.0  # desvio-padrão da margem de um jogo da NBA, em pontos
AQUI = pathlib.Path(__file__).resolve().parent


def baixar_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nba-painel/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def miniatura(url, largura):
    """Baixa uma imagem e devolve uma miniatura WebP como data: URL ('' se falhar)."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(baixar_bytes(url))).convert("RGBA")
        img = img.resize((largura, round(img.height * largura / img.width)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=72)
        return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def ultimos_jogos(atleta, n=10):
    """Os n jogos mais recentes de um jogador na temporada regular."""
    try:
        d = baixar(GAMELOG.format(atleta["jogador_id"]))
    except Exception:
        return []
    nomes, eventos, linhas = d.get("names") or [], d.get("events") or {}, []
    for tipo in d.get("seasonTypes") or []:
        if "Regular" not in (tipo.get("displayName") or ""):
            continue
        for cat in tipo.get("categories") or []:
            for e in cat.get("events") or []:
                ev, st = eventos.get(e["eventId"]), dict(zip(nomes, e.get("stats") or []))
                if not ev:
                    continue
                linhas.append({
                    "chave": f"{atleta['jogador_id']}-{e['eventId']}", "jogador_id": atleta["jogador_id"],
                    "jogador": atleta["jogador"], "data": (ev.get("gameDate") or "")[:10],
                    "adversario": ("@ " if ev.get("atVs") == "@" else "vs ") + (ev.get("opponent") or {}).get("abbreviation", ""),
                    "resultado": {"W": "V", "L": "D"}.get(ev.get("gameResult"), "") + " " + (ev.get("score") or ""),
                    "min": int(num(st.get("minutes"), 0)), "pts": int(num(st.get("points"), 0)),
                    "reb": int(num(st.get("totalRebounds"), 0)), "ast": int(num(st.get("assists"), 0)),
                    "stl": int(num(st.get("steals"), 0)), "blk": int(num(st.get("blocks"), 0)),
                    "arremessos": st.get("fieldGoalsMade-fieldGoalsAttempted") or "",
                    "tres": st.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted") or "",
                })
    return sorted(linhas, key=lambda x: x["data"], reverse=True)[:n]


def jogos_do_time(time_id, temporada=None):
    """Jogos encerrados de um time na temporada regular, do mais antigo ao mais recente."""
    url = f"{SITE}/teams/{time_id}/schedule?seasontype=2" + (f"&season={temporada}" if temporada else "")
    try:
        d = baixar(url)
    except Exception:
        return []
    ano = ((d.get("requestedSeason") or d.get("season") or {}).get("year"))
    pts = lambda c: int(num(c["score"]["value"] if isinstance(c.get("score"), dict) else c.get("score"), 0))
    linhas = []
    for e in d.get("events") or []:
        comp = e["competitions"][0]
        if comp["status"]["type"]["state"] != "post":
            continue
        eu = [c for c in comp["competitors"] if c["team"]["id"] == time_id][0]
        adv = [c for c in comp["competitors"] if c["team"]["id"] != time_id][0]
        linhas.append({"data": e["date"][:10], "adversario_id": adv["team"]["id"],
                       "adversario": adv["team"]["abbreviation"], "local": "casa" if eu["homeAway"] == "home" else "fora",
                       "pts": pts(eu), "pts_sofridos": pts(adv), "ano": ano})
    return sorted(linhas, key=lambda x: x["data"])


def media_de(valores):
    return round(sum(valores) / len(valores), 1) if valores else None


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nba-painel/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def num(v, padrao=None):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return padrao


def classificacao():
    """Uma linha por time, com campanha e médias de pontos."""
    dados = baixar(STAND)
    times = {}
    for conf in dados["children"]:
        nome_conf = "Leste" if "East" in conf["name"] else "Oeste"
        for e in conf["standings"]["entries"]:
            s = {q["name"]: q.get("displayValue") for q in e["stats"]}
            t = e["team"]
            v, d = int(num(s.get("wins"), 0)), int(num(s.get("losses"), 0))
            times[t["id"]] = {
                "time_id": t["id"], "sigla": t["abbreviation"], "time": t["displayName"],
                "logo_url": ((t.get("logos") or [{}])[0]).get("href") or "",
                "conferencia": nome_conf, "vitorias": v, "derrotas": d,
                "aproveitamento": round(v / (v + d), 3) if v + d else 0.0,
                "pts_feitos": num(s.get("avgPointsFor"), 0.0),
                "pts_sofridos": num(s.get("avgPointsAgainst"), 0.0),
                "saldo": num(s.get("differential"), 0.0),
                "sequencia": s.get("streak") or "", "casa": s.get("Home") or "",
                "fora": s.get("Road") or "", "ultimos_10": s.get("Last Ten Games") or "",
            }
    return times


def jogadores():
    """Médias da temporada de todos os jogadores com minutos."""
    linhas, pagina, paginas = [], 1, 1
    while pagina <= paginas:
        d = baixar(f"{ATHL}&page={pagina}")
        paginas = d["pagination"]["pages"]
        nomes = {c["name"]: c["names"] for c in d["categories"]}
        for a in d["athletes"]:
            st = {}
            for c in a["categories"]:
                st.update(dict(zip(nomes[c["name"]], c["totals"])))
            at = a["athlete"]
            linhas.append({
                "jogador_id": at["id"], "jogador": at["displayName"],
                "time_id": str(at.get("teamId") or ""), "sigla": at.get("teamShortName") or "",
                "posicao": (at.get("position") or {}).get("abbreviation") or "",
                "jogos": int(num(st.get("gamesPlayed"), 0)), "min": num(st.get("avgMinutes"), 0.0),
                "pts": num(st.get("avgPoints"), 0.0), "reb": num(st.get("avgRebounds"), 0.0),
                "ast": num(st.get("avgAssists"), 0.0), "stl": num(st.get("avgSteals"), 0.0),
                "blk": num(st.get("avgBlocks"), 0.0), "fg_pct": num(st.get("fieldGoalPct"), 0.0),
                "tres_pct": num(st.get("threePointFieldGoalPct"), 0.0),
                "ll_pct": num(st.get("freeThrowPct"), 0.0),
            })
        pagina += 1
    return linhas


def modelo(casa, fora, liga_pts):
    """Margem esperada do mandante, chance de vitória e pontos esperados de cada time."""
    margem = casa["saldo"] - fora["saldo"] + MANDO
    prob_casa = 0.5 * (1 + math.erf(margem / (DESVIO * math.sqrt(2))))
    base_casa = casa["pts_feitos"] + fora["pts_sofridos"] - liga_pts
    base_fora = fora["pts_feitos"] + casa["pts_sofridos"] - liga_pts
    return margem, prob_casa, base_casa + MANDO / 2, base_fora - MANDO / 2


def coletar(ontem, hoje):
    times = classificacao()
    liga_pts = sum(t["pts_feitos"] for t in times.values()) / len(times)
    atletas = jogadores()
    media = {a["jogador_id"]: a for a in atletas}
    jogos, projecoes, boxscore = [], [], []
    forma, estimativas, ultimos_times, confrontos = [], [], [], []

    for dia, rotulo in ((ontem, "ontem"), (hoje, "hoje")):
        placar = baixar(f"{SITE}/scoreboard?dates={dia}")
        for ev in placar.get("events", []):
            comp = ev["competitions"][0]
            lado = {c["homeAway"]: c for c in comp["competitors"]}
            casa_c, fora_c = lado["home"], lado["away"]
            casa, fora = times.get(casa_c["team"]["id"]), times.get(fora_c["team"]["id"])
            if not casa or not fora:
                continue
            estado = ev["status"]["type"]["state"]  # pre | in | post
            status = {"pre": "Agendado", "in": "Ao vivo", "post": "Final"}[estado]
            margem, prob_casa, exp_casa, exp_fora = modelo(casa, fora, liga_pts)
            fav, prob_fav = (casa, prob_casa) if prob_casa >= 0.5 else (fora, 1 - prob_casa)
            resumo = baixar(f"{SITE}/summary?event={ev['id']}")
            pred = resumo.get("predictor") or {}
            espn_casa = num((pred.get("homeTeam") or {}).get("gameProjection"))
            pick = (resumo.get("pickcenter") or [{}])[0]
            pc, pf = int(num(casa_c.get("score"), 0)), int(num(fora_c.get("score"), 0))
            vencedor = ""
            if estado == "post":
                vencedor = casa["sigla"] if pc > pf else fora["sigla"]
            hora = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            jogo = f"{fora['sigla']} @ {casa['sigla']}"
            jogos.append({
                "jogo_id": ev["id"], "dia": rotulo, "data": f"{dia[:4]}-{dia[4:6]}-{dia[6:]}",
                "hora_brasilia": hora.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M"),
                "jogo": jogo, "visitante": fora["sigla"], "mandante": casa["sigla"],
                "visitante_nome": fora["time"], "mandante_nome": casa["time"],
                "status": status, "detalhe": ev["status"]["type"].get("shortDetail") or "",
                "pts_visitante": pf if estado != "pre" else None,
                "pts_mandante": pc if estado != "pre" else None, "vencedor": vencedor,
                "favorito": fav["sigla"], "prob_favorito": round(prob_fav * 100),
                "margem_modelo": round(abs(margem), 1),
                "exp_visitante": round(exp_fora), "exp_mandante": round(exp_casa),
                "total_modelo": round(exp_fora + exp_casa),
                "prob_espn_mandante": espn_casa, "linha_casas": pick.get("details") or "",
                "total_casas": pick.get("overUnder"),
                "favorito_venceu": (vencedor == fav["sigla"]) if vencedor else None,
            })

            fora_de_combate = set()
            for bloco in resumo.get("injuries") or []:
                for les in bloco.get("injuries") or []:
                    if (les.get("status") or "").lower() == "out":
                        fora_de_combate.add(str((les.get("athlete") or {}).get("id")))

            if estado == "pre":  # pontos por jogo: temporada x últimos jogos x adversário
                rec = {}
                for t, adv, local in ((fora, casa, "fora"), (casa, fora, "casa")):
                    g = jogos_do_time(t["time_id"])
                    no_local = [x for x in g if x["local"] == local]
                    rec[t["sigla"]] = r = {
                        "pf": media_de([x["pts"] for x in g]), "pa": media_de([x["pts_sofridos"] for x in g]),
                        "pf10": media_de([x["pts"] for x in g[-10:]]), "pa10": media_de([x["pts_sofridos"] for x in g[-10:]]),
                        "pf5": media_de([x["pts"] for x in g[-5:]]), "pa5": media_de([x["pts_sofridos"] for x in g[-5:]]),
                    }
                    forma.append({
                        "chave": f"{ev['id']}-{t['sigla']}", "jogo_id": ev["id"], "sigla": t["sigla"], "time": t["time"],
                        "local_hoje": local, "jogos": len(g),
                        "feitos_temporada": r["pf"], "feitos_ult10": r["pf10"], "feitos_ult5": r["pf5"],
                        "sofridos_temporada": r["pa"], "sofridos_ult10": r["pa10"], "sofridos_ult5": r["pa5"],
                        "feitos_no_local": media_de([x["pts"] for x in no_local]),
                        "sofridos_no_local": media_de([x["pts_sofridos"] for x in no_local]),
                        "adversario": adv["sigla"],
                    })
                    for x in g[-10:]:
                        ultimos_times.append({
                            "chave": f"{ev['id']}-{t['sigla']}-{x['data']}", "jogo_id": ev["id"], "sigla": t["sigla"],
                            "data": x["data"], "adversario": ("vs " if x["local"] == "casa" else "@ ") + x["adversario"],
                            "pts": x["pts"], "pts_sofridos": x["pts_sofridos"],
                            "resultado": "V" if x["pts"] > x["pts_sofridos"] else "D",
                        })
                    if t is fora:  # confronto direto: temporada atual ou, se não houver, a anterior
                        direto, temp = [x for x in g if x["adversario_id"] == adv["time_id"]], "Atual"
                        if not direto and g and g[0].get("ano"):
                            passada = jogos_do_time(t["time_id"], int(g[0]["ano"]) - 1)
                            direto, temp = [x for x in passada if x["adversario_id"] == adv["time_id"]], "Passada"
                        for x in direto:
                            confrontos.append({
                                "chave": f"{ev['id']}-{x['data']}", "jogo_id": ev["id"], "temporada": temp,
                                "data": x["data"], "local": casa["sigla"] if x["local"] == "fora" else fora["sigla"],
                                "visitante_hoje": fora["sigla"], "pts_visitante_hoje": x["pts"],
                                "mandante_hoje": casa["sigla"], "pts_mandante_hoje": x["pts_sofridos"],
                                "vencedor": fora["sigla"] if x["pts"] > x["pts_sofridos"] else casa["sigla"],
                            })
                a_, h_ = rec[fora["sigla"]], rec[casa["sigla"]]
                for ordem, (recorte, k) in enumerate((("Temporada", ""), ("Últimos 10 jogos", "10"), ("Últimos 5 jogos", "5"))):
                    if None in (a_["pf" + k], a_["pa" + k], h_["pf" + k], h_["pa" + k]):
                        continue
                    pv = round((a_["pf" + k] + h_["pa" + k]) / 2, 1)
                    pm = round((h_["pf" + k] + a_["pa" + k]) / 2, 1)
                    estimativas.append({
                        "chave": f"{ev['id']}-{ordem}", "jogo_id": ev["id"], "ordem": ordem, "recorte": recorte,
                        "visitante": fora["sigla"], "pts_visitante": pv, "mandante": casa["sigla"], "pts_mandante": pm,
                        "total": round(pv + pm, 1), "favorito": fora["sigla"] if pv > pm else casa["sigla"],
                        "margem": round(abs(pv - pm), 1),
                    })

            if estado == "pre":  # pontos esperados dos principais jogadores
                for t, adv in ((fora, casa), (casa, fora)):
                    fator = adv["pts_sofridos"] / liga_pts if liga_pts else 1.0
                    elenco = [a for a in atletas if a["time_id"] == t["time_id"]
                              and a["jogos"] >= 3 and a["jogador_id"] not in fora_de_combate]
                    for a in sorted(elenco, key=lambda x: -x["pts"])[:5]:
                        projecoes.append({
                            "chave": f"{ev['id']}-{a['jogador_id']}", "jogo_id": ev["id"],
                            "jogo": jogo, "jogador": a["jogador"], "sigla": t["sigla"],
                            "adversario": adv["sigla"], "media_pts": a["pts"],
                            "pts_esperados": round(a["pts"] * fator, 1),
                            "reb": a["reb"], "ast": a["ast"], "min": a["min"], "jogos": a["jogos"],
                            "defesa_adversario": adv["pts_sofridos"],
                        })
            elif estado == "post":  # o que cada jogador fez
                for bloco in (resumo.get("boxscore") or {}).get("players") or []:
                    t = times.get(bloco["team"]["id"])
                    adv = fora if t is casa else casa
                    for grupo in bloco.get("statistics") or []:
                        col = grupo.get("names") or []
                        for ja in grupo.get("athletes") or []:
                            st = dict(zip(col, ja.get("stats") or []))
                            if not st or num(st.get("MIN"), 0) == 0:
                                continue
                            ref = media.get(ja["athlete"]["id"]) or {}
                            pts = int(num(st.get("PTS"), 0))
                            boxscore.append({
                                "chave": f"{ev['id']}-{ja['athlete']['id']}", "jogo_id": ev["id"],
                                "jogo": jogo, "jogador": ja["athlete"]["displayName"],
                                "sigla": t["sigla"], "adversario": adv["sigla"],
                                "min": int(num(st.get("MIN"), 0)), "pts": pts,
                                "reb": int(num(st.get("REB"), 0)), "ast": int(num(st.get("AST"), 0)),
                                "arremessos": st.get("FG") or "", "tres": st.get("3PT") or "",
                                "media_pts": ref.get("pts"),
                                "acima_da_media": round(pts - ref["pts"], 1) if ref else None,
                            })

    # confere os palpites guardados contra os resultados
    final = {j["jogo"]: j for j in jogos if j["status"] == "Final"}
    arq = AQUI / "palpites_registrados.json"
    registrados = json.loads(arq.read_text()) if arq.exists() else []
    palpites = []
    for p in registrados:
        j = final.get(p["jogo"]) if p["data"] in {x["data"] for x in jogos} else None
        j = j if j and j["data"] == p["data"] else None
        linha = dict(p, chave=f"{p['data']} {p['jogo']}")
        if j:
            linha.update(resultado=f"{j['visitante']} {j['pts_visitante']} x {j['pts_mandante']} {j['mandante']}",
                         vencedor=j["vencedor"], situacao="Acertou" if j["vencedor"] == p["palpite"] else "Errou")
        else:
            linha.setdefault("resultado", "")
            linha.setdefault("vencedor", "")
            linha.setdefault("situacao", "Em aberto")
        palpites.append(linha)
    arq.write_text(json.dumps(palpites, ensure_ascii=False, indent=1) + "\n")

    # jogadores com ficha completa: os de hoje, os cestinhas de ontem e os 100 maiores pontuadores
    ids = [p["chave"].split("-")[1] for p in projecoes]
    ids += [b["chave"].split("-")[1] for b in sorted(boxscore, key=lambda b: -b["pts"])[:20]]
    ids += [a["jogador_id"] for a in sorted(atletas, key=lambda a: -a["pts"]) if a["jogos"] >= 3]   # todos, para a busca do painel
    ids = [i for i in dict.fromkeys(ids) if i in media]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        logs = list(ex.map(lambda i: ultimos_jogos(media[i]), ids))
        fts = list(ex.map(lambda i: miniatura(FOTO.format(i), 160), ids))
    ultimos10 = [linha for lg in logs for linha in lg]
    fotos = [{"chave": i, "foto": f} for i, f in zip(ids, fts) if f]
    for t in times.values():
        logo = miniatura(t.pop("logo_url"), 72) if t.get("logo_url") else ""
        if logo:
            fotos.append({"chave": "time-" + t["sigla"], "foto": logo})

    return {"jogos": jogos, "projecoes": projecoes, "boxscore": boxscore,
            "ultimos10": ultimos10, "fotos": fotos, "forma": forma, "estimativas": estimativas,
            "ultimos_times": ultimos_times, "confrontos": confrontos,
            "times": sorted(times.values(), key=lambda t: -t["aproveitamento"]),
            "jogadores": atletas, "palpites": palpites}


def main():
    agora = dt.datetime.now(ZoneInfo("America/New_York"))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hoje", default=agora.strftime("%Y%m%d"))
    ap.add_argument("--ontem")
    ap.add_argument("--saida", default=str(AQUI / "data"))
    a = ap.parse_args()
    ontem = a.ontem or (dt.datetime.strptime(a.hoje, "%Y%m%d") - dt.timedelta(days=1)).strftime("%Y%m%d")
    tabelas = coletar(ontem, a.hoje)
    saida = pathlib.Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    meta = [
        {"label": "Fonte", "value": "API pública da ESPN (site.api.espn.com)"},
        {"label": "Coletado em (UTC)", "value": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")},
        {"label": "Datas", "value": f"ontem={ontem} hoje={a.hoje}"},
        {"label": "coletor.py", "value": pathlib.Path(__file__).read_text(), "type": "code", "lang": "python"},
    ]
    for nome, linhas in tabelas.items():
        (saida / f"{nome}.json").write_text(json.dumps({"rows": linhas, "meta": meta}, ensure_ascii=False))
        print(f"{nome}: {len(linhas)} linhas")


if __name__ == "__main__":
    main()
