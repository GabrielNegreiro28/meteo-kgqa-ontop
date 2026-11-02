"""Execução: fonte SPARQL (porta), executor com política e checagem prévia pelo motor, e o adaptador do Ontop (`store.py`).

Os nomes de `source.py` são carregados sob demanda: as regras de consulta importam o executor (política e prefixos) e o executor importa as
regras; carregar tudo no import do pacote fecharia o ciclo."""
__all__ = ["SparqlSource", "execute", "rows"]


def __getattr__(name):
    if name in __all__:
        from . import source
        return getattr(source, name)
    raise AttributeError(name)
