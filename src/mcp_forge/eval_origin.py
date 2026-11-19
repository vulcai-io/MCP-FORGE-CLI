"""
Origine des défauts relevés par l'évaluateur (lot D, D7, décisions du PO du
2026-10-30, 2026-11-01 et 2026-11-12).

Chaque défaut a une origine :
- `generateur` (par défaut) : compté dans la note ;
- `source` : la spec de l'API contient le défaut et le serveur le reproduit
  fidèlement ;
- `utilisateur` : le défaut vient d'une instruction écrite par
  l'utilisateur (`server_instructions`, `tool_instructions`).
Les défauts `source` et `utilisateur` n'ont aucun effet sur la note (ni
plafond ni moyenne) mais restent affichés, avec leur gravité.

La garde est mécanique, jamais confiée au LLM :
- `source` exige un élément nommé `{tool, sorte, parametre, valeur}` ; il
  n'est retenu que si (1) la spec contient cet élément avec cette valeur
  (faits transmis par le générateur, `source_facts`) et (2) le code généré
  le reproduit à l'identique. Sinon le défaut redevient `generateur`, avec
  la raison (`origine_refusee`).
- `utilisateur` n'est retenu que si le passage signalé se trouve dans les
  instructions de l'utilisateur (`user_texts`). Le même texte ajouté par le
  générateur (absent des instructions) reste `generateur`.
Les descriptions restent comptées (décision du 2026-11-01) : aucune sorte
« description ».
"""
from __future__ import annotations

import ast
import re
from typing import Any

from mcp_forge.naming import mcp_tool_name

ORIGINS = ("generateur", "source", "utilisateur")
SOURCE_KINDS = ("methode", "chemin", "emplacement", "obligatoire", "type", "champ_corps",
                "valeurs_permises", "schema_reponse")
_LOCATIONS = {"path", "query", "header", "body", "formData"}
_PY_TYPE = {"string": "str", "integer": "int", "number": "float", "boolean": "bool", "array": "list",
            "object": "dict"}
_MAX_ENUM = 50
_MIN_USER_PASSAGE = 12


# --- Faits de la source (transmis par le générateur) ---------------------------

def source_facts(tools: list) -> dict[str, dict[str, Any]]:
    """Faits de la spec par nom MCP, pris sur les tools découverts AVANT
    l'enrichissement (le LLM ne touche ni aux paramètres ni aux chemins)."""
    facts: dict[str, dict[str, Any]] = {}
    for tool in tools:
        params: dict[str, dict[str, Any]] = {}
        body: list[str] = []
        for p in [*tool.parameters, *getattr(tool, "option_parameters", [])]:
            location = "body" if p.param_in in ("body", "body_array") else (p.param_in or "query")
            params[p.name] = {"in": location, "required": bool(p.required), "type": p.type.value,
                              "format": getattr(p, "format", "") or "",
                              "enum": [str(v) for v in (p.enum_values or [])][:_MAX_ENUM]}
            if location in ("body", "formData"):
                body.append(p.name)
        response = tool.response_schema or {}
        facts[mcp_tool_name(tool.name) or tool.name] = {
            "method": (tool.http_method or "").upper(), "path": tool.endpoint or "", "params": params,
            "body_fields": body, "response_fields": sorted(_response_fields(response)),
        }
    return facts


def _response_fields(schema: dict, depth: int = 0) -> set[str]:
    if not isinstance(schema, dict) or depth > 3:
        return set()
    fields: set[str] = set()
    for name, sub in (schema.get("properties") or {}).items():
        fields.add(name)
        fields |= _response_fields(sub, depth + 1)
    if isinstance(schema.get("items"), dict):
        fields |= _response_fields(schema["items"], depth + 1)
    return fields


def user_texts(server_instructions: str | None, tool_instructions: dict[str, str] | None) -> list[str]:
    return [t for t in [server_instructions or "", *(tool_instructions or {}).values()] if t.strip()]


# --- Code généré : la partie qui concerne un tool -------------------------------

