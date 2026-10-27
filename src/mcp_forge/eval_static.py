"""
Analyseurs statiques déterministes autour de l'évaluateur (prototype,
2026-10-14). Même rôle que eval_checks / eval_dynamic : établir des FAITS
sans LLM, à donner à l'évaluateur avant le code.

Mesuré sur le jeu non vu v2 (eval_benchmark/) : l'évaluateur LLM manque le
ReDoS (0/2), la comparaison lâche en JavaScript (1/2), et le secret écrit
dans les logs (0/2 avec les vérifications). Ces familles de défauts se
détectent mécaniquement :

  - bandit      : appels dangereux connus (désérialisation pickle/marshal,
                  yaml.load, eval/exec, shell=True, verify=False). Liste de
                  tests restreinte : les règles bruyantes sur du code généré
                  (subprocess sans shell, bind 0.0.0.0, mots de passe
                  « codés en dur »…) sont exclues.
  - secret_in_log : une variable dont le nom désigne un secret (token, key,
                  password…) passée telle quelle à logging/print.
  - redos       : expression régulière littérale dont une répétition
                  englobe une autre répétition non bornée sans séparateur
                  obligatoire, ex. `(a+)+`, `([a-z]+[-_]?)+` (backtracking
                  exponentiel).
  - js_loose_equality : pilote JavaScript (code JS dans des chaînes
                  Python, module qui lance `node`) utilisant `==` / `!=`
                  (règle eqeqeq ; `== null` toléré).

Actif par défaut dans l'évaluateur (MCP_FORGE_STATIC_ANALYZERS=0 le
coupe, voir mcp_forge/evaluate.py::_facts). Bandit est installé dans
l'image de l'API (api/requirements.txt), pas dans les serveurs générés ni
dans la CLI : s'il est absent, son volet est marqué « unavailable » et les
autres règles tournent quand même.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

# Tests bandit retenus (les autres sont trop bruyants sur du code généré :
# B404/B603 subprocess, B104 bind 0.0.0.0, B105-B107 « mots de passe »…)
BANDIT_TESTS = "B102,B301,B302,B307,B501,B506,B602,B605"

_SECRET_NAME = re.compile(r"(?i)(token|secret|passw(or)?d|passwd|api_?key|apikey|credential|bearer|authorization)")
_LOG_FUNCS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}


# ---------------------------------------------------------------------------
# Bandit
# ---------------------------------------------------------------------------

def bandit_findings(code: str, timeout: float = 60.0) -> list[dict] | None:
    """Résultats bandit (tests BANDIT_TESTS, confiance >= moyenne), ou None
    si bandit n'est pas installé ou a échoué."""
    # Présence vérifiée sans importer bandit : l'importer dans ce processus
    # charge ses extensions stevedore, qui écrivent une ligne ERROR (« Could
    # not load 'sarif' ») dans les logs de l'API à chaque évaluation.
    if importlib.util.find_spec("bandit") is None:
        return None
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "server.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "bandit", "-q", "-f", "json", "-t", BANDIT_TESTS, "-ii", path],
                capture_output=True, text=True, timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    return [
        {
            "rule": f"bandit:{r['test_id']}",
            "severity": r.get("issue_severity", "").lower(),
            "line": r.get("line_number"),
            "message": r.get("issue_text", ""),
        }
        for r in data.get("results", [])
    ]


# ---------------------------------------------------------------------------
# Secret écrit dans les logs
# ---------------------------------------------------------------------------

