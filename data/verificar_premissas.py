"""Testa nos próprios dados as premissas que o dicionário marcou como hipótese (H). Só lê o DuckDB; não altera nada.

Uso (WSL): python data/verificar_premissas.py <met.duckdb> data/estacoes.csv > data/premissas_resultado.json

T1 fuso: fase do ciclo diário da temperatura (1º harmônico) no relógio dos dados, por estação. Convertida para hora solar sob cada hipótese
   sobre o relógio (UTC−3 fixo, hora legal da UF, UTC), a fase correta é a mesma em todos os fusos legais e não depende da longitude.
T2 horário de verão: nos estados que o tinham, a fase de dez–jan de 2016–2018 (com horário de verão) muda em relação a 2020–2024 (sem)?
   Comparado com os estados que nunca tiveram (diferença das diferenças). Hora legal daria +1 h; relógio fixo, ~0.
T3 unidades: visibilidade (degraus do METAR em dezenas de metros), base de nuvem por gênero e chuva anual contra normais climatológicas.
T4 boletins fora da hora cheia: minutos e se acompanham tempo pior (visibilidade menor, chuva), como SPECI.
T5 consistência entre variáveis na base limpa: orvalho > temperatura, bulbo úmido > seco.
"""
from __future__ import annotations

import csv
import json
import math
import statistics as st
import sys

import duckdb

VALID_T = "bseco BETWEEN -30 AND 50"


def phase(hour_means: dict[int, float]) -> float | None:
    """Hora do máximo do 1º harmônico (0–24)."""
    if len(hour_means) < 20:
        return None
    a = sum(v * math.cos(2 * math.pi * h / 24) for h, v in hour_means.items())
    b = sum(v * math.sin(2 * math.pi * h / 24) for h, v in hour_means.items())
    return (math.atan2(b, a) * 24 / (2 * math.pi)) % 24


def wrap(x: float) -> float:
    return (x + 12) % 24 - 12


def slope(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


def phases(c, where: str) -> dict[str, float]:
    rows = c.sql(f"""SELECT sigla, hour(hora_observacao) h, avg(bseco) m, count(*) n FROM raw_temperatura
                     WHERE minute(hora_observacao) = 0 AND {VALID_T} AND {where} GROUP BY 1, 2""").fetchall()
    by: dict[str, dict[int, float]] = {}
    for s, h, m, n in rows:
        if n >= 30:
            by.setdefault(s, {})[h] = m
    return {s: p for s, hm in by.items() if (p := phase(hm)) is not None}


def t1(c, reg: dict[str, dict]) -> dict:
    ph = phases(c, "TRUE")
    hyps = {"UTC-3 fixo": lambda r: -3, "hora legal da UF": lambda r: int(r["fuso_legal"]), "UTC": lambda r: 0}
    out = {"estacoes": len([s for s in ph if s in reg]), "hipoteses": {}}
    for name, tz in hyps.items():
        groups: dict[int, list[float]] = {}
        xs, ys = [], []
        for s, p in ph.items():
            r = reg.get(s)
            if not r:
                continue
            solar = (p - tz(r) + float(r["lon"]) / 15) % 24           # relógio -> UTC -> hora solar média
            groups.setdefault(int(r["fuso_legal"]), []).append(solar)
            xs.append(float(r["lon"]))
            ys.append(solar)
        ref = st.mean(groups[-3])
        out["hipoteses"][name] = {
            "fase_solar_media_por_fuso_legal": {str(k): round(st.mean(v), 2) for k, v in sorted(groups.items())},
            "n_por_fuso_legal": {str(k): len(v) for k, v in sorted(groups.items())},
            "maior_desvio_entre_fusos_h": round(max(abs(wrap(st.mean(v) - ref)) for v in groups.values()), 2),
            "inclinacao_fase_x_longitude_h_por_grau": round(slope(xs, ys), 4)}
    out["fronteira"] = border(ph, reg)
    out["fase_no_relogio_por_estacao"] = {s: round(p, 2) for s, p in sorted(ph.items()) if s in reg}
    return out


def border(ph: dict[str, float], reg: dict[str, dict]) -> dict:
    """Fase no relógio ~ a + b·lon + c·lat + d·[fuso legal −4] + e·[−5], por mínimos quadrados, só com estações a até 8° de longitude da
    fronteira −3/−4 (o clima muda devagar com a longitude; o fuso legal muda de uma vez). Relógio fixo: d ≈ 0 e b ≈ −1/15 h por grau.
    Hora legal: d ≈ −1 (a estação a oeste da fronteira marca o mesmo instante solar uma hora mais cedo)."""
    import numpy as np
    rows = [(p, float(reg[s]["lon"]), float(reg[s]["lat"]), int(reg[s]["fuso_legal"])) for s, p in ph.items()
            if s in reg and -66 < float(reg[s]["lon"]) < -44 and int(reg[s]["fuso_legal"]) in (-3, -4)]
    y = np.array([r[0] for r in rows])
    X = np.array([[1, r[1], r[2], 1.0 if r[3] == -4 else 0.0] for r in rows])
    coef, res, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    sigma2 = resid @ resid / (len(y) - X.shape[1])
    se = np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X)))
    return {"estacoes": len(rows), "n_fuso_-4": int(X[:, 3].sum()),
            "salto_no_fuso_-4_h": round(float(coef[3]), 3), "erro_padrao_salto_h": round(float(se[3]), 3),
            "inclinacao_longitude_h_por_grau": round(float(coef[1]), 4), "erro_padrao_inclinacao": round(float(se[1]), 4),
            "esperado_relogio_fixo": {"salto": 0.0, "inclinacao": round(-1 / 15, 4)},
            "esperado_hora_legal": {"salto": -1.0, "inclinacao": round(-1 / 15, 4)}}


