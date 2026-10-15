"""Carrega os .npz verificados em tabelas brutas do DuckDB (raw_*), sem transformar valores.
Uso: python ingest/load_raw.py <pasta_pack> <arquivo.duckdb>"""
import sys, time
from pathlib import Path
import duckdb
sys.path.insert(0, str(Path(__file__).parent))
from unpack import unpack

pack, db = Path(sys.argv[1]), sys.argv[2]
con = duckdb.connect(db)
for name in ["visibilidade", "precipitacao", "pressao", "temperatura", "vento", "nuvem"]:
    t0 = time.time()
    df = unpack(pack / f"{name}.npz")
    df = df.rename(columns={"hora_obs": "hora_observacao"})
    for c in df.columns:
        if str(df[c].dtype) == "category":
            df[c] = df[c].astype(str)
    df.insert(0, "row_id", range(len(df)))       # ordem original, para rastreabilidade
    con.execute(f"DROP TABLE IF EXISTS raw_{name}")
    con.execute(f"CREATE TABLE raw_{name} AS SELECT * FROM df")
    n = con.execute(f"SELECT COUNT(*) FROM raw_{name}").fetchone()[0]
    print(f"raw_{name}: {n} linhas em {time.time()-t0:.0f}s")
    del df
con.close()
