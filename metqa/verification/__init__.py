"""Verificação: antes (mundo fechado) e depois (resultado guiado pelo ResultShape), as regras de consulta e as ressalvas.

`verify_pre` e `verify_post` são carregados sob demanda: o catálogo usa as regras (dimensões e atributos), e o verificador usa o catálogo."""
__all__ = ["verify_post", "verify_pre"]


def __getattr__(name):
    if name == "verify_post":
        from .post import verify_post
        return verify_post
    if name == "verify_pre":
        from .pre import verify_pre
        return verify_pre
    raise AttributeError(name)
