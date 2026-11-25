"""Teste decisivo do fuso: compara a temperatura bruta de cada estação com os METAR da mesma estação, que vêm em UTC.

Fonte dos METAR: Iowa Environmental Mesonet (https://mesonet.agron.iastate.edu/request/download.phtml), amostras de 15 dias em
data/metar_amostra/<SIGLA>_<AAAAM>.csv. Para cada deslocamento k de 0 a 6 h, conta em quantas horas a temperatura bruta de `hora_observacao`
é igual (±0,5 °C) à do METAR de `hora_observacao + k`. O k com mais coincidências é o fuso do relógio dos dados (UTC = hora + k).
Uso (WSL): python data/verificar_fuso_metar.py <met.duckdb> data/estacoes.csv
"""
import csv, glob, json, os, sys
from datetime import datetime, timedelta

import duckdb


def main():
    c = duckdb.connect(sys.argv[1], read_only=True)
    reg = {r["sigla"]: r for r in csv.DictReader(open(sys.argv[2], encoding="utf-8"))}
    out = {}
    for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "metar_amostra", "*.csv"))):
        sigla, per = os.path.basename(f)[:-4].split("_")
        metar = {}
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if r["tmpf"]:
                metar[datetime.strptime(r["valid"], "%Y-%m-%d %H:%M")] = (float(r["tmpf"]) - 32) * 5 / 9
        lo, hi = min(metar), max(metar)
        raw = c.execute("""SELECT hora_observacao, avg(bseco) FROM raw_temperatura WHERE sigla = ? AND minute(hora_observacao) = 0
                           AND hora_observacao BETWEEN ? AND ? AND bseco IS NOT NULL GROUP BY 1""",
                        [sigla, lo - timedelta(hours=8), hi + timedelta(hours=8)]).fetchall()
        score = {}
        for k in range(0, 7):
            pares = [(t, v) for t, v in raw if t + timedelta(hours=k) in metar]
            iguais = sum(abs(v - metar[t + timedelta(hours=k)]) <= 0.5 for t, v in pares)
            score[k] = round(iguais / len(pares), 3) if pares else None
        best = max((k for k in score if score[k] is not None), key=lambda k: score[k])
        r = reg.get(sigla, {})
        out[f"{sigla}_{per}"] = {"uf": r.get("uf"), "fuso_legal": r.get("fuso_legal"), "horario_verao_vigente": per == "20181" and r.get("horario_verao_ate_2019") == "True",
                                 "fracao_coincidente_por_k": score, "melhor_k": best, "relogio": f"UTC−{best}"}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