def _tool_sources(code: str) -> dict[str, tuple[ast.FunctionDef, str, dict]]:
    """{nom MCP: (fonction, texte de la fonction + de son _OUTPUT_, valeurs
    permises par paramètre lues dans _ENUMS)}"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    outputs, enums = {}, {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith("_OUTPUT_"):
                    outputs[target.id.removeprefix("_OUTPUT_")] = ast.get_source_segment(code, node) or ""
                if isinstance(target, ast.Name) and target.id == "_ENUMS":
                    try:
                        enums = ast.literal_eval(node.value)
                    except ValueError:
                        enums = {}
    found = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "tool"
                    and isinstance(dec.func, ast.Attribute)):
                name = next((kw.value.value for kw in dec.keywords if kw.arg == "name"
                             and isinstance(kw.value, ast.Constant)), node.name)
                found[name] = (node, (ast.get_source_segment(code, node) or ""), outputs.get(node.name, ""))
    return {k: (v[0], v[1] + "\n" + v[2], enums.get(k) or {}) for k, v in found.items()}


def _arg(func: ast.FunctionDef, name: str) -> tuple[ast.arg | None, bool]:
    """(argument Python du paramètre, obligatoire ?)"""
    safe = re.sub(r"[^\w]", "_", name)
    args = func.args.args
    required_count = len(args) - len(func.args.defaults)
    for i, arg in enumerate(args):
        if arg.arg in (safe, f"{safe}_", f"p{safe}"):
            return arg, i < required_count
    return None, False


def _line_with_key(text: str, name: str) -> str:
    return next((line for line in text.splitlines() if f'"{name}": ' in line), "")


def _reproduced(kind: str, param: str | None, value: str, func: ast.FunctionDef, text: str,
                enums: dict, spec_type: str = "") -> str:
    """"" si le code reproduit l'élément à l'identique, sinon la raison."""
    if kind == "methode":
        method = value.upper()
        ok = bool(re.search(rf'client\.request\(\s*"{method}"', text)
                  or re.search(rf"client\.{method.lower()}\(", text))
        return "" if ok else f"the code does not send a {method}"
    if kind == "chemin":
        return "" if f'"{value}"' in text else "the path is not the one in the code"
    if kind == "schema_reponse":
        return "" if f"'{value}'" in text or f'"{value}"' in text else "field missing from the response schema"
    if kind == "valeurs_permises":
        served = [str(v) for v in enums.get(param or "", [])]
        missing = [v for v in _values(value) if v not in served]
        return "" if served and not missing else "allowed values missing from the server (_ENUMS)"
    if not param:
        return "parameter element without a parameter name"
    if kind == "champ_corps":
        line = _line_with_key(text, param)
        return "" if ("json=" in line or "data=" in line) else "field missing from the body sent"
    arg, required = _arg(func, param)
    if arg is None:
        return "parameter missing from the tool signature"
    if kind == "obligatoire":
        return "" if required == _truthy(value) else "the code does not reproduce this required flag"
    if kind == "type":
        annotation = ast.unparse(arg.annotation) if arg.annotation is not None else ""
        declared, _ = _type_and_format(value)
        # Une valeur réduite au format (« date-time ») : le type vient de la spec,
        # déjà vérifiée par _spec_has ; le code doit le reproduire.
        declared = declared or spec_type
        expected = _PY_TYPE.get(declared, declared)
        return "" if annotation.split("|")[0].strip().startswith(expected) else "different type in the code"
    if kind == "emplacement":
        location = value
        line = _line_with_key(text, param)
        if location == "path":
            ok = "{" + param + "}" in text and "url.format(" in text
        elif location == "query":
            ok = "params=" in line
        elif location == "header":
            ok = "_extra_headers" in line
        else:  # body / formData
            ok = "json=" in line or "data=" in line
        return "" if ok else f"the code does not send this parameter in {location}"
    return "unknown kind"


def _values(value: str) -> list[str]:
    return [v.strip().strip("'\"") for v in re.split(r"[,|]", value) if v.strip()]


_TYPE_FORMAT_SEPARATORS = re.compile(r"[\s(),/:]+")


def _type_and_format(value: str) -> tuple[str, str]:
    """« string (date-time) », « string/date-time », « integer », « int64 » →
    (type JSON Schema ou "", format ou "") ; ("", "") si illisible."""
    tokens = [t for t in _TYPE_FORMAT_SEPARATORS.split(str(value or "").lower()) if t]
    if len(tokens) == 1:
        return (tokens[0], "") if tokens[0] in _PY_TYPE else ("", tokens[0])
    if len(tokens) == 2 and tokens[0] in _PY_TYPE:
        return tokens[0], tokens[1]
    return "", ""


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in ("true", "oui", "yes", "required", "obligatoire", "1")


def _spec_has(kind: str, param: str | None, value: str, fact: dict) -> str:
    """"" si la spec contient l'élément avec cette valeur, sinon la raison."""
    if kind == "methode":
        return "" if fact["method"] == value.upper() else "different method in the spec"
    if kind == "chemin":
        return "" if fact["path"] == value else "different path in the spec"
    if kind == "schema_reponse":
        return "" if value in fact["response_fields"] else "field missing from the response schema of the spec"
    if kind == "champ_corps":
        return "" if (param or value) in fact["body_fields"] else "field missing from the body of the spec"
    spec_param = fact["params"].get(param or "")
    if spec_param is None:
        return "parameter missing from the spec"
    if kind == "emplacement":
        return "" if value in _LOCATIONS and spec_param["in"] == value else "different location in the spec"
    if kind == "obligatoire":
        return "" if spec_param["required"] == _truthy(value) else "different required flag in the spec"
    if kind == "type":
        declared, fmt = _type_and_format(value)
        if not declared and not fmt:
            return "type illisible"
        if declared and spec_param["type"] != declared:
            return "different type in the spec"
        if fmt and spec_param.get("format", "") != fmt:
            return "different format in the spec"
        return ""
    if kind == "valeurs_permises":
        values = _values(value)
        return "" if values and set(values) <= set(spec_param["enum"]) else "values missing from the spec"
    return "unknown kind"


