"""Gera o mapeamento Ontop (sintaxe nativa .obda) da camada limpa no PostgreSQL para a ontologia met v0.2.

Padrão para cada variável escalar (uma tabela obs_<nome> por variável):
  ?obs a <classe> ; sosa:observedProperty <prop> ; sosa:madeBySensor d:sensor/<sigla>/<nome> ;
       sosa:hasFeatureOfInterest d:site/<sigla> ; sosa:phenomenonTime <instante ou intervalo> ;
       sosa:resultTime ; met:localDate ; met:inReport d:report/<sigla>/<tmin> ;
       met:multipleReadings ; met:sourceFile ; met:sourceRow ;
       sosa:hasResult [ qudt:numericValue ; qudt:unit ] .
O caminho estação → sensor → observação é o mesmo do grafo sintético, então as consultas de referência
do incremento 1 se transferem. Sensores são virtuais (um por estação e variável): a fonte não identifica
o instrumento.
Uso: python mapping/build_mapping.py > mapping/met.obda
"""

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

# nome (=tabela obs_<nome>), propriedade, unidade, xsd do valor, arquivo de origem
INSTANT = [
    ("air_temp", "met:AirTemperature", "unit:DEG_C", "xsd:decimal", "temperatura.csv"),
    ("wet_bulb", "met:WetBulbTemperature", "unit:DEG_C", "xsd:decimal", "temperatura.csv"),
    ("dew_point", "met:DewPointTemperature", "unit:DEG_C", "xsd:decimal", "temperatura.csv"),
    ("rel_humidity", "met:RelativeHumidity", "unit:PERCENT", "xsd:decimal", "temperatura.csv"),
    ("runway_temp", "met:RunwayTemperature", "unit:DEG_C", "xsd:decimal", "temperatura.csv"),
    ("qnh", "met:PressureQNH", "unit:HectoPA", "xsd:decimal", "pressao.csv"),
    ("visibility", "met:PrevailingVisibility", "unit:M", "xsd:integer", "visibilidade.csv"),
    ("wind_speed", "met:WindSpeed", "unit:KN", "xsd:decimal", "vento.csv"),
    ("wind_dir", "met:WindDirection", "unit:DEG", "xsd:integer", "vento.csv"),
    ("wind_gust", "met:WindGust", "unit:KN", "xsd:decimal", "vento.csv"),
]
ACCUM = [
    ("precip", "met:Precipitation", "unit:MilliM", "xsd:decimal", "precipitacao.csv"),
    ("precip_duration", "met:PrecipitationDuration", "unit:MIN", "xsd:integer", "precipitacao.csv"),
]
WIND = {"wind_speed", "wind_dir", "wind_gust"}


def common(name, prop, src, cls, time_node):
    obs = f":obs/{name}/{{sigla}}/{{tmin}}/{{seq}}"
    return obs, (
        f"{obs} a {cls} ; sosa:observedProperty {prop} ; sosa:madeBySensor :sensor/{{sigla}}/{name} ; "
        f"sosa:hasFeatureOfInterest :site/{{sigla}} ; sosa:phenomenonTime {time_node} ; "
        f"sosa:resultTime {{t_utc}}^^xsd:dateTime ; met:localDate {{local_date}}^^xsd:date ; "
        f"met:inReport :report/{{sigla}}/{{tmin}} ; met:multipleReadings {{multi}}^^xsd:boolean ; met:sourceFile \"{src}\"^^xsd:string ; "
        f"met:sourceRow {{src_row}}^^xsd:integer ; sosa:hasResult :result/{name}/{{sigla}}/{{tmin}}/{{seq}} . "
    )


def scalar(name, prop, unit, xsd, src, accum=False):
    out = []
    if accum:
        tnode = f":interval/{name}/{{sigla}}/{{tmin}}/{{seq}}"
        obs, t = common(name, prop, src, "met:AccumulatedObservation", tnode)
        cols = "sigla, tmin, t_utc, local_date, value, seq, multi, src_row"
    else:
        tnode = f":time/{name}/{{sigla}}/{{tmin}}/{{seq}}"
        obs, t = common(name, prop, src, "met:InstantaneousObservation", tnode)
        cols = "sigla, tmin, t_utc, local_date, value, seq, multi, src_row" + (", runway" if name in WIND else "")
    if not accum:
        t += f"{tnode} a time:Instant ; time:inXSDDateTime {{t_utc}}^^xsd:dateTime . "
    t += (f":result/{name}/{{sigla}}/{{tmin}}/{{seq}} a qudt:QuantityValue ; "
          f"qudt:numericValue {{value}}^^{xsd} ; qudt:unit {unit} .")
    out.append((f"obs_{name}", t, f"SELECT {cols} FROM obs_{name}"))
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
    for spec in INSTANT:
        m += scalar(*spec)
    for spec in ACCUM:
        m += scalar(*spec, accum=True)
    obs, t = common("cloud", "met:CloudCover", "nuvem.csv", "met:CloudLayerObservation", ":time/cloud/{sigla}/{tmin}/{seq}")
    t = t.replace(" met:multipleReadings {multi}^^xsd:boolean ;", "")
    t += (":time/cloud/{sigla}/{tmin}/{seq} a time:Instant ; time:inXSDDateTime {t_utc}^^xsd:dateTime . "
          ":result/cloud/{sigla}/{tmin}/{seq} a met:CloudLayerResult ; met:skyObscured {sky_obscured}^^xsd:boolean .")
    m.append(("obs_cloud", t, "SELECT sigla, tmin, t_utc, local_date, seq, src_row, sky_obscured FROM obs_cloud_layer"))
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
