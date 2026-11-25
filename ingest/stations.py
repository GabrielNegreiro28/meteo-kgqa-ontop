"""Cadastro das estações: nome, município, UF, região, coordenadas, altitude e fuso legal de cada sigla.

Fonte: OurAirports (https://ourairports.com/data/, domínio público), arquivo airports.csv. Os CSV de METEOROLOGIA não trazem cadastro;
ele vem de fora e entra como dado de referência, não como medição.
Uso: python -m ingest.stations <airports.csv> <siglas.txt> > data/estacoes.csv

Fuso legal (horário padrão, sem horário de verão) e zona IANA pela UF. Exceções: Fernando de Noronha (UTC−2, America/Noronha) e o oeste do
Amazonas, que segue o Acre (UTC−5, America/Eirunepe; a única estação ali é SBTT). Todos os fusos foram conferidos contra METAR em UTC em
data/verificar_fuso_metar.py (SBTT, SBFN, SBCZ, SBRB, SBEG, SBUA, SBPV, SBCY, SBCG, SBSN, SBBE, SBGR, SBPA).
"""
from __future__ import annotations

import csv
import sys

REGIAO = {**dict.fromkeys(["AC", "AM", "AP", "PA", "RO", "RR", "TO"], "Norte"),
          **dict.fromkeys(["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"], "Nordeste"),
          **dict.fromkeys(["DF", "GO", "MS", "MT"], "Centro-Oeste"),
          **dict.fromkeys(["ES", "MG", "RJ", "SP"], "Sudeste"),
          **dict.fromkeys(["PR", "RS", "SC"], "Sul")}
UF_NOME = {"AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
           "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul", "MT": "Mato Grosso",
           "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco", "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
           "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
           "TO": "Tocantins"}
UTC4 = {"AM", "MS", "MT", "RO", "RR"}
ZONA = {"AC": "America/Rio_Branco", "AM": "America/Manaus", "RR": "America/Boa_Vista", "RO": "America/Porto_Velho", "MT": "America/Cuiaba",
        "MS": "America/Campo_Grande", "PA": "America/Belem", "AP": "America/Belem", "TO": "America/Araguaina", "MA": "America/Fortaleza",
        "PI": "America/Fortaleza", "CE": "America/Fortaleza", "RN": "America/Fortaleza", "PB": "America/Fortaleza", "PE": "America/Recife",
        "AL": "America/Maceio", "SE": "America/Maceio", "BA": "America/Bahia",
        **dict.fromkeys(["DF", "GO", "MG", "ES", "RJ", "SP", "PR", "SC", "RS"], "America/Sao_Paulo")}
# siglas sem cadastro: variantes de SBMI (Maricá, RJ), SDAM (Campinas, SP) e SIMK (Franca, SP); XXXX é desconhecida. Fuso assumido: UTC−3.
SEM_CADASTRO = {"fuso_legal": -3, "fuso_iana": "America/Sao_Paulo"}
# horário de verão vigente até fev/2019 (Decreto 9.242/2017 e anteriores)
HORARIO_VERAO = {"DF", "ES", "GO", "MG", "MS", "MT", "PR", "RJ", "RS", "SC", "SP"}
# A fonte registra a cidade ATENDIDA; aqui vale o município onde o aeroporto está (conferido à mão).
MUNICIPIO = {"SBGR": "Guarulhos", "SBCF": "Confins", "SBCT": "São José dos Pinhais", "SBCY": "Várzea Grande", "SBSG": "São Gonçalo do Amarante",
             "SBCO": "Canoas", "SBNT": "Parnamirim", "SBIL": "Ilha Solteira", "SBEC": "Bacia de Campos (plataforma)",
             "SBLB": "Bacia de Campos (plataforma)", "SBMM": "Bacia de Campos (plataforma)"}
