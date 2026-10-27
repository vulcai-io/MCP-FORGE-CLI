"""
Vérifications déterministes autour de l'évaluateur LLM (2026-10-13).

Mesuré sur eval_benchmark/ : l'évaluateur affirme parfois, avec la gravité
« bloquant », qu'une fonction de la bibliothèque standard n'existe pas ou
qu'un nom défini plus loin dans le fichier provoquera un NameError. Une
règle de prompt n'a pas suffi, et les plafonds de notation (P4)
amplifiaient ces erreurs (une fausse alerte bloquante = -1,5 à -2 points).

Ce module établit des FAITS par des moyens mécaniques — compilation, noms
indéfinis (pyflakes), import dans un sous-processus isolé — puis confronte
les bugs rapportés à ces faits :
  - un bug contredit (fonction qui existe, nom défini, import qui réussit)
    passe en gravité « a_verifier », sans plafond ;
  - un bug n'ouvre droit aux plafonds que s'il est confirmé mécaniquement
    ou appuyé par un extrait de code qui existe vraiment dans le fichier.
"""
from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Faits établis avant l'évaluation
# ---------------------------------------------------------------------------

_SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)
_ENV_ERRORS = ("ModuleNotFoundError", "ImportError", "OSError", "FileNotFoundError")


def compile_check(code: str) -> dict:
    try:
        compile(code, "server.py", "exec")
        return {"ok": True, "error": ""}
    except SyntaxError as exc:
        return {"ok": False, "error": f"SyntaxError line {exc.lineno}: {exc.msg}"}


def undefined_names(code: str) -> list[str] | None:
    """Noms utilisés mais jamais définis, selon pyflakes (None si pyflakes
    est indisponible ou si le code ne compile pas)."""
    try:
        from pyflakes import checker, messages
    except ImportError:
        return None
    try:
        tree = compile(code, "server.py", "exec", flags=0x400)  # ast.PyCF_ONLY_AST
    except SyntaxError:
        return None
    found = checker.Checker(tree, filename="server.py")
    undefined = (messages.UndefinedName, messages.UndefinedLocal, messages.UndefinedExport)
    return sorted({m.message_args[0] for m in found.messages if isinstance(m, undefined)})


def import_check(code: str, timeout: float = 20.0) -> dict:
    """Importe le serveur dans un sous-processus isolé (`python -I`, dossier
    temporaire, environnement sans aucune variable de type clé/token/secret).
    `kind` distingue une erreur du code d'une dépendance d'environnement
    absente (bibliothèque native, paquet non installé)."""
    env = {k: v for k, v in os.environ.items() if not _SECRET_ENV.search(k)}
    with tempfile.TemporaryDirectory(prefix="mcpforge_eval_") as tmp:
        path = Path(tmp) / "server.py"
        path.write_text(code, encoding="utf-8")
        loader = (
            "import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('evaluated_server', {str(path)!r})\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "sys.modules['evaluated_server'] = module\n"
            "spec.loader.exec_module(module)\n"
        )
        try:
            result = subprocess.run([sys.executable, "-I", "-c", loader], cwd=tmp, env=env,
                                    capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"ok": None, "kind": "timeout", "error": f"import took more than {timeout:.0f} s"}
    if result.returncode == 0:
        return {"ok": True, "kind": "", "error": ""}
    last = (result.stderr.strip().splitlines() or ["unknown error"])[-1]
    kind = "environment" if last.split(":", 1)[0].strip() in _ENV_ERRORS else "code"
    return {"ok": False, "kind": kind, "error": last[:300]}


def static_facts(code: str, run_import: bool = True) -> dict:
    facts = {"compile": compile_check(code), "undefined_names": undefined_names(code)}
    if run_import and facts["compile"]["ok"]:
        facts["import"] = import_check(code)
    return facts


# ---------------------------------------------------------------------------
# Confrontation des bugs rapportés aux faits
# ---------------------------------------------------------------------------

_EXISTENCE_CLAIM = re.compile(
    r"n['’]existe pas|does not exist|doesn['’]t exist|not exist|inexistant|nonexistent|non-existent|"
    # pas « undefined » seul : « undefined behavior » (C) n'est pas un nom indéfini
    r"is not defined|not defined|is undefined|undefined name|non défini|NameError|AttributeError|ImportError|"
    r"ModuleNotFoundError|has no attribute",
    re.IGNORECASE,
)
_IMPORT_TIME_CLAIM = re.compile(r"SyntaxError|NameError|ImportError|ModuleNotFoundError|at import|à l['’]import",
                                re.IGNORECASE)
_CLAIM_WINDOW = 100
_DOTTED = re.compile(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)")
_BACKTICKED = re.compile(r"`([^`\n]{1,200})`")


