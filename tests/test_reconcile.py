"""Conciliação v8 (pipeline/reconcile.py): o LLM decide o sentido e cita trechos; tempo, limiares e unidades vêm da leitura determinística.

Cada caso reproduz um erro MEDIDO no conjunto novo_a (docs/julgamento_novo_a_veredictos.yaml) com a interpretação que um LLM plausivelmente
devolveria no formato v8. O erro tem de ser impossível por construção (tempo) ou pego pelo mecanismo genérico (unidade, número sem dono,
alcance), nunca por uma regra escrita para aquela frase.
"""
from datetime import date

from pipeline.compiler import compile_structured
from pipeline.reconcile import reconcile
from pipeline.validators import validate_interpretation, validate_query
from pipeline.vocab import STATION_NS, OntologyIndex
from tests.test_structured import ROOT

IDX = OntologyIndex.load().with_profile_from_obda(ROOT / "mapping" / "met.obda")
IDX.entities = {STATION_NS + s: [s] for s in ("SBGL", "SBGO", "SBPV", "SBFZ", "SBCG", "SBNT", "SBCY", "SBSP", "SBBR", "SBVT", "SBNF", "SBSV", "SBBE")}
IDX.properties_with_data = set(IDX.properties)
IDX.coverage = (date(2016, 1, 1), date(2025, 12, 31))


def ir(prop, prop_span, station=None, agg=None, agg_span=None, **kw):
    out = {"status": "ok", "properties": [{"iri": prop, "span": prop_span}],
           "entities": [{"iri": f"st:{station.upper()}", "span": station}] if station else [],
           "aggregation": {"value": agg, "span": agg_span} if agg else None, "record_kind": "observation"}
    return {**out, **kw}


def codes(rec):
    return {f.diag.code for f in rec.findings}


def compiles(rec):
    """A interpretação conciliada passa nas regras de esquema/forma, é montada pelo compilador e a consulta passa nas regras de consulta."""
    assert not validate_interpretation(rec.interp, IDX, None, (), True)
    q = compile_structured(rec.interp, IDX, force=True)
    assert q, "o compilador não montou"
    assert not validate_query(q, rec.interp, IDX, True)[1]
    return q


# ---------------- dia vira mês (E07, E11, E43): impossível por construção, o período não vem do LLM ----------------

def test_dia_por_extenso_e_o_dia_nao_o_mes():
    for q, day, station, prop, agg, span in [
        ("Qual foi a visibilidade mínima, em metros, em SBGL no dia 15 de fevereiro de 2024?", "2024-02-15", "SBGL", "met:PrevailingVisibility", "min", "mínima"),
        ("Qual foi a temperatura máxima do ar em SBGO em 14 de outubro de 2019?", "2019-10-14", "SBGO", "met:AirTemperature", "max", "máxima"),
        ("qual a temperatua maxima em sbpv no dia 13 de março de 2021?", "2021-03-13", "SBPV", "met:AirTemperature", "max", "maxima"),
    ]:
        rec = reconcile(ir(prop, _prop_span(q), station.lower() if q.islower() else station, agg, span), q, IDX)
        assert not rec.findings and rec.clarify is None, (q, codes(rec), rec.clarify)
        assert rec.interp.period == {"start": day, "end": day, "tz": "-03:00", "inclusive_end": True}
        assert f'"{day}"^^xsd:date && ?d <= "{day}"^^xsd:date' in compiles(rec)


def _prop_span(q):
    from pipeline.vocab import fold
    f = fold(q)
    return next(w for w in ("visibilidade", "temperatua", "temperatura") if w in f)


# ---------------- grandeza errada pela unidade (E05, E44) ----------------

def test_minutos_de_chuva_nao_e_precipitacao_em_mm_E05():
    q = "Quantos minutos de chuva, somando todas as horas, foram registrados em SBFZ em 2020?"
    rec = reconcile(ir("met:Precipitation", "chuva", "SBFZ", "sum", "somando"), q, IDX)
    assert "UNIT_PROPERTY_MISMATCH" in codes(rec)
    ok = reconcile(ir("met:PrecipitationDuration", "minutos de chuva", "SBFZ", "sum", "somando"), q, IDX)
    assert not ok.findings and ok.interp.period["start"] == "2020-01-01"
    compiles(ok)


def test_quantos_mm_pede_soma_nao_contagem_E44():
    q = "sbcg, quantos mm choveu em janeiro de 2024?"
    assert "MEASURE_NOT_COUNT" in codes(reconcile(ir("met:Precipitation", "choveu", "sbcg", "count", "quantos"), q, IDX))
    ok = reconcile(ir("met:Precipitation", "choveu", "sbcg", "sum", "quantos mm"), q, IDX)
    assert not ok.findings
    assert "SUM(?v)" in compiles(ok)


# ---------------- restrição descartada em silêncio (E15, E50) ----------------