# Nomes pelos quais o aeroporto é conhecido (revisados à mão; o nome da fonte está em inglês). Separados por ";".
APELIDOS = {"SBGR": "Cumbica;Aeroporto de Guarulhos", "SBSP": "Congonhas", "SBMT": "Campo de Marte", "SBKP": "Viracopos",
            "SBGL": "Galeão;Tom Jobim", "SBRJ": "Santos Dumont", "SBJR": "Jacarepaguá", "SBAF": "Campo dos Afonsos;Afonsos",
            "SBSC": "Base Aérea de Santa Cruz", "SBCF": "Aeroporto de Confins", "SBBH": "Pampulha", "SBPR": "Carlos Prates",
            "SBCT": "Afonso Pena", "SBBI": "Bacacheri", "SBPA": "Salgado Filho", "SBBE": "Val de Cans", "SBJC": "Júlio César",
            "SBEG": "Eduardo Gomes", "SBMN": "Ponta Pelada", "SBRF": "Guararapes", "SBFZ": "Pinto Martins", "SBFL": "Hercílio Luz",
            "SBFI": "Cataratas", "SBMO": "Zumbi dos Palmares", "SBSV": "Aeroporto de Salvador", "SBBR": "Aeroporto de Brasília",
            "SBCO": "Base Aérea de Canoas", "SBNT": "Base Aérea de Natal", "SBST": "Base Aérea de Santos", "SBAN": "Base Aérea de Anápolis",
            "SBYS": "Academia da Força Aérea", "SBLS": "Base Aérea de Lagoa Santa", "SBTA": "Base de Aviação de Taubaté",
            "SBCC": "Cachimbo", "SBSG": "Aeroporto de São Gonçalo do Amarante", "SBQV": "Aeroporto antigo de Vitória da Conquista"}
# município que é também palavra comum: não serve para reconhecer a estação no texto (fica só no cadastro)
MUNICIPIO_AMBIGUO = {"Bonito", "Sorriso", "Cruz", "Una", "Bacia de Campos (plataforma)"}
CAMPOS = ["sigla", "nome", "municipio", "apelidos", "uf", "estado", "regiao", "lat", "lon", "altitude_m", "fuso_legal", "fuso_iana",
          "horario_verao_ate_2019", "fonte_id", "situacao"]


def fuso(uf: str, lon: float) -> tuple[int, str]:
    if uf == "PE" and lon > -33.5:
        return -2, "America/Noronha"
    if uf == "AC":
        return -5, ZONA[uf]
    if uf == "AM" and lon < -67.5:
        return -5, "America/Eirunepe"
    return (-4 if uf in UTC4 else -3), ZONA[uf]


def build(airports: str, siglas: list[str]) -> list[dict]:
    by_code: dict[str, dict] = {}
    with open(airports, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["iso_country"] != "BR":
                continue
            for k in ("ident", "icao_code", "gps_code"):
                if r[k]:
                    by_code.setdefault(r[k], r)
            for kw in r["keywords"].split(","):                    # aeroportos fechados guardam a sigla antiga nas palavras-chave
                kw = kw.strip()
                if len(kw) == 4 and kw.isupper() and kw.isalpha():
                    by_code.setdefault(kw, r)
    out = []
    for s in siglas:
        r = by_code.get(s)
        if r is None:
            out.append({"sigla": s, **SEM_CADASTRO, "situacao": "sem cadastro"})
            continue
        uf = r["iso_region"].split("-")[1]
        lon = float(r["longitude_deg"])
        tz, zona = fuso(uf, lon)
        out.append({"sigla": s, "nome": r["name"], "apelidos": APELIDOS.get(s, ""), "municipio": MUNICIPIO.get(s, r["municipality"].replace(" De ", " de ").replace(" Dos ", " dos ")), "uf": uf, "estado": UF_NOME[uf],
                    "regiao": REGIAO[uf], "lat": round(float(r["latitude_deg"]), 5), "lon": round(lon, 5),
                    "altitude_m": round(float(r["elevation_ft"]) * 0.3048) if r["elevation_ft"] else "",
                    "fuso_legal": tz, "fuso_iana": zona, "horario_verao_ate_2019": uf in HORARIO_VERAO, "fonte_id": r["ident"],
                    "situacao": "fechado na fonte" if r["type"] == "closed" else "ativo"})
    return out


def mentions(row: dict) -> list[tuple[str, str]]:
    """(nome, tipo) pelos quais a pergunta pode citar a estação: sigla e apelidos identificam UMA estação; município, estado e região
    podem cobrir várias, e a pipeline trata isso como ambiguidade (ver OntologyIndex.ambiguous_mentions)."""
    out = [(row["sigla"], "sigla")] + [(a, "apelido") for a in (row.get("apelidos") or "").split(";") if a]
    if row.get("municipio") and row["municipio"] not in MUNICIPIO_AMBIGUO:
        out.append((row["municipio"], "municipio"))
    if row.get("estado"):
        out += [(row["estado"], "estado"), (f"região {row['regiao']}", "regiao")]
    return out


def main() -> None:
    siglas = open(sys.argv[2], encoding="utf-8").read().split()
    w = csv.DictWriter(sys.stdout, CAMPOS, lineterminator="\n")
    w.writeheader()
    w.writerows(build(sys.argv[1], siglas))


if __name__ == "__main__":
    main()