def t2(c, reg: dict[str, dict]) -> dict:
    with_dst = phases(c, "month(hora_observacao) IN (12, 1) AND hora_observacao >= DATE '2016-12-01' AND hora_observacao < DATE '2019-02-01'")
    without = phases(c, "year(hora_observacao) BETWEEN 2020 AND 2024 AND month(hora_observacao) IN (12, 1)")
    diff: dict[bool, list[float]] = {True: [], False: []}
    for s in with_dst.keys() & without.keys():
        r = reg.get(s)
        if r and r.get("horario_verao_ate_2019") in ("True", "False"):
            diff[r["horario_verao_ate_2019"] == "True"].append(wrap(with_dst[s] - without[s]))
    a, b = st.mean(diff[True]), st.mean(diff[False])
    return {"mudanca_media_h_estados_com_horario_de_verao": round(a, 3), "n_com": len(diff[True]),
            "mudanca_media_h_estados_sem": round(b, 3), "n_sem": len(diff[False]),
            "diferenca_das_diferencas_h": round(a - b, 3), "esperado_se_hora_legal": 1.0, "esperado_se_relogio_fixo": 0.0}


def t3(c) -> dict:
    vis = c.sql("""SELECT visibpre, count(*) n FROM raw_visibilidade WHERE visibpre IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT 12""").fetchall()
    vis_frac = c.sql("""SELECT avg(CASE WHEN visibpre < 500 AND visibpre % 5 = 0 THEN 1
                                         WHEN visibpre >= 500 AND visibpre < 1000 AND visibpre % 10 = 0 THEN 1
                                         WHEN visibpre >= 1000 AND visibpre % 100 = 0 THEN 1 ELSE 0 END),
                               max(visibpre), avg(CASE WHEN visibpre = 2000 THEN 1 ELSE 0 END)
                        FROM raw_visibilidade WHERE visibpre IS NOT NULL""").fetchone()
    nuv = c.sql("""SELECT tipo_nuvem, median(altnuvem) med, count(*) n FROM raw_nuvem WHERE altnuvem > 0 GROUP BY 1 HAVING n > 10000
                   ORDER BY med""").fetchall()
    # chuva anual média 2016–2025 na base limpa (anos com ≥ 90 % das horas cheias com boletim de chuva)
    normais = {"SBBE": ("Belém", 3084), "SBEG": ("Manaus", 2307), "SBGR": ("Guarulhos", 1450), "SBBR": ("Brasília", 1477),
               "SBPA": ("Porto Alegre", 1504), "SBFZ": ("Fortaleza", 1608), "SBRF": ("Recife", 2263), "SBSV": ("Salvador", 2144),
               "SBCT": ("Curitiba", 1500), "SBCF": ("Belo Horizonte", 1600)}
    rows = c.sql(f"""SELECT sigla, year(local_date) y, sum(value) mm, count(*) n FROM clean.obs_precip
                     WHERE sigla IN ({','.join(repr(s) for s in normais)}) AND seq = 0 GROUP BY 1, 2""").fetchall()
    anual: dict[str, list[float]] = {}
    for s, y, mm, n in rows:
        if n >= 0.9 * 8760:
            anual.setdefault(s, []).append(float(mm))
    chuva = {s: {"cidade": normais[s][0], "media_mm": round(st.mean(v)), "anos": len(v), "normal_aprox_mm": normais[s][1],
                 "razao": round(st.mean(v) / normais[s][1], 2)} for s, v in anual.items()}
    return {"visibilidade_valores_mais_comuns": [[float(v), n] for v, n in vis], "visibilidade_fracao_nos_degraus_metar": round(vis_frac[0], 4),
            "visibilidade_max": float(vis_frac[1]), "visibilidade_fracao_2000": round(vis_frac[2], 3),
            "base_nuvem_mediana_dam_por_genero": [[t, float(m), n] for t, m, n in nuv], "chuva_anual": chuva}


