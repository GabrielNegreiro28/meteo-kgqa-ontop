"""Confere a base LIMPA contra os METAR (UTC): a temperatura em `t_utc` tem de bater com o METAR do mesmo instante, antes e depois da troca
de relógio de abril de 2021; e a hora civil (`t_local`) do pico de temperatura não pode saltar na troca.
Uso (WSL): python data/conferir_base_limpa_metar.py <met.duckdb>
"""
import csv, glob, json, os, sys
from datetime import datetime

import duckdb


def main():
    c = duckdb.connect(sys.argv[1], read_only=True)
    out = {"metar": {}, "hora_do_pico_local": {}}
    for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "metar_amostra", "*.csv"))):
        sigla, per = os.path.basename(f)[:-4].split("_")
        metar = {datetime.strptime(r["valid"], "%Y-%m-%d %H:%M"): (float(r["tmpf"]) - 32) * 5 / 9
                 for r in csv.DictReader(open(f, encoding="utf-8")) if r["tmpf"]}
        rows = c.execute("""SELECT t_utc, avg(value) FROM clean.obs_air_temp WHERE sigla = ? AND t_utc BETWEEN ? AND ?
                            AND minute(t_utc) = 0 GROUP BY 1""", [sigla, min(metar), max(metar)]).fetchall()
        pares = [(t, float(v)) for t, v in rows if t in metar]
        out["metar"][f"{sigla}_{per}"] = {"pares": len(pares), "fracao_igual_0_5C": round(sum(abs(v - metar[t]) <= 0.5 for t, v in pares) / len(pares), 3)}
    for s in ("SBGR", "SBEG", "SBRB", "SBCG", "SBBE", "SBPA"):
        rows = c.execute("""WITH h AS (SELECT strftime(local_date, '%Y') y, hour(t_local) hh, avg(value) m FROM clean.obs_air_temp
                                        WHERE sigla = ? AND minute(t_local) = 0 GROUP BY 1, 2)
                            SELECT y, arg_max(hh, m) FROM h GROUP BY 1 ORDER BY 1""", [s]).fetchall()
        out["hora_do_pico_local"][s] = {y: h for y, h in rows}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
