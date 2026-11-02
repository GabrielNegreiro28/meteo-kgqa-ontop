"""Arquitetura final (plano, D6 e D11): um só caminho de execução, sem o legado, e um só lugar que define grandezas, unidades e faixas."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPORT = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.M)


def _imports(path: Path) -> set[str]:
    return {m.split(".")[0] for m in IMPORT.findall(path.read_text(encoding="utf-8"))}


def test_o_legado_saiu_da_arvore():
    assert not list((ROOT / "pipeline").glob("*.py")) and not list((ROOT / "kgqa").glob("*.py"))


def test_metqa_nao_depende_do_legado_e_so_as_portas_tocam_a_evolucao():
    ports = {ROOT / "metqa" / "knowledge" / "lexicon.py", ROOT / "metqa" / "evolution" / "__init__.py"}
    for f in (ROOT / "metqa").rglob("*.py"):
        used = _imports(f)
        assert not used & {"pipeline", "kgqa"}, f
        assert "semantics" not in used or f in ports, f"{f}: só o léxico e a evolução falam com o EvoOntology"


def test_uma_so_tabela_de_unidades_e_faixas():
    """Nenhum código fora do catálogo (ontology/catalog.py, lido da ontologia) mantém tabela de unidade, fator ou faixa física."""
    unit_table = re.compile(r'["\'](DEG_C|HectoPA|MilliM|KiloM|OKTA|PERCENT|KN)["\']\s*:')
    literal_range = re.compile(r"BETWEEN\s+-?\d+\s+AND\s+\d+")
    for f in [*ROOT.glob("metqa/**/*.py"), *ROOT.glob("ingest/*.py"), *ROOT.glob("mapping/*.py"), *ROOT.glob("semantics/*.py")]:
        text = f.read_text(encoding="utf-8")
        assert not unit_table.search(text), f"{f}: tabela de unidades fora do catálogo"
        assert not re.search(r"^(UNIT_FACTORS|UNIT_DIMENSION|EXTRA_SYMBOLS)\s*=", text, re.M), f
        assert not literal_range.search(text), f"{f}: faixa física escrita à mão"


def test_artefatos_gerados_do_catalogo_estao_em_dia():
    from ontology.catalog import render_shapes
    assert (ROOT / "ontology" / "shapes.ttl").read_text(encoding="utf-8") == render_shapes(), "rode python -m ontology.catalog"
    out = subprocess.run([sys.executable, str(ROOT / "mapping" / "build_mapping.py")], capture_output=True, text=True, encoding="utf-8",
                         check=True).stdout
    assert out.strip() == (ROOT / "mapping" / "met.obda").read_text(encoding="utf-8").strip(), "rode python mapping/build_mapping.py"


def test_toda_grandeza_com_tabela_tem_unidade_e_faixa():
    from ontology.catalog import quantities, units
    for q in quantities().values():
        if q.observed_as == "CloudLayerObservation":
            continue                                                      # nebulosidade: categórica, sem valor numérico
        assert q.unit in units() and q.low is not None and q.high is not None and q.low < q.high, q.name
