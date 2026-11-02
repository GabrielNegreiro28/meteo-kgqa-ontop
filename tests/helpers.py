"""Perfis compartilhados pelos testes, sem Ontop: o índice com o perfil do grafo REAL (lido do mapeamento), estações e cobertura fixas."""
from datetime import date
from pathlib import Path

from metqa.knowledge.index import STATION_NS, OntologyIndex

ROOT = Path(__file__).resolve().parent.parent
IDX = OntologyIndex.load().with_profile_from_obda(ROOT / "mapping" / "met.obda")
IDX.entities = {STATION_NS + s: [s] for s in ("SBGL", "SBGO", "SBPV", "SBFZ", "SBCG", "SBNT", "SBCY", "SBSP", "SBBR", "SBVT", "SBNF", "SBSV", "SBBE")}
IDX.properties_with_data = set(IDX.properties)
IDX.coverage = (date(2016, 1, 1), date(2025, 12, 31))
