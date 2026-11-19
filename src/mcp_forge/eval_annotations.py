"""
Vérification mécanique des annotations MCP des tools (lot D, D1,
2026-10-30), à côté de l'évaluateur LLM (même rôle que eval_checks).

Un tool annoté readOnlyHint=True qui modifie des données trompe le client
(qui peut l'appeler sans confirmation) : c'est un bug « majeur », établi
ici sans LLM à partir du corps de la fonction :
  - appel HTTP d'écriture : .post/.put/.patch/.delete, ou .request("POST", …) ;
  - mutation GraphQL : chaîne qui commence par « mutation » ;
  - écriture sur disque : open(…, "w"/"a"/"x"/"+"), write_text, write_bytes,
    os.remove/unlink/rmdir/rename/replace, shutil.rmtree/move/copy….
Un tool qui supprime (DELETE HTTP, suppression de fichier) annoté
destructiveHint=False est aussi « majeur ». Des annotations absentes sont
« mineur » (critère docs) : elles aident le client, mais ne protègent rien.
Un tool dont le corps appelle du code qu'on ne voit pas (codebase) ne
produit aucun constat : seul ce qui est visible est jugé.
"""
from __future__ import annotations

import ast
import re

from mcp_forge.naming import comes_from, mcp_tool_name

_HTTP_WRITE = {"post", "put", "patch", "delete"}
_FILE_WRITE_ATTRS = {"write_text", "write_bytes", "unlink", "rmdir", "rmtree", "remove", "removedirs",
                     "rename", "renames", "move", "copy", "copy2", "copyfile", "copytree", "mkdir", "makedirs",
                     "truncate", "chmod", "chown", "touch"}
_FILE_WRITE_MODULES = {"os", "shutil", "pathlib", "Path"}
_DELETE_ATTRS = {"unlink", "rmdir", "rmtree", "remove", "removedirs"}
_MUTATION = re.compile(r"^\s*mutation\b")
_GRAPHQL_DOC = re.compile(r"^\s*(query|mutation|subscription)\b")


# Verbes de suppression (aussi utilisés par le générateur pour annoter un POST
# ou un PATCH qui supprime : POST /orders/{id}/cancel, operationId deleteUser).
DESTRUCTIVE_WORDS = re.compile(
    r"(^|_)(delete|remove|del|drop|destroy|purge|clear|reset|truncate|erase|wipe|revoke|"
    r"cancel|kill|uninstall|overwrite|replace|terminate|deactivate|discard)(_|$)")


def destructive_name(*names: str) -> bool:
    """Un des noms (chemin HTTP, operationId, nom de fonction) contient-il un
    verbe de suppression ? camelCase et séparateurs ramenés à « _ »."""
    for name in names:
        words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name or "")
        if DESTRUCTIVE_WORDS.search(re.sub(r"[^A-Za-z0-9]+", "_", words).lower()):
            return True
    return False


def _is_tool(node: ast.AST) -> ast.Call | ast.Attribute | None:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if (isinstance(target, ast.Attribute) and target.attr == "tool"
                and isinstance(target.value, ast.Name) and target.value.id == "mcp"):
            return dec
    return None


def _annotations(decorator: ast.AST) -> dict | None:
    """Annotations littérales du décorateur ({} si présentes mais illisibles,
    None si absentes)."""
    if not isinstance(decorator, ast.Call):
        return None
    for kw in decorator.keywords:
        if kw.arg != "annotations":
            continue
        value = kw.value
        if isinstance(value, ast.Call):
            pairs = {k.arg: k.value for k in value.keywords if k.arg}
        elif isinstance(value, ast.Dict):
            pairs = {k.value: v for k, v in zip(value.keys, value.values, strict=True) if isinstance(k, ast.Constant)}
        else:
            return {}
        return {k: v.value for k, v in pairs.items() if isinstance(v, ast.Constant)}
    return None


def _mcp_name(node: ast.FunctionDef, decorator: ast.AST) -> str:
    if isinstance(decorator, ast.Call):
        for kw in decorator.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                return str(kw.value.value)
    return node.name