def t4(c) -> dict:
    mins = c.sql("""SELECT minute(hora_observacao) m, count(*) n FROM raw_visibilidade GROUP BY 1 ORDER BY n DESC LIMIT 8""").fetchall()
    tot = c.sql("SELECT count(*) FROM raw_visibilidade").fetchone()[0]
    cmp = c.sql("""SELECT minute(hora_observacao) = 0 cheia, avg(visibpre), avg(CASE WHEN visibpre < 500 THEN 1 ELSE 0 END), count(*)
                   FROM raw_visibilidade WHERE visibpre IS NOT NULL GROUP BY 1""").fetchall()
    return {"minutos_mais_comuns": [[m, n, round(n / tot, 4)] for m, n in mins],
            "hora_cheia_x_fora": {("hora cheia" if k else "fora da hora cheia"): {"vis_media_dam": round(v, 1), "fracao_vis_abaixo_5km": round(f, 4),
                                                                                 "boletins": n} for k, v, f, n in cmp}}


def t5(c) -> dict:
    td = c.sql("""SELECT count(*), sum(CASE WHEN d.value > a.value + 0.5 THEN 1 ELSE 0 END), sum(CASE WHEN d.value > a.value + 2 THEN 1 ELSE 0 END)
                  FROM clean.obs_air_temp a JOIN clean.obs_dew_point d USING (sigla, t_utc) WHERE a.seq = 0 AND d.seq = 0""").fetchone()
    wb = c.sql("""SELECT count(*), sum(CASE WHEN w.value > a.value + 0.5 THEN 1 ELSE 0 END)
                  FROM clean.obs_air_temp a JOIN clean.obs_wet_bulb w USING (sigla, t_utc) WHERE a.seq = 0 AND w.seq = 0""").fetchone()
    return {"orvalho_acima_da_temperatura": {"pares": td[0], "mais_de_0_5C": td[1], "mais_de_2C": td[2]},
            "bulbo_umido_acima_do_seco": {"pares": wb[0], "mais_de_0_5C": wb[1]}}


def main() -> None:
    c = duckdb.connect(sys.argv[1], read_only=True)
    c.execute("SET memory_limit = '2GB'; SET threads = 2")
    reg = {r["sigla"]: r for r in csv.DictReader(open(sys.argv[2], encoding="utf-8")) if r.get("lon")}
    out = {}
    for name, fn in (("T1_fuso", lambda: t1(c, reg)), ("T2_horario_de_verao", lambda: t2(c, reg)), ("T3_unidades", lambda: t3(c)),
                     ("T4_fora_da_hora_cheia", lambda: t4(c)), ("T5_consistencia", lambda: t5(c))):
        out[name] = fn()
        print(name, "ok", file=sys.stderr, flush=True)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
