"""
Parser Python pour la découverte codebase.
Utilise ast.parse pour extraire les fonctions et méthodes publiques.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from mcp_forge.models import DiscoveredTool, ParameterType, ToolParameter

_ANNOTATION_MAP: dict[str, ParameterType] = {
    "str": ParameterType.STRING,
    "int": ParameterType.INTEGER,
    "float": ParameterType.NUMBER,
    "bool": ParameterType.BOOLEAN,
    "list": ParameterType.ARRAY,
    "List": ParameterType.ARRAY,
    "dict": ParameterType.OBJECT,
    "Dict": ParameterType.OBJECT,
    "Any": ParameterType.OBJECT,
    "bytes": ParameterType.STRING,
    "Path": ParameterType.STRING,
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class PythonParser:
    """Extrait les fonctions publiques de fichiers Python via AST."""

    def extract(self, path: Path, root: Path) -> list[DiscoveredTool]:
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            return []

        tools: list[DiscoveredTool] = []
        relative_path = str(path.relative_to(root))

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if not node.name.startswith("_"):
                    tool = self._func_to_tool(node, relative_path, prefix="")
                    if tool:
                        tools.append(tool)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    for item in ast.iter_child_nodes(node):
                        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                            if not item.name.startswith("_"):
                                tool = self._func_to_tool(item, relative_path, prefix=node.name)
                                if tool:
                                    tools.append(tool)
        return tools

    def _func_to_tool(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
        prefix: str,
    ) -> DiscoveredTool | None:
        func_name = node.name
        raw_name = f"{prefix.lower()}_{func_name}" if prefix else func_name
        name = _SLUG_RE.sub("_", raw_name.lower()).strip("_")

        docstring = ast.get_docstring(node) or ""
        description = _first_line(docstring) or f"{prefix + '.' if prefix else ''}{func_name}"
        parameters = self._extract_parameters(node, docstring)
        response_description = self._describe_return(node)

        return DiscoveredTool(
            name=name,
            description=description,
            parameters=parameters,
            response_description=response_description,
            tags=["codebase", file_path],
            metadata={
                "file": file_path,
                "function": func_name,
                "class": prefix or None,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "language": "python",
            },
        )

    def _describe_return(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Décrit la valeur de retour à partir de l'annotation Python de la
        fonction — remplace le fallback générique "Résultat de la
        fonction." (signalé comme mineur mais récurrent dans les rapports
        d'éval : sans ça, l'appelant MCP ne sait pas quel type attendre)."""
        ann = node.returns
        type_name = None
        if isinstance(ann, ast.Name):
            type_name = ann.id
        elif isinstance(ann, ast.Constant):
            type_name = str(ann.value)
        elif isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name):
            type_name = ann.value.id
        if not type_name or type_name == "None":
            return ""
        return f"Résultat de type {type_name} (converti en chaîne)."

    def _extract_parameters(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        docstring: str,
    ) -> list[ToolParameter]:
        params: list[ToolParameter] = []
        args = node.args
        all_args = args.args + args.kwonlyargs
        defaults_offset = len(args.args) - len(args.defaults)
        kw_defaults = {
            args.kwonlyargs[i].arg: args.kw_defaults[i]
            for i in range(len(args.kwonlyargs))
            if i < len(args.kw_defaults) and args.kw_defaults[i] is not None
        }
        doc_params = _parse_docstring_params(docstring)

        for i, arg in enumerate(all_args):
            if arg.arg in ("self", "cls"):
                continue

            ptype = ParameterType.STRING
            items_type = None
            if arg.annotation:
                ptype, items_type = self._annotation_to_type(arg.annotation)

            default = None
            required = True
            if arg in args.args:
                default_idx = i - defaults_offset
                if 0 <= default_idx < len(args.defaults):
                    default = _ast_const(args.defaults[default_idx])
                    required = False
            elif arg.arg in kw_defaults:
                default = _ast_const(kw_defaults[arg.arg])
                required = False

            params.append(ToolParameter(
                name=arg.arg,
                type=ptype,
                items_type=items_type,
                description=doc_params.get(arg.arg, ""),
                required=required,
                default=default,
            ))

        if args.vararg:
            params.append(ToolParameter(
                name=args.vararg.arg,
                type=ParameterType.ARRAY,
                description=doc_params.get(args.vararg.arg, "Arguments supplémentaires"),
                required=False,
            ))

        return params

    def _annotation_to_type(self, annotation: ast.expr) -> tuple[ParameterType, ParameterType | None]:
        """Retourne (type, items_type). `items_type` n'est renseigné que
        pour `list[X]`/`List[X]` quand X est un type simple connu — permet
        au générateur de produire `list[float]` plutôt qu'un `list` nu."""
        if isinstance(annotation, ast.Name):
            return _ANNOTATION_MAP.get(annotation.id, ParameterType.STRING), None
        if isinstance(annotation, ast.Constant):
            return _ANNOTATION_MAP.get(str(annotation.value), ParameterType.STRING), None
        if isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name):
            name = annotation.value.id
            if name in ("List", "list", "Sequence"):
                items_type = None
                if isinstance(annotation.slice, ast.Name):
                    items_type = _ANNOTATION_MAP.get(annotation.slice.id)
                return ParameterType.ARRAY, items_type
            if name in ("Dict", "dict", "Mapping"):
                return ParameterType.OBJECT, None
            if name in ("Optional", "Union"):
                if isinstance(annotation.slice, ast.Name):
                    return _ANNOTATION_MAP.get(annotation.slice.id, ParameterType.STRING), None
        return ParameterType.STRING, None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _ast_const(node: ast.expr | None) -> str | int | float | bool | None:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        if isinstance(node.operand, ast.Constant):
            return -node.operand.value
    return None


def _parse_docstring_params(docstring: str) -> dict[str, str]:
    params: dict[str, str] = {}
    if not docstring:
        return params
    for m in re.finditer(r"^\s{4,8}(\w+)\s*\(.*?\)\s*:\s*(.+)$", docstring, re.MULTILINE):
        params[m.group(1)] = m.group(2).strip()
    for m in re.finditer(r":param\s+(\w+):\s*(.+)", docstring):
        params[m.group(1)] = m.group(2).strip()
    for m in re.finditer(r"^\s{4,8}(\w+):\s+(.+)$", docstring, re.MULTILINE):
        if m.group(1) not in params:
            params[m.group(1)] = m.group(2).strip()
    return params