def _effects(node: ast.FunctionDef, mcp_name: str = "") -> tuple[list[str], bool]:
    """(preuves d'écriture visibles, dont au moins une suppression ?) Un
    POST ou un PATCH compte comme suppression si un chemin de la fonction ou
    le nom MCP du tool contient un verbe de suppression."""
    evidence: list[str] = []
    deletes = False
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and _MUTATION.match(sub.value):
            evidence.append("GraphQL mutation")
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Attribute):
            owner = func.value.id if isinstance(func.value, ast.Name) else ""
            if func.attr in _HTTP_WRITE and owner not in _FILE_WRITE_MODULES:
                evidence.append(f"HTTP {func.attr.upper()}")
                deletes |= func.attr == "delete"
            elif (func.attr == "request" and sub.args and isinstance(sub.args[0], ast.Constant)
                  and str(sub.args[0].value).lower() in _HTTP_WRITE):
                evidence.append(f"HTTP {str(sub.args[0].value).upper()}")
                deletes |= str(sub.args[0].value).lower() == "delete"
            elif func.attr in _FILE_WRITE_ATTRS and (owner in _FILE_WRITE_MODULES or func.attr.startswith("write_")
                                                     or func.attr in ("unlink", "rmdir", "touch")):
                evidence.append(f"{owner + '.' if owner else ''}{func.attr}()")
                deletes |= func.attr in _DELETE_ATTRS
        elif isinstance(func, ast.Name) and func.id == "_fetch":
            # Sites web (D3) : _fetch(client, "POST", url, …)
            method = next((a.value for a in sub.args[:2] if isinstance(a, ast.Constant)
                           and str(a.value).lower() in _HTTP_WRITE), None)
            if method:
                evidence.append(f"HTTP {str(method).upper()}")
                deletes |= str(method).lower() == "delete"
        elif isinstance(func, ast.Name) and func.id == "open":
            mode = sub.args[1] if len(sub.args) > 1 else next((k.value for k in sub.keywords if k.arg == "mode"), None)
            if isinstance(mode, ast.Constant) and isinstance(mode.value, str) and set(mode.value) & set("wax+"):
                evidence.append(f"open(…, {mode.value!r})")
    if any(isinstance(sub, ast.Constant) and isinstance(sub.value, str) and _GRAPHQL_DOC.match(sub.value)
           for sub in ast.walk(node)):
        # GraphQL : tout passe par un POST de transport ; seule une mutation écrit.
        evidence = [e for e in evidence if not e.startswith("HTTP POST")]
    if not deletes and any(e in ("HTTP POST", "HTTP PATCH") for e in evidence):
        paths = [sub.value for sub in ast.walk(node)
                 if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and sub.value.startswith("/")]
        deletes = destructive_name(mcp_name, *paths)
    return sorted(set(evidence)), deletes


