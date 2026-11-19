"""
Mode auto (0.4.1) : stdout ne porte que la ligne JSON du résultat.

Tout le reste (en-tête, résumé, progression, rapport d'évaluation, messages
d'erreur, sortie des sous-processus) part sur stderr. Une CI peut alors lire
stdout directement (`result=$(mcp-forge run … )`), sans chercher la
dernière ligne.

Deux niveaux de redirection, pendant toute la commande :
- Python : `sys.stdout` pointe sur stderr (Rich, `print`, consoles créées à
  l'import : Rich relit `sys.stdout` à chaque écriture) ;
- descripteur 1, quand stdout en a un : redirigé sur le descripteur 2, pour
  les sous-processus et les bibliothèques qui écrivent sans passer par
  Python.

La ligne JSON est mise de côté (`emit_result`) et écrite sur le vrai stdout
une fois la redirection levée, même si la commande échoue. Si la commande
échoue sans avoir produit de résultat (option invalide, YAML introuvable…),
une ligne `{"success": false, "errors": [...]}` est écrite à sa place : stdout
contient toujours exactement une ligne JSON.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Iterator

_pending: list[str] | None = None  # lignes du résultat, quand le mode auto est actif

EARLY_FAILURE = "Failed before the generation (details on stderr)"


def emit_result(payload: dict) -> None:
    """Résultat du mode auto : mis de côté pendant la commande, sinon écrit
    tout de suite sur stdout."""
    line = json.dumps(payload, ensure_ascii=False)
    if _pending is not None:
        _pending.append(line)
    else:
        print(line, file=sys.stdout, flush=True)


def _exit_code(exc: BaseException) -> int:
    code = getattr(exc, "exit_code", None)  # typer.Exit / click
    if code is None:
        code = getattr(exc, "code", 1)  # SystemExit
    if code is None:
        return 0
    return code if isinstance(code, int) else 1


def _real_fd(stream) -> int | None:
    try:
        return stream.fileno()
    except (AttributeError, OSError, ValueError):
        return None


@contextlib.contextmanager
def json_only_stdout(enabled: bool) -> Iterator[None]:
    global _pending
    if not enabled or _pending is not None:
        yield
        return
    real_stdout = sys.stdout
    out_fd, err_fd = _real_fd(real_stdout), _real_fd(sys.stderr)
    saved_fd = None
    real_stdout.flush()
    if out_fd is not None and err_fd is not None and out_fd != err_fd:
        saved_fd = os.dup(out_fd)
        os.dup2(err_fd, out_fd)
    _pending = []
    failed = False
    try:
        with contextlib.redirect_stdout(sys.stderr):
            yield
    except BaseException as exc:
        failed = _exit_code(exc) != 0
        raise
    finally:
        lines, _pending = _pending, None
        sys.stderr.flush()
        if saved_fd is not None:
            os.dup2(saved_fd, out_fd)
            os.close(saved_fd)
        if not lines and failed:
            lines = [json.dumps({"success": False, "errors": [EARLY_FAILURE]}, ensure_ascii=False)]
        for line in lines[-1:]:  # une seule ligne : la dernière écrite
            print(line, file=real_stdout)
        real_stdout.flush()
