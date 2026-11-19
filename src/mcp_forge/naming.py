"""
Nom MCP d'un tool, à partir du nom de la source (operationId, nom de
fonction…). Règle unique, utilisée par le générateur (_assign_mcp_names) et
par l'évaluateur (contrôle des noms, eval_annotations) : les deux doivent
donner exactement le même nom, sinon l'évaluateur signale comme « absent de
la source » un nom que le générateur a fabriqué (constat Stripe du
2026-11-01 : 4 operationId de plus de 64 caractères).

- Caractères refusés par MCP (tout sauf lettres, chiffres, « _ », « - »)
  remplacés par « _ », « _ » de début et de fin retirés.
- 64 caractères au plus. Un nom plus long garde ses premiers et ses
  derniers mots entiers (au plus 27 caractères de chaque côté, coupure
  entre deux mots, sur « _ »), puis « _ » et 8 caractères hexadécimaux de
  l'empreinte SHA-256 (hashlib) du nom d'origine en UTF-8 (décision du PO,
  2026-11-12) : la fin du nom porte souvent le verbe qui distingue deux
  opérations (…_design_activate, …_design_deactivate). Le même nom de la
  source donne toujours le même nom MCP ; deux noms longs proches restent
  distincts par l'empreinte. Un premier ou un dernier mot de plus de
  27 caractères est coupé au caractère près.
  Exemple : post_test_helpers_issuing_personalization_designs_
  personalization_design_deactivate → post_test_helpers_issuing_design_
  deactivate_af519ef7.
- Doublon restant (deux noms de la source identiques après remplacement des
  caractères) : suffixe « _2 », « _3 »… sans dépasser 64 caractères.
"""
from __future__ import annotations

import hashlib
import re

MAX_LENGTH = 64
DIGEST_LENGTH = 8
KEPT_PER_SIDE = 27        # 27 + « _ » + 27 + « _ » + 8 = 64 au plus
_INVALID = re.compile(r"[^A-Za-z0-9_-]")
_DEDUP = re.compile(r"^(.*)(_\d+)$")


def mcp_tool_name(source_name: str) -> str:
    """Nom MCP valide et stable pour un nom de la source ("" si rien ne reste)."""
    safe = _INVALID.sub("_", source_name or "").strip("_")
    if len(safe) <= MAX_LENGTH:
        return safe
    digest = hashlib.sha256(source_name.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]
    words = [w for w in safe.split("_") if w]
    head = "_".join(_whole_words(words)) or safe[:KEPT_PER_SIDE].strip("_")
    tail = "_".join(_whole_words(words[::-1])[::-1]) or safe[-KEPT_PER_SIDE:].strip("_")
    return f"{head}_{tail}_{digest}"


def _whole_words(words: list[str]) -> list[str]:
    """Premiers mots entiers dont la longueur jointe par « _ » ne dépasse
    pas KEPT_PER_SIDE caractères ([] si le premier mot est déjà trop long)."""
    kept: list[str] = []
    for word in words:
        if len("_".join([*kept, word])) > KEPT_PER_SIDE:
            break
        kept.append(word)
    return kept


def with_dedup_suffix(name: str, n: int) -> str:
    """n-ième variante d'un nom déjà pris (n >= 2), 64 caractères au plus."""
    suffix = f"_{n}"
    return name[:MAX_LENGTH - len(suffix)] + suffix


def comes_from(name: str, source_names: set[str]) -> bool:
    """Le nom MCP `name` est-il celui d'un des noms de la source (déjà passés
    par mcp_tool_name), éventuellement avec un suffixe de doublon ?"""
    if name in source_names:
        return True
    match = _DEDUP.match(name)
    if not match:
        return False
    n = int(match.group(2)[1:])
    return n >= 2 and any(with_dedup_suffix(known, n) == name for known in source_names)