def annotation_bugs(code: str, source_names: list[str] | None = None) -> list[dict]:
    """Bugs établis mécaniquement sur les annotations des tools et, si les
    noms des opérations de la source sont connus, sur les noms MCP."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    bugs: list[dict] = []
    missing: list[str] = []
    foreign: list[str] = []
    known = {mcp_tool_name(n) for n in source_names or []}  # même règle que le générateur
    for node in tree.body:
        decorator = _is_tool(node)
        if decorator is None:
            continue
        name = _mcp_name(node, decorator)
        if known and not comes_from(name, known):
            foreign.append(name)
        annotations = _annotations(decorator)
        if annotations is None:
            missing.append(name)
            continue
        evidence, deletes = _effects(node, name)
        if annotations.get("readOnlyHint") is True and evidence:
            bugs.append(_bug(
                node, f"[annotations] tool {name} is annotated readOnlyHint=True but changes data "
                      f"({', '.join(evidence)}): the client may call it without confirmation."))
        elif deletes and annotations.get("destructiveHint") is False:
            bugs.append(_bug(
                node, f"[annotations] tool {name} deletes ({', '.join(evidence)}) but is annotated "
                      f"destructiveHint=False."))
    if foreign:
        shown = ", ".join(foreign[:8]) + (f" (+{len(foreign) - 8})" if len(foreign) > 8 else "")
        bugs.append({
            "description": f"[names] {len(foreign)} MCP name(s) match no operation of the source "
                           f"(a client that calls the tool by its stable name will fail): {shown}.",
            "ligne": None, "severite": "majeur", "critere": "fidelity", "extrait_code": "",
            "cap_eligible": True, "verification": "checked mechanically (source names)",
        })
    if missing:
        shown = ", ".join(missing[:8]) + (f" (+{len(missing) - 8})" if len(missing) > 8 else "")
        bugs.append({
            "description": f"[annotations] {len(missing)} tool(s) without MCP annotations (title, readOnlyHint, "
                           f"destructiveHint, idempotentHint, openWorldHint): {shown}.",
            "ligne": None, "severite": "mineur", "critere": "docs", "extrait_code": "",
            "cap_eligible": True, "verification": "checked mechanically (annotations)",
        })
    return bugs


def _bug(node: ast.FunctionDef, description: str) -> dict:
    return {"description": description, "ligne": node.lineno, "severite": "majeur", "critere": "fidelity",
            "extrait_code": f"def {node.name}(", "cap_eligible": True,
            "verification": "checked mechanically (annotations)"}


def mechanical_bugs(code: str, source_names: list[str] | None = None) -> list[dict]:
    """Tous les constats mécaniques de ce module."""
    external = untrusted_content_bugs(code)
    # Un tool déjà signalé pour le texte d'une page web (D3) ne l'est pas une
    # seconde fois pour la même réponse (D5)
    already = {b["extrait_code"] for b in external}
    raw_api = [b for b in raw_api_response_bugs(code) if b["extrait_code"] not in already]
    return annotation_bugs(code, source_names) + external + poisoned_description_bugs(code) + raw_api


def facts_text(code: str, source_names: list[str] | None = None) -> str:
    """Résumé pour le prompt de l'évaluateur : constats déjà établis."""
    bugs = mechanical_bugs(code, source_names)
    if not bugs:
        return "MCP tool annotations: present on every tool, and consistent with what the visible code does."
    return "MCP tool annotations, checked mechanically (already reported, do not repeat):\n" + "\n".join(
        f"- {b['description']}" for b in bugs)


# ---------------------------------------------------------------------------
# Contenu externe (lot D, D3, OWASP MCP06) : un tool qui renvoie le texte
# d'une page web au LLM doit le marquer comme une donnée non fiable
# (délimiteurs, rappel de ne pas suivre ses instructions, longueur bornée :
# `_untrusted(...)` dans les serveurs générés). Sinon, une page peut
# glisser des instructions au LLM (injection de prompt indirecte).
# ---------------------------------------------------------------------------


def _wrapped_in_untrusted(node: ast.AST, parents: dict) -> bool:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, ast.Call):
            func = current.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if "untrusted" in name.lower():
                return True
        current = parents.get(current)
    return False