# --- Classement ----------------------------------------------------------------

SPEC_CLAIM_UNVERIFIED = "claim about the spec not verified"


def _source_reason(bug: dict, facts: dict[str, dict], tools: dict) -> str:
    return _source_check(bug, facts, tools)[0]


def _source_check(bug: dict, facts: dict[str, dict], tools: dict) -> tuple[str, bool]:
    """(motif du refus ou "", vrai si le refus vient de la spec elle-même :
    le tool ou l'élément nommé n'y est pas, ou pas avec cette valeur). Ce
    second cas est une affirmation de l'évaluateur sur la spec que la spec
    dément : mesuré au banc (hallucinations sur la spec), signalé dans le
    rapport, sans autre effet sur la note que l'origine refusée."""
    element = bug.get("element_source")
    if not isinstance(element, dict):
        return "no source element named", False
    tool, kind = str(element.get("tool") or ""), str(element.get("sorte") or "")
    param = element.get("parametre") or None
    value = str(element.get("valeur") or "")
    if kind not in SOURCE_KINDS:
        return f"kind \"{kind}\" not accepted", False
    if not value and kind != "champ_corps":
        return "element without a value", False
    if kind == "champ_corps":
        param = param or value
    fact = facts.get(tool)
    if fact is None:
        return f"tool \"{tool}\" missing from the source", bool(facts)
    if tool not in tools:
        return f"tool \"{tool}\" missing from the code", False
    reason = _spec_has(kind, param, value, fact)
    if reason:
        return reason, True
    func, text, enums = tools[tool]
    spec_type = (fact["params"].get(param or "") or {}).get("type", "")
    return _reproduced(kind, param, value, func, text, enums, spec_type), False


def _normalize(text: str) -> str:
    return " ".join(str(text).split())