def _secret_refs(node: ast.AST) -> list[str]:
    """Noms de secrets utilisés COMME VALEUR dans `node` (pas dans un test :
    `"set" if TOKEN else "unset"`, `bool(TOKEN)`, `len(TOKEN)` sont sûrs)."""
    found: list[str] = []

    def visit(n: ast.AST) -> None:
        if isinstance(n, ast.IfExp):
            visit(n.body)
            visit(n.orelse)
            return
        if isinstance(n, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
            return
        if isinstance(n, ast.Call):
            fname = n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
            if fname in ("len", "bool", "type", "isinstance", "hash", "mask", "_mask", "redact", "_redact"):
                return
            if fname in ("getenv", "get") and n.args and isinstance(n.args[0], ast.Constant) \
                    and isinstance(n.args[0].value, str) and _SECRET_NAME.search(n.args[0].value):
                found.append(n.args[0].value)
                return
        if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) \
                and isinstance(n.slice.value, str) and _SECRET_NAME.search(n.slice.value) \
                and "environ" in ast.unparse(n.value):
            found.append(n.slice.value)
            return
        if isinstance(n, ast.Name) and _SECRET_NAME.search(n.id):
            found.append(n.id)
            return
        if isinstance(n, ast.Attribute) and _SECRET_NAME.search(n.attr):
            found.append(n.attr)
            return
        for child in ast.iter_child_nodes(n):
            visit(child)

    visit(node)
    return found


def secret_in_log_findings(tree: ast.AST) -> list[dict]:
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_log = (isinstance(func, ast.Attribute) and func.attr in _LOG_FUNCS
                  and "log" in ast.unparse(func.value).lower())
        is_print = isinstance(func, ast.Name) and func.id == "print"
        is_write = isinstance(func, ast.Attribute) and func.attr == "write" \
            and ast.unparse(func.value) in ("sys.stderr", "sys.stdout")
        if not (is_log or is_print or is_write):
            continue
        names = [r for arg in [*node.args, *(k.value for k in node.keywords)] for r in _secret_refs(arg)]
        if names:
            findings.append({
                "rule": "secret_in_log",
                "severity": "high",
                "line": node.lineno,
                "message": f"secret value written to logs/output: {', '.join(sorted(set(names)))}",
            })
    return findings


# ---------------------------------------------------------------------------
# ReDoS
# ---------------------------------------------------------------------------

def _sre_parse(pattern: str):
    try:
        import re._parser as sre_parse  # Python 3.11+
    except ImportError:  # pragma: no cover
        import sre_parse  # type: ignore
    return sre_parse.parse(pattern)


_REPEATS = ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT")


def _items(seq) -> list:
    return list(seq.data if hasattr(seq, "data") else seq)


def _nullable(item) -> bool:
    """Le motif `item` peut-il ne rien consommer ?"""
    op, av = item
    name = str(op)
    if name in _REPEATS:
        return av[0] == 0 or all(_nullable(i) for i in _items(av[2]))
    if name == "SUBPATTERN":
        return all(_nullable(i) for i in _items(av[-1]))
    if name == "BRANCH":
        return any(all(_nullable(i) for i in _items(b)) for b in av[1])
    return name in ("AT", "ASSERT", "ASSERT_NOT")


def _has_unbounded_repeat(seq) -> bool:
    for op, av in _items(seq):
        name = str(op)
        if name in _REPEATS and av[1] > 1:
            return True
        if name == "SUBPATTERN" and _has_unbounded_repeat(av[-1]):
            return True
        if name == "BRANCH" and any(_has_unbounded_repeat(b) for b in av[1]):
            return True
    return False


def _ambiguous_body(seq) -> bool:
    """Le corps d'une répétition est ambigu si l'un de ses éléments est une
    répétition non bornée et que TOUS les autres éléments sont facultatifs :
    une même chaîne se découpe alors d'un nombre exponentiel de façons."""
    items = _items(seq)
    if len(items) == 1 and str(items[0][0]) == "SUBPATTERN":
        return _ambiguous_body(items[0][1][-1])
    for i, (op, av) in enumerate(items):
        name = str(op)
        inner_unbounded = (name in _REPEATS and av[1] > 1) or \
            (name == "SUBPATTERN" and _has_unbounded_repeat(av[-1]))
        if inner_unbounded and all(_nullable(o) for j, o in enumerate(items) if j != i):
            return True
    return False


