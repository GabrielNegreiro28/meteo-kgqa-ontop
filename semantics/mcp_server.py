"""Servidor MCP (stdio) da camada semântica: o do EvoOntology, com `resolve_semantics` e `browse_semantics` ligados à
ontologia formal. As demais operações (versões, execuções de evolução) continuam sendo as do núcleo.

    python -m semantics.mcp_server --store .evoontology
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evoontology.runtime.mcp_server import SemanticMCPServer, force_utf8_stdio
from evoontology.workspace import resolve_workspace

from .facade import GroundedLayer

SEMANTIC_TOOLS = {"browse_semantics", "resolve_semantics"}


class GroundedMCPServer(SemanticMCPServer):
    def __init__(self, store_path: str, version: str = ""):
        super().__init__(store_path, version)
        self.layer = GroundedLayer.open(store_path, version or None)

    def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "tools/call" and str(params.get("name", "")) in SEMANTIC_TOOLS:
            args = dict(params.get("arguments") or {})
            args.pop("workspace", None)               # este servidor serve UM workspace; o chamador não escolhe o caminho
            version = str(args.pop("version", "") or "") or self.version or None
            try:
                self.layer = GroundedLayer.open(self.store_path, version)
                result, is_error = self.layer.execute(str(params["name"]), args), False
            except Exception as exc:
                result, is_error = {"status": "error", "message": str(exc)}, True
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}],
                    "isError": is_error}
        if method == "resources/read":
            self.layer = GroundedLayer.open(self.store_path, self.version or None)
            return {"contents": [{"uri": "evo-semantic://session-manifest", "mimeType": "text/plain",
                                  "text": self.layer.manifest()}]}
        return super().dispatch(method, params)


def main() -> None:
    force_utf8_stdio()
    parser = argparse.ArgumentParser(description="Servidor MCP da camada semântica meteorológica")
    parser.add_argument("--store", default=None, help="workspace (padrão: <cwd>/.evoontology)")
    parser.add_argument("--version", default="", help="versão explícita (padrão: a ativa)")
    args = parser.parse_args()
    GroundedMCPServer(str(resolve_workspace(args.store)), version=args.version).run()


if __name__ == "__main__":
    main()