def untrusted_content_bugs(code: str) -> list[dict]:
    """Tools qui renvoient le texte d'une page web (BeautifulSoup
    `.get_text()`) sans le marquer comme une donnée non fiable."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    bugs = []
    for node in tree.body:
        decorator = _is_tool(node)
        if decorator is None:
            continue
        parents = {child: parent for parent in ast.walk(node) for child in ast.iter_child_nodes(parent)}
        raw = [sub for sub in ast.walk(node) if isinstance(sub, ast.Call) and getattr(sub.func, "attr", "") == "get_text"
               and not _wrapped_in_untrusted(sub, parents)]
        if raw:
            bugs.append({
                "description": f"[external content] tool {_mcp_name(node, decorator)} returns the text of a web page "
                               "to the LLM as is, without marking it as untrusted data or bounding its length: "
                               "a page can slip instructions into it (OWASP MCP06, indirect prompt injection).",
                "ligne": raw[0].lineno, "severite": "majeur", "critere": "auth",
                "extrait_code": f"def {node.name}(", "cap_eligible": True,
                "verification": "checked mechanically (external content)",
            })
    return bugs


# ---------------------------------------------------------------------------
# Descriptions empoisonnées (lot D, D4, OWASP MCP03) : la description d'un
# tool (docstring, `description=`) et les instructions du serveur
# (`FastMCP(instructions=...)`) sont lues par le LLM client comme des
# consignes. Une description venue d'une source hostile, ou des
# instructions mal écrites, peuvent y cacher des ordres. Les motifs sont
# volontairement étroits (formules d'injection connues, texte caché) : une
# consigne d'usage légitime (« appeler list_pets d'abord ») ne doit pas
# être signalée.
# ---------------------------------------------------------------------------

_POISON_PATTERNS = (
    ("instruction to ignore previous instructions", re.compile(
        r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|other|system)\b"
        r"[^.\n]{0,20}\b(instructions?|prompts?|rules|guidelines|directives)\b", re.I)),
    ("instruction to hide something from the user", re.compile(
        r"\b(do not|don't|never|without)\b[^.\n]{0,20}\b(tell|telling|inform|informing|mention|mentioning|"
        r"reveal|revealing|show|showing|notify|notifying|alert|alerting)\b[^.\n]{0,20}\b(the )?user\b", re.I)),
    ("hidden instruction tag", re.compile(
        r"<\s*/?\s*(important|system|instructions?|secret|hidden|admin)\s*>", re.I)),
    ("reference to the system prompt", re.compile(r"\bsystem[ _-]?prompt\b", re.I)),
    ("change of the LLM's role", re.compile(
        r"\b(you are now|from now on,? you|act as (an? )?(admin|administrator|root|developer|system))\b", re.I)),
    ("reading sensitive files of the client", re.compile(
        r"(~/\.ssh|\.ssh/|\bid_rsa\b|\bid_ed25519\b|~/\.aws|/etc/passwd|/etc/shadow|\bmcp\.json\b|"
        r"claude_desktop_config|~/\.config|~/\.netrc|\.env file)", re.I)),
    ("HTML comment (invisible to the user)", re.compile(r"<!--")),
)


def _poison_findings(text: str) -> list[str]:
    from mcp_forge.instructions import INVISIBLE
    found = [label for label, pattern in _POISON_PATTERNS if pattern.search(text)]
    # Saut de ligne, tabulation et retour chariot sont autorisés (INVISIBLE ne les contient pas)
    if INVISIBLE.search(text):
        found.append("invisible characters (zero-width, direction, \"tag\")")
    return found


def _described_texts(tree: ast.Module) -> list[tuple[str, int, str, str]]:
    """(nom, ligne, extrait, texte) pour chaque texte lu par le LLM client :
    docstring et `description=` des tools, `instructions=` de FastMCP."""
    texts = []
    for node in tree.body:
        decorator = _is_tool(node)
        if decorator is not None:
            name = _mcp_name(node, decorator)
            doc = ast.get_docstring(node, clean=False)
            if doc:
                texts.append((f"tool {name}", node.lineno, f"def {node.name}(", doc))
            if isinstance(decorator, ast.Call):
                for kw in decorator.keywords:
                    if kw.arg in ("description", "title") and isinstance(kw.value, ast.Constant) \
                            and isinstance(kw.value.value, str):
                        texts.append((f"tool {name}", node.lineno, f"def {node.name}(", kw.value.value))
    for node in tree.body:
        # Schéma de réponse (lot D, D5) : _OUTPUT_<tool> = Annotated[Any, WithJsonSchema({...})] ;
        # schéma des paramètres regroupés : _OPTIONS_<tool> (tool de plus de 50 paramètres)
        for prefix, label in (("_OUTPUT_", "response schema of"), ("_OPTIONS_", "`options` parameters of")):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id.startswith(prefix)
                                                    for t in node.targets):
                name = next(t.id for t in node.targets if isinstance(t, ast.Name)).removeprefix(prefix)
                strings = [sub.value for sub in ast.walk(node.value)
                           if isinstance(sub, ast.Constant) and isinstance(sub.value, str)]
                if strings:
                    texts.append((f"{label} {name}", node.lineno, f"{prefix}{name} =", "\n".join(strings)))
        # Prompts et valeurs permises (lot D, D6) : lus par le client et le LLM
        labels = {"_PROMPTS": "server prompts", "_ENUMS": "allowed values (reference://enums)"}
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in labels for t in node.targets):
            target = next(t.id for t in node.targets if isinstance(t, ast.Name) and t.id in labels)
            strings = [sub.value for sub in ast.walk(node.value)
                       if isinstance(sub, ast.Constant) and isinstance(sub.value, str)]
            if strings:
                texts.append((labels[target], node.lineno, f"{target} =", "\n".join(strings)))
    for sub in ast.walk(tree):
        if isinstance(sub, ast.Call) and getattr(sub.func, "id", getattr(sub.func, "attr", "")) == "FastMCP":
            for kw in sub.keywords:
                if kw.arg == "instructions" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    texts.append(("server instructions", sub.lineno, "FastMCP(", kw.value.value))
    return texts


def poisoned_description_bugs(code: str) -> list[dict]:
    """Descriptions de tools et instructions du serveur qui contiennent des
    ordres cachés ou des formules d'injection (OWASP MCP03)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    by_target: dict[tuple[str, int, str], list[str]] = {}
    texts: dict[tuple[str, int, str], str] = {}
    for target, line, extract, text in _described_texts(tree):
        for label in _poison_findings(text):
            labels = by_target.setdefault((target, line, extract), [])
            texts[(target, line, extract)] = text
            if label not in labels:
                labels.append(label)
    return [{
        "description": f"[poisoned description] {target}: {', '.join(labels)}. The client LLM reads this text "
                       "as an instruction: it may follow hidden orders in it (OWASP MCP03, tool poisoning). "
                       "Check the description in the source or in the instructions provided.",
        "ligne": line, "severite": "majeur", "critere": "auth", "extrait_code": extract, "cap_eligible": True,
        "verification": "checked mechanically (descriptions)",
        # Pour la garde d'origine (mcp_forge/eval_origin.py) : texte signalé,
        # retiré du rapport une fois l'origine fixée
        "texte_signale": texts[(target, line, extract)], "motifs": labels,
    } for (target, line, extract), labels in by_target.items()]


