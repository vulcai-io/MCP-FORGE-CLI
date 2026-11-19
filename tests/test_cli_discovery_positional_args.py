"""
Regression 2026-09-30, discovery/cli_app.py: missing positional arguments.

A real evaluation report on an MCP server generated from `git`: almost every tool failed because
required positional arguments (`git clone <repository> <directory>`, `git add <pathspec>`,
`git mv <source> <destination>`, etc.) were never detected. `_parse_options()` only looked at the
`-x`/`--xxx` flags, never at the synopsis line ("usage: ...") that documents positional arguments
with the `<name>` / `[<name>]` convention.

`_extract_positional_args()` fills that gap with a best-effort heuristic:
- `<name>` without enclosing brackets is required; `[<name>]` is optional;
- a `<name>` that is the value of a flag (`-m <msg>`, `--cleanup=<mode>`, `-u<mode>`) is ignored:
  it is not an independent positional;
- generic placeholders (`[<options>]`) are filtered out;
- multi-line synopses are handled: an indented CONTINUATION line (e.g. `git tag`) is attached to
  the current form; an `or: ...` line (e.g. `git reset`) starts a new alternative form.

Regression 2026-10-05, found by the quality evaluator on a real server generated from `git`:
several tools (`diff`, `log`, `fetch`, `branch`, `reset`) had a positional marked required
although the command is very often used WITHOUT it (`git log` alone, `git reset --hard HEAD`...).
Root cause: when a command documents several alternative usage forms (`usage: ...` + `or: ...`),
only the FIRST form where a name appeared decided whether it was required. If that form showed it
bare (without brackets), it stayed required even when another, more common form did without it.
A positional is now marked required ONLY if it appears, as required, in ALL the alternative forms:
if it is missing from at least one valid form, there is a way to call the command without it, so
it must be optional.

These tests use real `git <subcommand> -h` outputs captured as fixtures (stable git behaviour),
not arbitrary mocks: it is the only way to check the heuristic against the real format that caused
the bug.
"""
from __future__ import annotations

from mcp_forge.discovery.cli_app import CLIAppDiscovery

# Fixtures: real synopsis lines (git 2.4x), enough for these tests
# since _extract_positional_args only looks at the "usage:"/"or:" block.

_CLONE_HELP = "usage: git clone [<options>] [--] <repo> [<dir>]\n\n    -v, --[no-]verbose    be more verbose\n"
_ADD_HELP = "usage: git add [<options>] [--] <pathspec>...\n\n    -n, --[no-]dry-run    dry run\n"
_MV_HELP = "usage: git mv [<options>] <source>... <destination>\n\n    -v, --[no-]verbose    be verbose\n"
_SWITCH_HELP = "usage: git switch [<options>] [<branch>]\n\n    -c, --[no-]create <branch>\n"
_RESET_HELP = (
    "usage: git reset [--mixed | --soft | --hard | --merge | --keep] [-q] [<commit>]\n"
    "   or: git reset [-q] [<tree-ish>] [--] <pathspec>...\n"
    "   or: git reset [-q] [--pathspec-from-file [--pathspec-file-nul]] [<tree-ish>]\n"
    "   or: git reset --patch [<tree-ish>] [--] [<pathspec>...]\n\n"
    "    -q, --[no-]quiet      be quiet\n"
)
_COMMIT_HELP = (
    "usage: git commit [-a | --interactive | --patch] [-s] [-v] [-u<mode>] [--amend]\n"
    "                  [--dry-run] [(-c | -C | --squash) <commit> | --fixup [(amend|reword):]<commit>)]\n"
    "                  [-F <file> | -m <msg>] [--reset-author] [--allow-empty]\n"
    "                  [--cleanup=<mode>]\n"
    "                  [--] [<pathspec>...]\n\n"
    "    -m, --[no-]message <message>\n"
    "                          commit message\n"
)
_RESTORE_HELP = "usage: git restore [<options>] [--source=<branch>] <file>...\n\n    -s, --[no-]source <tree-ish>\n"
_TAG_HELP = (
    "usage: git tag [-a | -s | -u <key-id>] [-f] [-m <msg> | -F <file>] [-e]\n"
    "               <tagname> [<commit> | <object>]\n"
    "   or: git tag -d <tagname>...\n\n"
    "    -f, --[no-]force      force\n"
)
_NO_USAGE_HELP = "Some tool with no recognizable synopsis format at all.\n\n  --flag   does a thing\n"
_LOG_SHOW_HELP = "usage: git log [<options>] [<revision-range>] [[--] <path>...]\n   or: git show [<options>] <object>...\n"
_FETCH_HELP = (
    "usage: git fetch [<options>] [<repository> [<refspec>...]]\n"
    "   or: git fetch [<options>] <group>\n"
    "   or: git fetch [<options>] --multiple [<options>] [(<repository> | <group>)...]\n"
    "   or: git fetch [<options>] --all [<options>]\n"
)
_BRANCH_HELP = (
    "usage: git branch [<options>] [-r | -a] [--merged] [--no-merged]\n"
    "   or: git branch [<options>] [-f] [--recurse-submodules] <branch-name> [<start-point>]\n"
    "   or: git branch [<options>] [-l] [<pattern>...]\n"
    "   or: git branch [<options>] [-r] (-d | -D) <branch-name>...\n"
    "   or: git branch [<options>] (-m | -M) [<old-branch>] <new-branch>\n"
    "   or: git branch [<options>] (-c | -C) [<old-branch>] <new-branch>\n"
    "   or: git branch [<options>] [-r | -a] [--points-at]\n"
    "   or: git branch [<options>] [-r | -a] [--format]\n"
)


