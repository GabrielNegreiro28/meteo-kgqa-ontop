"""Quanto a correção do relógio (R1) muda a base limpa: compara a camada limpa antiga (UTC−3 fixo) com a nova, linha a linha pelo `src_row`.
Uso (WSL): python data/efeito_correcao_fuso.py <antes.duckdb> <depois.duckdb> > data/efeito_correcao_fuso.json
"""
import json, sys

import duckdb


def main():
    c = duckdb.connect()
    c.execute("SET memory_limit = '2GB'; SET threads = 2")
    c.execute(f"ATTACH '{sys.argv[1]}' AS a (READ_ONLY); ATTACH '{sys.argv[2]}' AS d (READ_ONLY)")
    per = "CASE WHEN d.t_utc < TIMESTAMP '2021-04-16' THEN 'ate_15_04_2021' ELSE 'desde_16_04_2021' END"
    out = {}
    out["leituras_de_temperatura_com_outro_dia_local"] = {
        k: {"leituras": n, "fracao_dia_diferente": round(f, 4), "fracao_hora_diferente": round(h, 4)} for k, n, f, h in c.sql(f"""
        SELECT {per} p, count(*), avg(CASE WHEN a.local_date <> d.local_date THEN 1 ELSE 0 END),
               avg(CASE WHEN hour(a.t_local) <> hour(d.t_local) THEN 1 ELSE 0 END)
        FROM a.clean.obs_air_temp a JOIN d.clean.obs_air_temp d USING (src_row, seq) GROUP BY 1 ORDER BY 1""").fetchall()}
    for name, table, agg, tol in (("chuva_diaria", "obs_precip", "sum", 0.05), ("temperatura_maxima_diaria", "obs_air_temp", "max", 0.05)):
        q = f"""WITH x AS (SELECT sigla, local_date, {agg}(value) v FROM a.clean.{table} WHERE seq = 0 GROUP BY 1, 2),
                     y AS (SELECT sigla, local_date, {agg}(value) v FROM d.clean.{table} WHERE seq = 0 GROUP BY 1, 2)
                SELECT CASE WHEN local_date < DATE '2021-04-16' THEN 'ate_15_04_2021' ELSE 'desde_16_04_2021' END p, count(*),
                       avg(CASE WHEN x.v IS NULL OR y.v IS NULL OR abs(x.v - y.v) > {tol} THEN 1 ELSE 0 END)
                FROM x FULL JOIN y USING (sigla, local_date) GROUP BY 1 ORDER BY 1"""
        out[name] = {k: {"estacao_dias": n, "fracao_com_valor_diferente": round(f, 4)} for k, n, f in c.sql(q).fetchall()}
    # exemplo concreto: chuva diária de Guarulhos nos dias mais chuvosos de 2023
    out["exemplo_SBGR_2023_maiores_chuvas_diarias"] = [
        {"dia": str(day), "antes_mm": float(va) if va is not None else None, "depois_mm": float(vd) if vd is not None else None}
        for day, va, vd in c.sql("""
        WITH x AS (SELECT local_date, sum(value) v FROM a.clean.obs_precip WHERE sigla = 'SBGR' AND seq = 0 AND year(local_date) = 2023 GROUP BY 1),
             y AS (SELECT local_date, sum(value) v FROM d.clean.obs_precip WHERE sigla = 'SBGR' AND seq = 0 AND year(local_date) = 2023 GROUP BY 1)
        SELECT local_date, x.v, y.v FROM x FULL JOIN y USING (local_date) ORDER BY greatest(coalesce(x.v, 0), coalesce(y.v, 0)) DESC LIMIT 5""").fetchall()]
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
