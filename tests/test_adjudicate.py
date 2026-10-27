from eval.adjudicate import classify, robust_match, signature


def test_rotulo_de_periodo_em_qualquer_formato_e_ordem_livre():
    oracle = [[1, 27.22], [2, 24.75]]
    assert robust_match([["2019-02", 24.749, 737.0], ["2019-01", 27.217, 789.0]], oracle)
    assert robust_match([[2.0, 24.749], [1.0, 27.217]], oracle)
    assert not robust_match([["2019-02", 24.749]], oracle)          # falta uma linha da referência
    assert not robust_match([[1, 27.22], [2, 30.0]], oracle)         # valor diferente


def _row(i, status, rows, oracle=(), exp="answerable", ok=True, diag=()):
    return {"id": i, "expected_behavior": exp, "status": status, "pipeline_rows": [list(r) for r in rows], "oracle_rows": [list(r) for r in oracle],
            "status_ok": ok, "diagnostics": list(diag)}


def test_diferenca_de_limpeza_so_vale_com_consenso_e_o_que_nao_rodou_sai_do_placar():
    ref = [(7.0,)]
    a = {"E1": _row("E1", "answered", [(14.0,)], ref), "E2": _row("E2", "answered", [(5.0,)], ref), "E3": _row("E3", "execution_error", [], ref, diag=["BUDGET_EXCEEDED"])}
    b = {"E1": _row("E1", "answered", [(14.0,)], ref), "E2": _row("E2", "answered", [(6.0,)], ref), "E3": _row("E3", "answered", [(7.0,)], ref)}
    res = classify({"a": a, "b": b}, {"E1": {"verdict": "cleaning_difference"}, "E2": {"verdict": "cleaning_difference"}})
    assert set(res["a"]) == {"E1", "E2"}                              # E3 não rodou em `a`: fora para todos
    assert res["a"]["E1"] == "correto" and res["b"]["E1"] == "correto"  # mesmo valor nas duas: diferença de limpeza
    assert res["a"]["E2"] == "errado"                                 # valores diferentes entre si: não é o conjunto de regras
    assert signature([[1.04, 2]]) == signature([[1.0, 2]])