def _names(help_text: str) -> dict[str, bool]:
    return dict(CLIAppDiscovery._extract_positional_args(help_text))


def test_clone_repo_required_dir_optional():
    result = _names(_CLONE_HELP)
    assert result == {"repo": True, "dir": False}


def test_add_pathspec_required():
    assert _names(_ADD_HELP) == {"pathspec": True}


def test_mv_source_and_destination_both_required():
    assert _names(_MV_HELP) == {"source": True, "destination": True}


def test_switch_branch_optional_per_gits_own_synopsis():
    assert _names(_SWITCH_HELP) == {"branch": False}


def test_reset_pathspec_optional_since_first_form_has_no_pathspec_at_all():
    """2026-10-05, a regression found by the quality evaluator on a real server generated from
    `git`: `pathspec` was marked required because the original logic only looked at the FIRST
    form where a name appeared. But the first form of `git reset` (`git reset [...] [<commit>]`,
    e.g. `git reset --hard HEAD`) has NO pathspec, and it is the most common use. pathspec must
    therefore be optional: there is a perfectly valid way to call `git reset` without it."""
    result = _names(_RESET_HELP)
    assert result.get("pathspec") is False


def test_commit_flag_values_never_become_positional_args():
    """<msg> (value of -m), <mode> (value of -u<mode> and --cleanup=<mode>), <commit> (value of
    --fixup) must NEVER appear: they are flag values, not independent positionals."""
    result = _names(_COMMIT_HELP)
    assert "msg" not in result
    assert "mode" not in result
    # <pathspec> at the very end, outside any flag, optional (inside [<pathspec>...])
    assert result.get("pathspec") is False


def test_restore_file_required_even_after_flag_with_inline_value():
    """--source=<branch> already takes its value inline (with =); the <file> that follows is an
    independent positional, not a second value of the same flag."""
    assert _names(_RESTORE_HELP) == {"file": True}


def test_tag_finds_tagname_on_continuation_line():
    """tagname appears on a CONTINUATION line (indented, without a 'usage:' or 'or:' prefix): it
    must still be attached to the same synopsis as the preceding 'usage:' line (not a separate
    form).

    2026-10-05, updated with the cross-form aggregation fix: tagname is found as an independent,
    required positional in the first form (`usage: git tag [...] <tagname> [...]`), but treated as
    the value of `-d` in the second (`or: git tag -d <tagname>...`): it does not appear
    consistently in every form. The result is optional, which is semantically right anyway:
    `git tag` alone (no argument, list mode) is a valid use."""
    result = _names(_TAG_HELP)
    assert "tagname" in result
    assert result.get("tagname") is False


def test_no_recognizable_usage_line_returns_empty_list():
    """Silent degradation: if the format does not follow the usage:/<name> convention, invent
    nothing rather than produce noise."""
    assert CLIAppDiscovery._extract_positional_args(_NO_USAGE_HELP) == []


def test_generic_placeholder_words_are_filtered():
    help_text = "usage: mytool [<options>] <realarg>\n\n  -v  verbose\n"
    assert _names(help_text) == {"realarg": True}


# ---------------------------------------------------------------------------
# Regression 2026-10-05: real "major" bugs reported by the quality evaluator
# on an MCP server generated from `git`: several commands had a positional
# marked required while one usage form, among several documented
# alternatives ("usage: ..." + "or: ..."), does entirely without it.
# Fixtures = real captured `git <subcommand> -h` outputs
# (stable git behaviour), like the rest of this file.
# ---------------------------------------------------------------------------

def test_log_revision_range_and_path_optional_not_required():
    """`git log` alone (no range nor path) is the most common use. Old bug: these two names were in
    a synopsis where they are already optional (`[...]`), so this exact case already passed before
    the fix."""
    result = _names(_LOG_SHOW_HELP)
    assert result.get("revision_range") is False
    assert result.get("path") is False


def test_log_does_not_inherit_show_s_required_object():
    """`object` appears ONLY in the alternative form `or: git show [<options>] <object>...`, not in
    the `git log` form itself. Since it does not appear in ALL the forms of the shared synopsis, it
    must be optional (one valid form, `git log`, does not need it), not inherited as required from
    the `show` alternative."""
    result = _names(_LOG_SHOW_HELP)
    assert result.get("object") is False


def test_fetch_group_optional_since_default_remote_form_has_none():
    """Real bug reported by the evaluator: `group` was required. The very first form
    (`git fetch [<options>] [<repository> [<refspec>...]]`, fetching the default remote) has no
    `group` at all: it must be optional."""
    result = _names(_FETCH_HELP)
    assert result.get("group") is False
    assert result.get("repository") is False


def test_branch_new_branch_optional_since_list_form_has_none():
    """Real bug reported by the evaluator: `new_branch` (renaming a branch) was required, which
    prevented `git branch` alone (listing branches, the first form of the synopsis, which has no
    positional)."""
    result = _names(_BRANCH_HELP)
    assert result.get("new_branch") is False
    assert result.get("branch_name") is False
