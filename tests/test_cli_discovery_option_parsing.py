"""
Regression 2026-09-30 (continued), discovery/cli_app.py: option parsing.

Bugs found while digging into the "commit -m message missing" limit first reported:

1. The git idiom `--[no-]xxx` (a bool/value flag documented in a single entry, e.g.
   `--[no-]verbose`) made the flag completely invisible: the literal brackets broke
   `--[a-z][a-z0-9_-]*`. This affected almost every boolean flag of git (`--[no-]verbose`,
   `--[no-]bare`, `--[no-]mirror`...), not just one isolated case.
2. `-x, --xxx` (short and long forms combined, THE most common format in git/GNU style CLIs) was
   entirely rejected by the name extraction: the code only handled `--xxx` alone or `-x` alone.
3. Option entries spread over 2 lines (flag and value on one line, description on the next, more
   indented, e.g. `-m, --[no-]message <message>` then `commit message` on the following line)
   were never joined, so never detected by the single-line parser.

Together, these bugs explained why `git commit` had no `message` parameter even though
`-m, --[no-]message <message>` is documented.
"""
from __future__ import annotations

from mcp_forge.discovery.cli_app import CLIAppDiscovery
from mcp_forge.models import ForgeConfig, ForgeMode, NameStyle, SourceType


def _parse(help_text: str):
    config = ForgeConfig(source="tool", mode=ForgeMode.AUTO, output_dir="./out",
                          source_type=SourceType.CLI_APP, name_style=NameStyle.SHORT)
    disc = CLIAppDiscovery(config)
    return disc._parse_options(help_text)


def test_bracket_no_toggle_idiom_is_detected_as_a_plain_flag():
    help_text = "usage: tool [<options>]\n\n    --[no-]verbose    be more verbose\n"
    params, _ = _parse(help_text)
    names = {p.name for p in params}
    assert "verbose" in names


def test_combined_short_and_long_flag_uses_long_form_name():
    help_text = "usage: tool [<options>]\n\n    -v, --verbose    be more verbose\n"
    params, _ = _parse(help_text)
    names = {p.name for p in params}
    assert "verbose" in names
    assert "v" not in names


def test_short_only_flag_reconstructs_single_dash_override():
    """A purely short flag (no long form) must be recalled with a single dash (-x), not "--x"."""
    help_text = "usage: tool [<options>]\n\n    -x    do the x thing\n"
    params, flags = _parse(help_text)
    assert flags.get("x") == "-x"


def test_two_line_option_entry_is_merged_and_detected():
    """Reproduces exactly the real case of `git commit -h`:
    "-m, --[no-]message <message>" on one line, the description
    ("commit message") indented on the next line."""
    help_text = (
        "usage: tool [<options>]\n\n"
        "    -m, --[no-]message <message>\n"
        "                          commit message\n"
    )
    params, _ = _parse(help_text)
    msg = next((p for p in params if p.name == "message"), None)
    assert msg is not None
    assert msg.description == "commit message"


def test_description_less_flag_does_not_swallow_the_next_option_line():
    """Subtle regression of the old pattern: `\\s{2,}` includes the line break, so a flag WITHOUT
    a description on its own line could "swallow" the whole next line (another full option) as if
    it were its description, and that second option simply disappeared. `--alpha` without a
    description is still not captured itself (an existing limit, out of scope here), but `--beta`
    must no longer disappear because of it."""
    help_text = (
        "usage: tool [<options>]\n\n"
        "    --alpha\n"
        "    --beta    the beta flag\n"
    )
    params, _ = _parse(help_text)
    names = {p.name for p in params}
    assert "beta" in names


def test_angle_bracket_value_hint_treated_as_optional_flag_value():
    """A flag with a `<name>` value (git convention) must stay an OPTIONAL value (the flag itself
    stays optional), not become a required parameter of the MCP tool."""
    help_text = "usage: tool [<options>]\n\n    --author <author>    override author\n"
    params, _ = _parse(help_text)
    author = next(p for p in params if p.name == "author")
    assert author.required is False


def test_bare_allcaps_value_hint_is_an_optional_flag_too():
    """A bare ALLCAPS hint ("--output FILE") means the value is required when the flag is given,
    not that the flag is: the parameter of the MCP tool stays optional. Before, every call of the
    generated tool demanded it."""
    help_text = "usage: tool [<options>]\n\n    --output FILE    write to FILE\n"
    params, _ = _parse(help_text)
    output = next(p for p in params if p.name == "output")
    assert output.required is False
    assert output.type.value == "string"  # the flag still takes a value (not a switch)


def test_usage_synopsis_flags_are_not_mistaken_for_option_entries():
    """A flag that appears in an "or: ..." synopsis line (not in the option list) must not be
    captured as a real option."""
    help_text = (
        "usage: tool [<options>] [<path>...]\n"
        "   or: tool [<options>] --cached [<commit>]\n\n"
        "    -v, --verbose    be more verbose\n"
    )
    params, _ = _parse(help_text)
    names = {p.name for p in params}
    assert "cached" not in names
    assert "verbose" in names


def test_real_git_commit_help_produces_message_param():
    """End-to-end reproduction with the real help text of `git commit -h` (excerpt): the original
    bug reported by the user."""
    help_text = (
        "usage: git commit [-a | --interactive | --patch] [-s] [-v] [-u<mode>] [--amend]\n"
        "                  [--dry-run] [(-c | -C | --squash) <commit> | --fixup [(amend|reword):]<commit>)]\n"
        "                  [-F <file> | -m <msg>] [--reset-author] [--allow-empty]\n"
        "                  [--] [<pathspec>...]\n\n"
        "    -m, --[no-]message <message>\n"
        "                          commit message\n"
        "    -a, --[no-]all        commit all changed files\n"
    )
    params, _ = _parse(help_text)
    names = {p.name for p in params}
    assert "message" in names
    assert "all" in names
