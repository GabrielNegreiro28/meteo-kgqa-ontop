"""Gera o mapeamento Ontop (sintaxe nativa .obda) da camada limpa no PostgreSQL para a ontologia met v0.2.

Padrão para cada variável escalar (uma tabela obs_<nome> por variável):
  ?obs a <classe> ; sosa:observedProperty <prop> ; sosa:madeBySensor d:sensor/<sigla>/<nome> ;
       sosa:hasFeatureOfInterest d:site/<sigla> ; sosa:phenomenonTime <instante ou intervalo> ;
       sosa:resultTime ; met:localDate ; met:localHour ; met:localWeekday ; met:inReport d:report/<sigla>/<tmin> ;
       met:multipleReadings ; met:sourceFile ; met:sourceRow ;
       sosa:hasResult [ qudt:numericValue ; qudt:unit ] .
O caminho estação → sensor → observação é o mesmo do grafo sintético, então as consultas de referência
do incremento 1 se transferem. Sensores são virtuais (um por estação e variável): a fonte não identifica
o instrumento.
As grandezas, as unidades, as tabelas e os arquivos de origem vêm do catálogo de grandezas (ontology/catalog.py), gerado da ontologia:
este arquivo só sabe a FORMA do mapeamento (e os atributos próprios do vento e da camada de nuvem).
Uso: python mapping/build_mapping.py > mapping/met.obda
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ontology.catalog import quantities  # noqa: E402

PREFIXES = {
    ":": "https://example.org/kgqa-met/data/",
    "met:": "https://example.org/kgqa-met/ontology#",
    "sosa:": "http://www.w3.org/ns/sosa/",
    "time:": "http://www.w3.org/2006/time#",
    "qudt:": "http://qudt.org/schema/qudt/",
    "unit:": "http://qudt.org/vocab/unit/",
    "rdfs:": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd:": "http://www.w3.org/2001/XMLSchema#",
    "skos:": "http://www.w3.org/2004/02/skos/core#",
}

WIND = {"wind_speed", "wind_dir", "wind_gust"}
# hora e dia da semana locais (UTC−3, D-85): colunas geradas no banco (ingest/export_pg.py::LOCAL_TIME)
LOCAL = "local_hour, local_weekday"


def common(name, prop, src, cls, time_node, multi=True):
    obs = f":obs/{name}/{{sigla}}/{{tmin}}/{{seq}}"
    return obs, (
        f"{obs} a {cls} ; sosa:observedProperty {prop} ; sosa:madeBySensor :sensor/{{sigla}}/{name} ; "
        f"sosa:hasFeatureOfInterest :site/{{sigla}} ; sosa:phenomenonTime {time_node} ; "
        f"sosa:resultTime {{t_utc}}^^xsd:dateTime ; met:localDate {{local_date}}^^xsd:date ; "
        f"met:localHour {{local_hour}}^^xsd:integer ; met:localWeekday {{local_weekday}}^^xsd:integer ; "
        f"met:inReport :report/{{sigla}}/{{tmin}} ; " + ("met:multipleReadings {multi}^^xsd:boolean ; " if multi else "") +
        f"met:sourceFile \"{src}\"^^xsd:string ; "
        f"met:sourceRow {{src_row}}^^xsd:integer ; sosa:hasResult :result/{name}/{{sigla}}/{{tmin}}/{{seq}} . "
    )


def scalar(name, prop, unit, xsd, src, accum=False, table=None, column="value"):
    out = []
    table = table or f"obs_{name}"
    own = table == f"obs_{name}"                     # tabela só desta grandeza (com `multi`); a camada de nuvem tem várias grandezas
    value = "value" if column == "value" else f"{column} AS value"
    if accum:
        tnode = f":interval/{name}/{{sigla}}/{{tmin}}/{{seq}}"
        obs, t = common(name, prop, src, "met:AccumulatedObservation", tnode)
        cols = f"sigla, tmin, t_utc, local_date, {LOCAL}, {value}, seq, multi, src_row"
    else:
        tnode = f":time/{name}/{{sigla}}/{{tmin}}/{{seq}}"
        obs, t = common(name, prop, src, "met:InstantaneousObservation", tnode, multi=own)
        cols = f"sigla, tmin, t_utc, local_date, {LOCAL}, {value}, seq" + (", multi" if own else "") + ", src_row" + (", runway" if name in WIND else "")
    if not accum:
        t += f"{tnode} a time:Instant ; time:inXSDDateTime {{t_utc}}^^xsd:dateTime . "
    t += (f":result/{name}/{{sigla}}/{{tmin}}/{{seq}} a qudt:QuantityValue ; "
          f"qudt:numericValue {{value}}^^{xsd} ; qudt:unit {unit} .")
    out.append((f"obs_{name}", t, f"SELECT {cols} FROM {table}" + ("" if column == "value" else f" WHERE {column} IS NOT NULL")))
    if name == "cloud_base":                         # o gênero da camada é atributo da base (ex.: "a base mais baixa e de que nuvem")
        out.append(("obs_cloud_base_genus", f"{obs} met:cloudGenus <https://example.org/kgqa-met/ontology#genus_{{genus_code}}> .",
                    "SELECT sigla, tmin, seq, CASE genus WHEN 'CI e/ou CC' THEN 'CI_CC' ELSE genus END AS genus_code "
                    "FROM obs_cloud_layer WHERE base_m IS NOT NULL AND genus IS NOT NULL"))
    if name in WIND:
        out.append((f"obs_{name}_runway", f"{obs} met:runwayDesignator {{runway}}^^xsd:string .",
                    f"SELECT sigla, tmin, seq, runway FROM obs_{name} WHERE runway IS NOT NULL"))
    if name == "wind_speed":
        out.append(("obs_wind_condition", f"{obs} met:windCondition {{condition}}^^xsd:string .",
                    "SELECT sigla, tmin, seq, condition FROM obs_wind_speed WHERE condition IS NOT NULL"))
    if accum:
        iv = f":interval/{name}/{{sigla}}/{{tmin}}/{{seq}}"
        b = f":time/{name}/start/{{sigla}}/{{tmin}}/{{seq}}"
        e = f":time/{name}/end/{{sigla}}/{{tmin}}/{{seq}}"
        out.append((f"interval_{name}",
                    f"{iv} a time:Interval ; time:hasBeginning {b} ; time:hasEnd {e} . "
                    f"{b} a time:Instant ; time:inXSDDateTime {{start_utc}}^^xsd:dateTime . "
                    f"{e} a time:Instant ; time:inXSDDateTime {{t_utc}}^^xsd:dateTime .",
                    f"SELECT sigla, tmin, seq, start_utc, t_utc FROM obs_{name}"))
    return out


def all_mappings():
    m = [
        ("station", ":station/{sigla} a met:WeatherStation ; met:stationCode {sigla}^^xsd:string ; "
                    "rdfs:label {sigla}^^xsd:string . :site/{sigla} a met:Site ; met:siteOf :station/{sigla} .",
         "SELECT sigla FROM station"),
        ("station_sensor", ":station/{sigla} sosa:hosts :sensor/{sigla}/{var} . :sensor/{sigla}/{var} a sosa:Sensor .",
         "SELECT sigla, var FROM station_sensor"),
        ("report", ":report/{sigla}/{tmin} a met:WeatherReport ; met:reportOf :station/{sigla} ; "
                   "time:hasTime :time/report/{sigla}/{tmin} ; met:localDate {local_date}^^xsd:date ; met:isHourly {is_hourly}^^xsd:boolean . "
                   ":time/report/{sigla}/{tmin} a time:Instant ; time:inXSDDateTime {t_utc}^^xsd:dateTime .",
         "SELECT sigla, tmin, t_utc, local_date, is_hourly FROM report"),
    ]
    for q in quantities().values():
        if q.observed_as != "CloudLayerObservation":
            m += scalar(q.sensor, f"met:{q.name}", f"unit:{q.unit}", f"xsd:{q.datatype}", q.source_file, q.accumulated, q.table, q.column)
    obs, t = common("cloud", "met:CloudCover", "nuvem.csv", "met:CloudLayerObservation", ":time/cloud/{sigla}/{tmin}/{seq}", multi=False)
    t += (":time/cloud/{sigla}/{tmin}/{seq} a time:Instant ; time:inXSDDateTime {t_utc}^^xsd:dateTime . "
          ":result/cloud/{sigla}/{tmin}/{seq} a met:CloudLayerResult ; met:skyObscured {sky_obscured}^^xsd:boolean .")
    m.append(("obs_cloud", t, f"SELECT sigla, tmin, t_utc, local_date, {LOCAL}, seq, src_row, sky_obscured FROM obs_cloud_layer"))
    for col, prop, xsd in [("okta", "met:oktas", "xsd:integer"), ("base_m", "met:cloudBaseHeight", "xsd:integer"),
                           ("cloud_movement", "met:cloudMovement", "xsd:string")]:
        m.append((f"cloud_{col}", f":result/cloud/{{sigla}}/{{tmin}}/{{seq}} {prop} {{{col}}}^^{xsd} .",
                  f"SELECT sigla, tmin, seq, {col} FROM obs_cloud_layer WHERE {col} IS NOT NULL"))
    m.append(("cloud_genus", ":result/cloud/{sigla}/{tmin}/{seq} met:cloudGenus <https://example.org/kgqa-met/ontology#genus_{genus_code}> .",
              "SELECT sigla, tmin, seq, CASE genus WHEN 'CI e/ou CC' THEN 'CI_CC' ELSE genus END AS genus_code "
              "FROM obs_cloud_layer WHERE genus IS NOT NULL"))
    return m


def render():
    lines = ["[PrefixDeclaration]"]
    lines += [f"{k}\t\t{v}" for k, v in PREFIXES.items()]
    lines += ["", "[MappingDeclaration] @collection [["]
    for mid, target, source in all_mappings():
        lines += [f"mappingId\t{mid}", f"target\t\t{target}", f"source\t\t{source}", ""]
    lines += ["]]"]
    return "\n".join(lines)


if __name__ == "__main__":
    print(render())