def test_horas_com_chuva_viram_condicao_e_contam_horas_distintas_E15():
    q = "Quantas horas com chuva houve em SBCY em 2022?"
    rec = reconcile(ir("met:Precipitation", "chuva", "SBCY", "count", "Quantas horas"), q, IDX)
    assert not rec.findings
    assert rec.interp.filters == [{"op": ">", "value": 0.0}] and rec.interp.count_of == "hours"
    sparql = compiles(rec)
    assert "FILTER(?v > 0)" in sparql and "COUNT(DISTINCT ?hour)" in sparql and "?obs met:localHour ?h ." in sparql
    assert any("horas distintas" in n for n in rec.notes)


def test_fins_de_semana_entram_na_consulta_E50():
    q = "Qual a velocidade média do vento em SBNT nos fins de semana de 2024?"
    rec = reconcile(ir("met:WindSpeed", "velocidade média do vento", "SBNT", "avg", "média"), q, IDX)
    assert not rec.findings and rec.interp.weekdays == [5, 6]
    sparql = compiles(rec)
    assert "?obs met:localWeekday ?wd ." in sparql and "FILTER(?wd IN (5, 6))" in sparql     # sábado e domingo, dia da semana local


def test_madrugada_vira_horas_locais():
    q = "Quanto choveu em SBBE de madrugada em 2019?"
    rec = reconcile(ir("met:Precipitation", "choveu", "SBBE", "sum", "Quanto choveu"), q, IDX)
    assert not rec.findings and rec.interp.hours == (0, 6)
    assert "FILTER(?h IN (0, 1, 2, 3, 4, 5))" in compiles(rec)                          # hora local, sem conversão na consulta


def test_limiar_sem_dono_e_pego():
    q = "Em quantas horas a visibilidade em SBSP ficou abaixo de 1000 metros em 2018?"
    dropped = reconcile(ir("met:PrevailingVisibility", "visibilidade", "SBSP", "count", "Em quantas horas"), q, IDX)
    assert "NUMBER_UNUSED" in codes(dropped)
    ok = reconcile(ir("met:PrevailingVisibility", "visibilidade", "SBSP", "count", "Em quantas horas",
                      filters=[{"op": "<", "span": "abaixo de 1000 metros"}]), q, IDX)
    assert not ok.findings and ok.interp.filters == [{"op": "<", "value": 1000.0, "unit": "unit:M"}] and ok.interp.count_of == "hours"
    compiles(ok)


def test_o_valor_do_filtro_vem_do_trecho_nao_do_llm():
    q = "Quantas vezes o vento passou de 15 nós em SBNF em 2017?"
    rec = reconcile(ir("met:WindSpeed", "vento", "SBNF", "count", "Quantas vezes", filters=[{"op": ">", "span": "passou de 15 nós"}]), q, IDX)
    assert rec.interp.filters == [{"op": ">", "value": 15.0, "unit": "unit:KN"}] and rec.interp.count_of == "readings"


# ---------------- trechos ----------------

def test_trecho_inventado_ou_estacao_trocada_volta_para_reparo():
    q = "Qual foi a temperatura média em SBGL em 2020?"
    assert "SPAN_NOT_IN_QUESTION" in codes(reconcile(ir("met:AirTemperature", "calor", "SBGL", "avg", "média"), q, IDX))
    swapped = reconcile({**ir("met:AirTemperature", "temperatura", None, "avg", "média"),
                         "entities": [{"iri": "st:SBGO", "span": "SBGL"}]}, q, IDX)
    assert {"ENTITY_SPAN_MISMATCH", "ENTITY_OMITTED"} <= codes(swapped)


# ---------------- alcance mínimo: esclarecer em vez de chutar (E41, E42) ----------------

def test_sem_estacao_nem_periodo_pede_esclarecimento_E41():
    rec = reconcile(ir("met:WindSpeed", "vento", None, "avg", "média"), "Qual foi a média de vento?", IDX)
    assert rec.clarify and not rec.findings
    whole = reconcile(ir("met:Precipitation", "chuva", None, "max", "maior"), "Qual foi a maior chuva já registrada na rede?", IDX)
    assert whole.clarify is None


def test_sem_calculo_pede_esclarecimento_E42():
    rec = reconcile(ir("met:AirTemperature", "temperatura", "SBSV", None, None), "Qual foi a temperatura em SBSV em 2020?", IDX)
    assert rec.clarify and "cálculo" in rec.clarify


def test_mes_sem_ano_e_periodo_vago_pedem_esclarecimento():
    assert "ano" in reconcile(ir("met:RelativeHumidity", "umidade relativa", None, "avg", "média"),
                              "Me passa a média da umidade relativa de julho.", IDX).clarify
    assert "semana" in reconcile(ir("met:AirTemperature", "temperatura", "SBGL", "avg", "média"),
                                 "Qual foi a temperatura média de SBGL em toda a semana?", IDX).clarify


def test_dois_periodos_sao_ditos_nao_suportados():
    rec = reconcile(ir("met:AirTemperature", "quente", "SBSP", "avg", "mais quente"), "SBSP esteve mais quente em janeiro de 2016 ou em janeiro de 2025?", IDX)
    assert rec.unsupported and rec.interp.period is None
