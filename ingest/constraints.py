"""Chaves primárias e estrangeiras no PostgreSQL.

Dois papéis:
 1. Integridade: falha se a limpeza deixou duplicatas ou observações sem boletim/estação.
 2. Desempenho do Ontop: com chaves declaradas, o Ontop elimina SELECT DISTINCT e ramos de UNION
    redundantes criados pelo raciocínio OWL 2 QL (ex.: estações "derivadas" de met:reportOf).
"""
import sys, time
import psycopg

PG = sys.argv[1] if len(sys.argv) > 1 else "host=127.0.0.1 port=5433 user=postgres dbname=met"
OBS = ["air_temp", "wet_bulb", "dew_point", "rel_humidity", "runway_temp", "qnh", "visibility",
       "wind_speed", "wind_dir", "wind_gust", "precip", "precip_duration", "cloud_layer"]

STMTS = [
    "ALTER TABLE report ADD PRIMARY KEY (sigla, tmin)",
    "ALTER TABLE report ADD FOREIGN KEY (sigla) REFERENCES station(sigla)",
    "ALTER TABLE station_sensor ADD FOREIGN KEY (sigla) REFERENCES station(sigla)",
]
for n in OBS:
    STMTS += [
        f"ALTER TABLE obs_{n} ADD PRIMARY KEY (sigla, tmin, seq)",
        f"ALTER TABLE obs_{n} ADD FOREIGN KEY (sigla, tmin) REFERENCES report(sigla, tmin)",
        f"ALTER TABLE obs_{n} ADD FOREIGN KEY (sigla) REFERENCES station(sigla)",
    ]

def exists(c, stmt):
    """Verifica no catálogo se a restrição descrita por `stmt` já existe (idempotência)."""
    table = stmt.split()[2]
    kind = "p" if "PRIMARY KEY" in stmt else "f"
    cols = stmt.split("(")[1].split(")")[0].replace(" ", "")
    for (d,) in c.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = %s::regclass AND contype = %s",
                          (table, kind)).fetchall():
        if d.split("(")[1].split(")")[0].replace(" ", "") == cols and (kind == "p" or stmt.split("REFERENCES ")[1].split("(")[0] in d):
            return True
    return False


def dedupe_fks(c):
    """Remove chaves estrangeiras duplicadas (mesma definição) deixadas por execuções anteriores."""
    rows = c.execute("""SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) FROM pg_constraint
                        WHERE contype = 'f' ORDER BY 1, 2""").fetchall()
    seen = set()
    for table, name, d in rows:
        if (table, d) in seen:
            c.execute(f'ALTER TABLE {table} DROP CONSTRAINT "{name}"')
            print("removida duplicata", table, name)
        seen.add((table, d))


with psycopg.connect(PG, autocommit=True) as c:
    dedupe_fks(c)
    for s in STMTS:
        if exists(c, s):
            continue
        t0 = time.time()
        c.execute(s)
        print(f"ok  {time.time()-t0:5.1f}s  {s}", flush=True)
    # A reexportação recria tabelas e perde permissões: reaplica leitura ao usuário do Ontop.
    if c.execute("SELECT 1 FROM pg_roles WHERE rolname = 'kgqa_reader'").fetchone():
        c.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO kgqa_reader")
        print("permissões de leitura reaplicadas a kgqa_reader")
