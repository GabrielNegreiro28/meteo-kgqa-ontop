"""Immutable snapshot manifest. Run after a clean load, never during a question.

python -m ingest.manifest --raw ../METEOROLOGIA --database met.duckdb --out snapshot.json
Coverage JSON is keyed by station IRI then measure IRI, with start/end/n fields.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def coverage_from_database(database):
    """Perfil por estação/grandeza sobre a mesma camada limpa usada pelo oráculo."""
    import duckdb
    from ontology.catalog import load as catalog_load
    from metqa.knowledge.index import STATION_NS
    coverage = {}
    with duckdb.connect(str(database), read_only=True, config={"enable_external_access": False}) as db:
        for q in catalog_load()[0].values():
            # Identificadores vêm exclusivamente do catálogo versionado.
            if not db.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='clean' AND table_name=?", [q.table]).fetchone()[0]:
                continue
            for station, start, end, n in db.execute(
                f'SELECT sigla, min(local_date), max(local_date), count(*) FROM clean."{q.table}" '
                f'WHERE "{q.column}" IS NOT NULL GROUP BY sigla'
            ).fetchall():
                iri = STATION_NS + station
                coverage.setdefault(iri, {})[q.iri] = {'start': str(start), 'end': str(end), 'n': n}
    return coverage


def build(raw, coverage, database=None):
    files = sorted(Path(raw).glob('*.csv'))
    if not files:
        raise ValueError('no raw CSV files')
    artifacts = [*sorted((ROOT / 'ingest').glob('*.py')), ROOT / 'mapping/met.obda', ROOT / 'ontology/catalog.py',
                 *sorted((ROOT / 'ontology').rglob('*.ttl'))]
    body = {'version': 1, 'raw': {p.name: digest(p) for p in files},
            'artifacts': {str(p.relative_to(ROOT)): digest(p) for p in artifacts},
            'coverage': coverage, 'coverage_complete': False,
            'hypotheses': {'timezone': 'UTC-03:00', 'quality_policy': 'R1-R7/Q1-Q5',
                           'expert_approved': False}}
    if database is not None:
        body['clean_database_sha256'] = digest(database)
    body['snapshot_id'] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return body


def load(path):
    body = json.loads(Path(path).read_text(encoding='utf-8'))
    expected = body.pop('snapshot_id')
    if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != expected:
        raise ValueError('snapshot manifest changed')
    return {**body, 'snapshot_id': expected}


def verify_database(manifest, database):
    expected = manifest.get('clean_database_sha256')
    if not expected or digest(database) != expected:
        raise ValueError('clean database does not match snapshot manifest')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--raw', required=True)
    ap.add_argument('--coverage', help='perfil JSON revisado; sem ele, extrai da base limpa')
    ap.add_argument('--database', required=True, help='snapshot DuckDB fechado após a limpeza')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    coverage = json.loads(Path(a.coverage).read_text(encoding='utf-8')) if a.coverage else coverage_from_database(a.database)
    manifest = build(a.raw, coverage, a.database)
    with Path(a.out).open('x', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)


if __name__ == '__main__':
    main()