_QUOTED = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"")
# Seule ligne où le générateur écrit les instructions de l'utilisateur
# (server_instructions) : `mcp = FastMCP("<nom>", instructions='…')`. Les
# tool_instructions vont dans les docstrings, sans guillemets : elles
# passent par le cas « passage tel quel ».
_CARRIER_NAMES = {"mcp", "FastMCP", "instructions"}
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _in_user_texts(passage: str, texts: list[str], code: str = "") -> bool:
    """Le passage cité vient des instructions de l'utilisateur : soit tel
    quel, soit c'est la ligne de code qui les porte (l'évaluateur la cite
    souvent : `mcp = FastMCP("x", instructions='…')`), à quatre conditions :
    l'extrait se trouve mot pour mot dans le code généré ; il contient au moins une chaîne d'au moins _MIN_USER_PASSAGE
    caractères ; chacune de ces chaînes vient mot pour mot des instructions
    de l'utilisateur ; hors des chaînes, il n'y a que les noms de la ligne
    porteuse (_CARRIER_NAMES). Une chaîne du générateur à côté, une ligne
    ressemblante absente des instructions ou un autre appel (`verify=False`…)
    suffisent à refuser."""
    normalized_texts = [_normalize(t) for t in texts]

    def from_user(fragment: str) -> bool:
        fragment = _normalize(fragment).strip("\"'(),")
        return len(fragment) >= _MIN_USER_PASSAGE and any(fragment in t for t in normalized_texts)

    passage = passage or ""
    if from_user(passage):
        return True
    if _normalize(passage) not in _normalize(code):
        return False
    quoted = [a or b for a, b in _QUOTED.findall(passage)]
    long_quoted = [q for q in quoted if len(_normalize(q)) >= _MIN_USER_PASSAGE]
    outside = set(_IDENTIFIER.findall(_QUOTED.sub(" ", passage)))
    return bool(long_quoted) and all(from_user(q) for q in long_quoted) and outside <= _CARRIER_NAMES


def _poisoning_from_user(bug: dict, texts: list[str]) -> bool:
    """Constat mécanique d'empoisonnement : toutes ses formules viennent
    d'une instruction de l'utilisateur contenue dans le texte signalé."""
    from mcp_forge.eval_annotations import _poison_findings
    flagged = _normalize(bug.get("texte_signale") or "")
    labels = set(bug.get("motifs") or [])
    if not flagged or not labels:
        return False
    found: set[str] = set()
    for text in texts:
        if _normalize(text) in flagged:
            found |= set(_poison_findings(text))
    return labels <= found


def classify_origins(report: dict, code: str, facts: dict | None) -> None:
    """Fixe `origine` sur chaque défaut (garde mécanique) et résume les
    défauts hors note dans `defauts_hors_note`."""
    facts = facts or {}
    spec = facts.get("source_facts") or {}
    texts = facts.get("user_texts") or []
    tools = _tool_sources(code) if spec else {}
    counts = {"source": 0, "utilisateur": 0}
    unverified = 0
    for bug in report.get("bugs_critiques") or []:
        if not isinstance(bug, dict):
            continue
        claimed = bug.get("origine") if bug.get("origine") in ORIGINS else "generateur"
        if bug.get("texte_signale") is not None:
            # Constat mécanique d'empoisonnement : utilisateur seulement si
            # toutes ses formules viennent des instructions de l'utilisateur
            bug["origine"] = "utilisateur" if _poisoning_from_user(bug, texts) else "generateur"
            bug.pop("texte_signale")
        elif claimed == "source":
            reason, about_spec = _source_check(bug, spec, tools)
            bug["origine"] = "generateur" if reason else "source"
            if reason:
                bug["origine_refusee"] = f"source rejected: {reason}"
            if about_spec:
                bug["affirmation_spec"] = SPEC_CLAIM_UNVERIFIED
                unverified += 1
        elif claimed == "utilisateur":
            if not _in_user_texts(bug.get("extrait_code") or "", texts, code):
                bug["origine"] = "generateur"
                bug["origine_refusee"] = "user rejected: passage missing from the user's instructions"
            else:
                bug["origine"] = "utilisateur"
        else:
            bug["origine"] = "generateur"
        if bug["origine"] in counts:
            counts[bug["origine"]] += 1
    # Format de defauts_hors_note figé : la migration en lit le texte
    # (api/main.py, off_score_count) ; le décompte des affirmations sur la
    # spec démenties a sa propre clé.
    report["defauts_hors_note"] = counts
    report["affirmations_spec_non_verifiees"] = unverified


def off_score_total(report: Any) -> int | None:
    """Nombre de défauts hors note d'un rapport (source + utilisateur), gardé
    dans generations.off_score_count : la purge vide le rapport, pas ce
    compteur. None si le rapport n'a pas classé les origines."""
    counts = report.get("defauts_hors_note") if isinstance(report, dict) else None
    if not isinstance(counts, dict):
        return None
    return sum(int(v) for v in counts.values() if isinstance(v, int) and v > 0)


def counted(bug: Any) -> bool:
    """Le défaut compte-t-il dans la note ?"""
    return isinstance(bug, dict) and bug.get("origine", "generateur") == "generateur"