def redos_risk(pattern: str) -> bool:
    """Vrai si une répétition non bornée englobe un corps ambigu (étoile
    imbriquée sans séparateur obligatoire). Heuristique, non exhaustive :
    les alternatives qui se recouvrent (`(a|a)*`) ne sont pas détectées."""
    try:
        parsed = _sre_parse(pattern)
    except Exception:
        return False

    def walk(seq) -> bool:
        for op, av in _items(seq):
            name = str(op)
            if name in _REPEATS:
                if av[1] > 1 and _ambiguous_body(av[2]):
                    return True
                if walk(av[2]):
                    return True
            elif name == "SUBPATTERN":
                if walk(av[-1]):
                    return True
            elif name == "BRANCH":
                if any(walk(b) for b in av[1]):
                    return True
        return False

    return walk(parsed)


_RE_FUNCS = {"compile", "match", "fullmatch", "search", "findall", "finditer", "sub", "subn", "split"}


def redos_findings(tree: ast.AST) -> list[dict]:
    findings = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in _RE_FUNCS and node.args):
            continue
        base = ast.unparse(node.func.value)
        if not re.fullmatch(r"_?re|regex", base):
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and redos_risk(arg.value):
            findings.append({
                "rule": "redos",
                "severity": "high",
                "line": node.lineno,
                "message": f"regular expression with nested unbounded repetition (catastrophic backtracking): {arg.value!r}",
            })
    return findings


# ---------------------------------------------------------------------------
# JavaScript : comparaison lâche dans le pilote
# ---------------------------------------------------------------------------

_JS_RUNNERS = ("node", "ts-node", "tsx", "deno", "bun")
_JS_HINT = re.compile(r"console\.|\bconst\b|\blet\b|=>|\bfunction\b|require\(|;\s*$")
_JS_STRING_LITERAL = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")
_LOOSE_EQ = re.compile(r"(?<![=!<>])(==|!=)(?!=)\s*(\S+)?")


def js_loose_equality_findings(tree: ast.AST) -> list[dict]:
    consts = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    if not any(c.value in _JS_RUNNERS for c in consts):
        return []
    findings = []
    for c in consts:
        text = c.value
        if not _JS_HINT.search(text):
            continue
        code_only = _JS_STRING_LITERAL.sub('""', text)
        for m in _LOOSE_EQ.finditer(code_only):
            if (m.group(2) or "").startswith(("null", "undefined")):
                continue  # `x == null` : idiome toléré par eqeqeq ("smart")
            findings.append({
                "rule": "js_loose_equality",
                "severity": "medium",
                "line": c.lineno,
                "message": f"JavaScript driver uses loose equality '{m.group(1)}' (type coercion): {text.strip()[:120]!r}",
            })
            break
    return findings


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def run_static_analyzers(code: str, use_bandit: bool = True) -> dict:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"ok": False, "error": f"SyntaxError line {exc.lineno}", "findings": [], "bandit": "skipped"}
    findings = secret_in_log_findings(tree) + redos_findings(tree) + js_loose_equality_findings(tree)
    bandit_status = "disabled"
    if use_bandit:
        b = bandit_findings(code)
        bandit_status = "unavailable" if b is None else "ok"
        findings += b or []
    findings.sort(key=lambda f: (f.get("line") or 0, f["rule"]))
    return {"ok": True, "findings": findings, "bandit": bandit_status}


def facts_text(result: dict) -> str:
    """Section « Tool facts » pour le prompt de l'évaluateur."""
    if not result.get("ok"):
        return "- static analyzers: not run (" + result.get("error", "") + ")"
    lines = [f"- static analyzers (bandit: {result.get('bandit')}): "
             + (f"{len(result['findings'])} finding(s)" if result["findings"] else "no finding")]
    for f in result["findings"][:15]:
        lines.append(f"  - line {f.get('line')}: [{f['rule']}] {f['message']}")
    return "\n".join(lines)
