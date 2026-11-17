import json
from decimal import Decimal

import duckdb
import pytest

from eval.clean_reference import compare, freeze
from ingest import manifest
from tests.test_metqa import nir
from tests.test_metqa_shapes import ask, lit, table, XD


@pytest.fixture
def snapshot(tmp_path):
    database = tmp_path / 'met.duckdb'
    with duckdb.connect(str(database)) as db:
        db.execute('CREATE SCHEMA clean')
        db.execute('CREATE TABLE clean.obs_air_temp(sigla VARCHAR, local_date DATE, value DECIMAL(8,4))')
        db.execute("INSERT INTO clean.obs_air_temp VALUES ('SBGL', '2020-01-01', 20), ('SBGL', '2020-01-02', 30), ('SBGR', '2020-01-01', 15)")
    (tmp_path / 'temperatura.csv').write_text('sigla,value\nSBGL,20\n', encoding='utf-8')
    coverage = manifest.coverage_from_database(database)
    body = manifest.build(tmp_path, coverage, database)
    return database, body


def test_snapshot_profiles_and_detects_tampering(snapshot, tmp_path):
    database, body = snapshot
    station = 'https://example.org/kgqa-met/data/station/SBGL'
    measure = 'https://example.org/kgqa-met/ontology#AirTemperature'
    assert body['coverage'][station][measure] == {'start': '2020-01-01', 'end': '2020-01-02', 'n': 2}
    from tests.test_metqa_shapes import CAT
    from metqa.knowledge import DomainCatalog
    from metqa.understanding import parse
    catalog = DomainCatalog(CAT.index)
    catalog.snapshot = body
    query = parse(nir('met:AirTemperature', ['st:SBGL'], 'avg')).parts[0][1]
    assert catalog.coverage_for(query)['stations'][station]['n'] == 2
    file = tmp_path / 'snapshot.json'
    file.write_text(json.dumps(body), encoding='utf-8')
    assert manifest.load(file) == body
    manifest.verify_database(body, database)
    body['coverage'][station][measure]['n'] = 999
    file.write_text(json.dumps(body), encoding='utf-8')
    with pytest.raises(ValueError, match='changed'):
        manifest.load(file)


def test_clean_oracle_aligns_columns_and_checks_units(snapshot):
    database, body = snapshot
    units = {'value': 'http://qudt.org/vocab/unit/DEG_C'}
    spec = {'cases': [{'id': 'X', 'expected_status': 'answered', 'parts': [
        {'sql': "SELECT avg(value) AS value, count(*) AS n FROM clean.obs_air_temp WHERE sigla='SBGL'", 'units': units}]}]}
    reference = freeze(database, body, spec)['cases']['X']
    response, _ = ask(nir('met:AirTemperature', ['st:SBGL'], 'avg', '2020-01-01', '2020-01-02'),
                      table({'n': lit(2), 'value': lit(25, XD)}))
    assert compare(response, reference)
    response.result_shape[0]['units']['value'] = 'http://qudt.org/vocab/unit/K'
    assert not compare(response, reference)
    with pytest.raises(ValueError, match='missing'):
        compare(response, None)


def test_reference_refuses_writes_and_different_database(snapshot):
    database, body = snapshot
    spec = {'cases': [{'id': 'X', 'expected_status': 'answered', 'parts': [{'sql': 'DELETE FROM clean.obs_air_temp'}]}]}
    with pytest.raises(ValueError, match='SELECT'):
        freeze(database, body, spec)
    with duckdb.connect(str(database)) as db:
        db.execute("INSERT INTO clean.obs_air_temp VALUES ('SBGL', '2020-01-03', 10)")
    with pytest.raises(ValueError, match='snapshot'):
        manifest.verify_database(body, database)
