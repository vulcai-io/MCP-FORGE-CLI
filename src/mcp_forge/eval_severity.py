"""
Plancher de gravité appliqué par le code (décision du PO, 2026-11-14).

Mesure du 2026-11-14 (banc, 4 passages + A/B avec le prompt d'avant le
lot D) : l'évaluateur notait « mineur » un secret écrit dans les journaux,
que l'analyse statique avait pourtant relevé, et un secret exigé dans l'URL
par la spec (origine « source »). La règle 21 du prompt dit « majeur au
moins » ; le code le garantit désormais :

1. un constat de l'évaluateur confirmé par l'analyse statique de sécurité
   (`SECURITY_RULES` : secret dans les journaux, pickle/marshal, eval/exec,
   yaml.load, shell, vérification TLS coupée, ReDoS) ne descend jamais sous
   « majeur ». Confirmé = le constat porte sur la ligne relevée (à deux
   lignes près) ou cite son code, hors critère `docs` (le manque
   d'avertissement de la règle 19 reste plafonné à « mineur ») ;
2. l'origine « source » ne baisse jamais la gravité : un secret que la spec
   place dans l'URL (élément validé par la garde, sorte `emplacement`,
   valeur `query`, nom de secret) est « majeur » au moins, comme s'il venait
   du générateur.

Le plancher ne crée aucun constat et ne baisse jamais une gravité. La
gravité donnée par l'évaluateur est gardée dans `severite_evaluateur`, la
raison dans `severite_relevee`.
"""
from __future__ import annotations

import re

from mcp_forge.eval_static import _SECRET_NAME

SECURITY_RULES = {
    "secret_in_log": "secret written to logs",
    "redos": "regular expression open to ReDoS",
    "bandit:B102": "exec",
    "bandit:B301": "unsafe deserialization (pickle)",
    "bandit:B302": "unsafe deserialization (marshal)",
    "bandit:B307": "eval",
    "bandit:B501": "TLS certificate verification disabled",
    "bandit:B506": "unsafe yaml.load",
    "bandit:B602": "subprocess with shell=True",
    "bandit:B605": "shell command (os.system)",
}
_RANK = {"mineur": 1, "majeur": 2, "bloquant": 3}
_NEAR = 2


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def _confirmed_by(bug: dict, findings: list[dict], lines: list[str]) -> dict | None:
    line = bug.get("ligne")
    excerpt = _norm(bug.get("extrait_code") or "")
    for finding in findings:
        at = finding.get("line")
        if not isinstance(at, int):
            continue
        if isinstance(line, int) and abs(line - at) <= _NEAR:
            return finding
        code_line = _norm(lines[at - 1]) if 0 < at <= len(lines) else ""
        if code_line and len(code_line) >= 8 and code_line in excerpt:
            return finding
    return None


def _secret_in_url_from_source(bug: dict) -> bool:
    element = bug.get("element_source")
    return (bug.get("origine") == "source" and isinstance(element, dict)
            and element.get("sorte") == "emplacement" and str(element.get("valeur", "")).lower() == "query"
            and bool(_SECRET_NAME.search(str(element.get("parametre") or ""))))


def _raise(bug: dict, reason: str) -> None:
    bug["severite_evaluateur"] = bug.get("severite")
    bug["severite"] = "majeur"
    bug["severite_relevee"] = reason


def apply_severity_floor(report: dict, code: str, facts: dict | None) -> None:
    static = (facts or {}).get("static_analyzers") or {}
    findings = [f for f in static.get("findings") or [] if f.get("rule") in SECURITY_RULES]
    lines = code.splitlines()
    for bug in report.get("bugs_critiques") or []:
        if not isinstance(bug, dict) or _RANK.get(bug.get("severite"), 0) >= _RANK["majeur"]:
            continue
        if bug.get("severite") not in _RANK:  # « a_verifier » : affirmation démentie, pas de plancher
            continue
        # Le manque d'avertissement (règle 19, critère docs) reste plafonné
        # à « mineur » : seul le constat sur la faille elle-même est relevé.
        finding = None if bug.get("critere") == "docs" else _confirmed_by(bug, findings, lines)
        if finding is not None:
            _raise(bug, f"floor: confirmed by static analysis ({finding['rule']}, line {finding['line']}: "
                        f"{SECURITY_RULES[finding['rule']]})")
        elif _secret_in_url_from_source(bug):
            _raise(bug, "floor: a secret in the URL is major even when the source specification requires it")
