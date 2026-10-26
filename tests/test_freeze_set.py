import pytest
import yaml

from eval import freeze_set as fs


def _q(i, text, b="answerable"):
    return {"id": i, "question": text, "expected_behavior": b}


def test_congela_e_verifica(tmp_path):
    src = tmp_path / "n.yaml"
    src.write_text(yaml.safe_dump({"questions": [_q("N01", "Quanto choveu em SBGL em 2019?")]}, allow_unicode=True), encoding="utf-8")
    out = fs.freeze(src, "a", "teste", root=tmp_path)
    assert (out / "manifest.json").exists()
    assert fs.verify("a", root=tmp_path)
    (out / "questions.yaml").write_text("questions: []\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        fs.verify("a", root=tmp_path)
    with pytest.raises(SystemExit):                      # não sobrescreve
        fs.freeze(src, "a", "teste", root=tmp_path)


def test_recusa_pergunta_ja_vista_id_repetido_e_comportamento_invalido():
    seen = {fs._norm("Qual a temperatura média em SBGL?")}
    errs = fs.check([_q("A", "qual a TEMPERATURA média em SBGL"), _q("A", "outra"), _q("B", "x", "talvez")], seen)
    assert any("já vista" in e for e in errs) and any("repetido" in e for e in errs) and any("fora de" in e for e in errs)


def test_perguntas_reais_ja_existentes_sao_lidas():
    assert len(fs.seen_questions()) > 100
