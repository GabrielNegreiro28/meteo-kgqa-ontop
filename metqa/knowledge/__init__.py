"""Conhecimento do domínio: o índice da ontologia (`index.py`), o Catálogo de Domínio, o léxico (EvoOntology ou rótulos formais) e a
memória de exemplos verificados. Nomes carregados sob demanda: o índice é usado pelas regras de consulta, que o catálogo também usa."""
_WHERE = {"DomainCatalog": "catalog", "Measure": "catalog", "ExemplarStore": "exemplars", "EvoLexicon": "lexicon", "Lexicon": "lexicon",
          "LexiconHit": "lexicon", "OntologyLexicon": "lexicon"}
__all__ = list(_WHERE)


def __getattr__(name):
    if name in _WHERE:
        from importlib import import_module
        return getattr(import_module(f".{_WHERE[name]}", __name__), name)
    raise AttributeError(name)
