"""Empacotador executado NO COMPUTADOR DE ORIGEM (onde estão os CSVs) para transferir os dados.

Converte um CSV em colunas numpy compactas, sem perda semântica, e grava estatísticas por coluna
(contagens, somas, mín/máx) calculadas a partir do CSV original. `unpack.py` confere essas estatísticas
e o SHA-256 do arquivo do outro lado. Validado linha a linha em visibilidade.csv (8,6 mi linhas idênticas).
Números com 1 casa decimal viram inteiros ×10; vazio vira -2^31; texto vira código de categoria.
Uso: python pack.py <arquivo.csv> <saida.npz>
"""
import sys, json, hashlib, os, numpy as np, pandas as pd

src, dst = sys.argv[1], sys.argv[2]
CAT = {"sigla", "cabeceira", "tipo_nuvem", "direcao_nuvem", "qtdnuvem"}
hdr = pd.read_csv(src, nrows=0).columns.tolist()
tcol = [c for c in hdr if c.startswith("hora")][0]
dt = {c: ("category" if c in CAT else "float64") for c in hdr if c != tcol}
dt[tcol] = str
df = pd.read_csv(src, dtype=dt, keep_default_na=False, na_values={c: [""] for c in hdr if c not in CAT and c != tcol})
meta = {"columns": hdr, "rows": len(df), "tcol": tcol, "cols": {}, "stats": {}}
ts = df[tcol]; assert ts.str.endswith(":00.000").all()
mins = ((pd.to_datetime(ts, format="%Y-%m-%d %H:%M:%S.%f") - pd.Timestamp("2016-01-01")) // pd.Timedelta(minutes=1)).values.astype(np.int64)
del ts; df.drop(columns=[tcol], inplace=True)
out = {"t_delta": np.diff(mins, prepend=0).astype(np.int32)}
meta["stats"]["t"] = {"sum": int(mins.sum()), "min": int(mins.min()), "max": int(mins.max())}
for c in df.columns:
    if c in CAT:
        cats = df[c].cat.categories.tolist(); codes = df[c].cat.codes.values.astype(np.int16)
        out[c] = codes; meta["cols"][c] = {"kind": "cat", "cats": [str(x) for x in cats]}
        meta["stats"][c] = {"counts": {str(k): int(v) for k, v in df[c].value_counts().items()}}
    else:
        x = df[c].values; nn = ~np.isnan(x)
        assert np.allclose(np.round(x[nn]*10)/10, x[nn], atol=1e-9), c
        v = np.where(nn, np.round(np.nan_to_num(x)*10), -2**31).astype(np.int64)
        out[c] = v.astype(np.int32); meta["cols"][c] = {"kind": "num10", "null": -2**31}
        meta["stats"][c] = {"null": int((~nn).sum()), "sum10": int(v[nn].sum()), "min10": int(v[nn].min()) if nn.any() else None, "max10": int(v[nn].max()) if nn.any() else None}
np.savez_compressed(dst, **out)
json.dump(meta, open(dst + ".json", "w"), ensure_ascii=False)
h = hashlib.sha256(open(dst, "rb").read()).hexdigest()
print(os.path.basename(src), len(df), "linhas ->", round(os.path.getsize(dst)/1e6, 1), "MB sha", h)
open(dst + ".sha256", "w").write(h)