def _stdlib_attr_exists(dotted: str) -> bool | None:
    """True / False si `dotted` désigne un attribut d'un module de la
    bibliothèque standard ; None si ce n'est pas un nom de la bibliothèque
    standard (rien n'est importé hors bibliothèque standard)."""
    parts = dotted.split(".")
    if parts[0] not in getattr(sys, "stdlib_module_names", ()):
        return None
    for i in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except ImportError:
            continue
        for attr in parts[i:]:
            if not hasattr(obj, attr):
                return False
            obj = getattr(obj, attr)
        return True
    return None


def _defined_in(code: str, name: str) -> bool:
    pattern = rf"^\s*(?:async\s+)?def\s+{re.escape(name)}\b|^\s*class\s+{re.escape(name)}\b|^\s*{re.escape(name)}\s*[:=]"
    return re.search(pattern, code, re.MULTILINE) is not None


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def quote_found(text: str, code: str, min_len: int = 8) -> bool:
    """Le texte cite-t-il du code qui existe vraiment dans le fichier ?
    (extrait entre backticks, ou texte brut, comparés espaces normalisés)."""
    if not text:
        return False
    haystack = _normalized(code)
    candidates = _BACKTICKED.findall(text) or [text]
    for fragment in candidates:
        fragment = _normalized(fragment).rstrip(".…")
        if len(fragment) >= min_len and fragment in haystack:
            return True
    return False


def verify_bug(bug: dict, code: str, facts: dict) -> dict:
    """Ajoute à `bug` : `verification` (texte) et `cap_eligible` (bool). Un
    bug contredit passe en gravité "a_verifier" (gravité d'origine gardée
    dans `severite_llm`)."""
    text = f"{bug.get('description', '')} {bug.get('extrait_code', '')}"
    severity = bug.get("severite")
    contradicted, confirmed = "", ""
    undefined = facts.get("undefined_names")
    imported = (facts.get("import") or {}).get("ok")

    claims = list(_EXISTENCE_CLAIM.finditer(text))
    if claims:
        # Seuls les noms cités AU VOISINAGE d'une affirmation d'inexistence
        # sont vérifiés : un autre nom cité ailleurs dans la description
        # (« restype = c_int, il faudrait c_double ») n'est pas visé.
        window = " ".join(text[max(0, m.start() - _CLAIM_WINDOW):m.end() + _CLAIM_WINDOW] for m in claims)
        verdicts = {d: _stdlib_attr_exists(d) for d in set(_DOTTED.findall(window))}
        missing = [d for d, ok in verdicts.items() if ok is False]
        existing = [d for d, ok in verdicts.items() if ok is True]
        bare = {n for n in _BACKTICKED.findall(window) if re.fullmatch(r"[A-Za-z_]\w*", n)}
        really_undefined = sorted(bare & set(undefined or []))
        if missing or really_undefined:
            confirmed = f"confirmé : {', '.join(missing + really_undefined)} introuvable(s)"
        elif existing:
            contradicted = f"contredit : {', '.join(sorted(existing))} existe(nt) dans la bibliothèque standard"
        elif undefined == [] and bare and all(_defined_in(code, n) for n in bare):
            contradicted = f"contredit : {', '.join(sorted(bare))} défini(s) dans le fichier, aucun nom indéfini (pyflakes)"

    if not (contradicted or confirmed) and severity == "bloquant" and _IMPORT_TIME_CLAIM.search(text):
        if facts.get("compile", {}).get("ok") and imported is True and undefined == []:
            contradicted = "contredit : le fichier compile, s'importe sans erreur et pyflakes ne signale aucun nom indéfini"
        elif imported is False and (facts.get("import") or {}).get("kind") == "code":
            confirmed = f"confirmé : l'import échoue ({facts['import']['error']})"

    if contradicted and severity in ("bloquant", "majeur", "mineur"):
        bug["severite_llm"] = severity
        bug["severite"] = "a_verifier"
        bug["verification"] = contradicted
        bug["cap_eligible"] = False
    elif confirmed:
        bug["verification"] = confirmed
        bug["cap_eligible"] = True
    else:
        supported = quote_found(bug.get("extrait_code", ""), code)
        bug["verification"] = "extrait cité trouvé dans le fichier" if supported else \
            "non confirmé : aucun extrait de code vérifiable"
        bug["cap_eligible"] = supported
    return bug


def verify_report(report: dict, code: str, facts: dict) -> dict:
    """Vérifie chaque bug ; un problème de checklist n'ouvre droit à son
    plafond que si sa preuve cite du code présent dans le fichier."""
    for bug in report.get("bugs_critiques", []):
        if isinstance(bug, dict):
            verify_bug(bug, code, facts)
    for item in report.get("checklist_securite", []):
        if isinstance(item, dict) and item.get("statut") == "probleme" and "cap_eligible" not in item:
            item["cap_eligible"] = quote_found(item.get("preuve", ""), code)
    report["verifications"] = {
        "compile": facts.get("compile"), "undefined_names": facts.get("undefined_names"),
        "import": facts.get("import"),
        "bugs_contredits": sum(1 for b in report.get("bugs_critiques", [])
                               if isinstance(b, dict) and b.get("severite") == "a_verifier"),
    }
    return report
