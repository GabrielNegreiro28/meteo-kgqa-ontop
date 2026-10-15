"""Desempacota os arquivos .npz gerados por pack.py (no computador do Gabriel) e confere estatísticas."""
import hashlib, json, sys
from pathlib import Path
import numpy as np, pandas as pd

EPOCH = pd.Timestamp("2016-01-01")

def unpack(npz: Path) -> pd.DataFrame:
    meta = json.loads(Path(str(npz) + ".json").read_text(encoding="utf-8"))
    sha = Path(str(npz) + ".sha256").read_text().strip()
    assert hashlib.sha256(npz.read_bytes()).hexdigest() == sha, f"sha256 divergente: {npz}"
    z = np.load(npz)
    mins = np.cumsum(z["t_delta"].astype(np.int64))
    st = meta["stats"]["t"]
    assert (int(mins.sum()), int(mins.min()), int(mins.max())) == (st["sum"], st["min"], st["max"]), "tempo"
    cols = {meta["tcol"]: EPOCH + pd.to_timedelta(mins, unit="m")}
    for c, info in meta["cols"].items():
        a = z[c]
        if info["kind"] == "cat":
            s = pd.Categorical.from_codes(a.astype(np.int32), categories=info["cats"]) if (a >= 0).all() \
                else pd.Categorical.from_codes(a.astype(np.int32), categories=info["cats"])
            cols[c] = s
            got = pd.Series(s).value_counts()
            assert {k: int(v) for k, v in got.items() if v} == {k: v for k, v in meta["stats"][c]["counts"].items() if v}, c
        else:
            v = a.astype(np.int64); nn = v != info["null"]
            s = meta["stats"][c]
            assert int((~nn).sum()) == s["null"] and int(v[nn].sum()) == s["sum10"], c
            cols[c] = pd.Series(np.where(nn, v / 10.0, np.nan))
    df = pd.DataFrame(cols)[[c for c in meta["columns"]]]
    assert len(df) == meta["rows"]
    return df

if __name__ == "__main__":
    for p in sys.argv[1:]:
        df = unpack(Path(p)); print(p, len(df), "linhas OK"); print(df.head(3).to_string())
