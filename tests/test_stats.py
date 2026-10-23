"""eval/stats.py: o módulo que diz quanto uma diferença de placar vale não pode errar em silêncio. Valores conferidos à mão."""
import pytest

from eval.stats import compare, harmful, mcnemar_exact, succeeded, wilson


@pytest.mark.parametrize("k,n,lo,hi", [(0, 10, 0.0, 0.2775), (5, 10, 0.2366, 0.7634), (10, 10, 0.7225, 1.0), (22, 24, 0.7415, 0.9769)])
def test_wilson_matches_known_values(k, n, lo, hi):
    got = wilson(k, n)
    assert got[0] == pytest.approx(lo, abs=1e-3) and got[1] == pytest.approx(hi, abs=1e-3)


def test_wilson_stays_inside_zero_and_one_and_handles_empty():
    for k, n in [(0, 1), (1, 1), (3, 3), (0, 50)]:
        lo, hi = wilson(k, n)
        assert 0.0 <= lo <= hi <= 1.0
    assert wilson(0, 0) == (0.0, 1.0)


@pytest.mark.parametrize("a,b,p", [(0, 0, 1.0), (3, 3, 1.0), (6, 0, 0.03125), (5, 1, 0.21875), (4, 0, 0.125), (0, 5, 0.0625)])
def test_mcnemar_exact_matches_the_binomial(a, b, p):
    assert mcnemar_exact(a, b) == pytest.approx(p)
    assert mcnemar_exact(a, b) == pytest.approx(mcnemar_exact(b, a))             # bilateral: não depende da ordem


def row(status="answered", expected="answered", ok=True, match=True):
    return {"status": status, "expected_status": expected, "status_ok": ok, "result_match": match}


def test_success_requires_the_right_status_and_no_wrong_value():
    assert succeeded(row())
    assert not succeeded(row(match=False))                       # status certo, número errado
    assert not succeeded(row(status="unsupported", ok=False, match=None))
    assert succeeded(row(status="unsupported", expected="unsupported", match=None))


def test_harm_is_only_what_the_user_cannot_notice():
    assert harmful(row(match=False))                                                         # número errado entregue
    assert harmful(row(status="no_results", ok=False, match=False))                         # 'sem registros' onde há dados
    assert harmful(row(status="answered", expected="unsupported", ok=False, match=None))    # respondeu o que devia recusar
    assert not harmful(row(status="unsupported", ok=False, match=None))                     # abstenção indevida: perda de utilidade, não dano
    assert not harmful(row(status="no_results", expected="no_results", match=None))


def test_the_report_calls_a_tiny_difference_noise():
    a = {f"q{i}": row() for i in range(10)}
    b = {f"q{i}": row(match=(i != 0)) for i in range(10)}                                    # b erra uma
    text = compare({"a": a, "b": b})
    assert "p = 1.00" in text and "ruído" in text


def test_compare_refuses_runs_with_different_questions_instead_of_dropping_some_silently():
    """Codex C15: v6 em dois arquivos (RG24 rodada à parte) comparado com o v4 de 24 perguntas deixava a 24ª de fora sem dizer."""
    a = {f"Q{i}": row() for i in range(1, 25)}
    b = {f"Q{i}": row() for i in range(1, 24)}
    with pytest.raises(ValueError, match="Q24"):
        compare({"v4": a, "v6": b})
    text = compare({"v4": a, "v6": b}, allow_partial=True)
    assert "excluídas" in text and "Q24" in text and "Perguntas em comum: 23" in text


def test_load_joins_the_files_of_one_condition_and_rejects_duplicates(tmp_path):
    import json
    from eval.stats import load
    (tmp_path / "a.json").write_text(json.dumps([{"id": "Q1"}, {"id": "Q2"}]), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps([{"id": "Q3"}]), encoding="utf-8")
    (tmp_path / "c.json").write_text(json.dumps([{"id": "Q2"}]), encoding="utf-8")
    assert set(load(f"{tmp_path / 'a.json'},{tmp_path / 'b.json'}")) == {"Q1", "Q2", "Q3"}
    with pytest.raises(ValueError, match="Q2"):
        load(f"{tmp_path / 'a.json'},{tmp_path / 'c.json'}")