# ---------------------------------------------------------------------------
# Réponses des API (lot D, D5, OWASP MCP06 et MCP10) : un tool qui appelle
# une API HTTP doit renvoyer sa réponse (et ses corps d'erreur) comme une
# donnée non fiable, bornée, champs sensibles masqués — `_response_result`,
# `_api_result`, `_api_error` dans les serveurs générés, ou `_untrusted`.
# ---------------------------------------------------------------------------

_SAFE_WRAPPERS = ("untrusted", "_api_result", "_api_error", "_response_result")
_HTTP_CALLS = {"get", "post", "put", "patch", "delete", "request", "head", "options"}


def _calls_http(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr in _HTTP_CALLS:
            owner = sub.func.value
            if not (isinstance(owner, ast.Name) and owner.id in _FILE_WRITE_MODULES | {"os", "environ", "kwargs"}):
                return True
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "_fetch":
            return True
    return False


def _raw_response_part(value: ast.AST, parents: dict) -> ast.AST | None:
    """Partie d'une valeur renvoyée qui vient de la réponse HTTP sans passer
    par un des enveloppes sûres."""
    for sub in ast.walk(value):
        raw = ((isinstance(sub, ast.Attribute) and sub.attr == "text")
               or (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                   and sub.func.attr in ("json", "dumps")))
        if not raw:
            continue
        current, wrapped = parents.get(sub), False
        while current is not None and current is not value:
            if isinstance(current, ast.Call):
                func = current.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if any(w in name.lower() for w in _SAFE_WRAPPERS):
                    wrapped = True
                    break
            current = parents.get(current)
        if isinstance(value, ast.Call):
            func = value.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            wrapped = wrapped or any(w in name.lower() for w in _SAFE_WRAPPERS)
        if not wrapped:
            return sub
    return None


def raw_api_response_bugs(code: str) -> list[dict]:
    """Tools HTTP qui renvoient la réponse de l'API (ou son corps d'erreur)
    telle quelle au LLM."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    bugs = []
    for node in tree.body:
        decorator = _is_tool(node)
        if decorator is None or not _calls_http(node):
            continue
        parents = {child: parent for parent in ast.walk(node) for child in ast.iter_child_nodes(parent)}
        raw = [ret for ret in ast.walk(node) if isinstance(ret, ast.Return) and ret.value is not None
               and _raw_response_part(ret.value, parents) is not None]
        if raw:
            bugs.append({
                "description": f"[API response] tool {_mcp_name(node, decorator)} returns the API response "
                               "to the LLM as is: not marked as untrusted data, not bounded, not filtered "
                               "(sensitive fields). A response can slip instructions to the LLM or expose "
                               "secrets (OWASP MCP06, MCP10).",
                "ligne": raw[0].lineno, "severite": "majeur", "critere": "auth",
                "extrait_code": f"def {node.name}(", "cap_eligible": True,
                "verification": "checked mechanically (API responses)",
            })
    return bugs
