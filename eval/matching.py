"""Strict reference comparison. Columns must be aligned explicitly by the caller.
Historical unlabeled results are never guessed into the reference schema.
"""
from decimal import Decimal


def cell_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, (int, float, Decimal)) and isinstance(b, (int, float, Decimal)):
        x, y = Decimal(str(a)), Decimal(str(b))
        return x.is_finite() and y.is_finite() and abs(x-y) <= max(Decimal("0.01"), Decimal("0.001") * max(abs(x), abs(y)))
    return type(a) is type(b) and a == b


def match_rows(actual, expected):
    if expected is None:
        raise ValueError("missing reference is not an empty reference")
    if len(actual) != len(expected):
        return False
    # Bipartite matching preserves multiplicity even with overlapping tolerances.
    edges = [[j for j,b in enumerate(actual) if len(a)==len(b) and all(cell_equal(x,y) for x,y in zip(a,b))] for a in expected]
    matched = {}
    def visit(i, seen):
        for j in edges[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in matched or visit(matched[j], seen):
                matched[j] = i
                return True
        return False
    return all(visit(i, set()) for i in range(len(expected)))
