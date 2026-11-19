"""
Wide coverage: discovery/cli_app.py on real `--help`/`-h` outputs of very common CLI tools, beyond
`git` alone, which motivated the fixes of this series (see test_cli_discovery_positional_args.py
and test_cli_discovery_option_parsing.py for git itself).

Goal: prove that the detection heuristic (positionals and options) is really generic, not
accidentally tuned to git's formatting habits, by testing it against several distinct families of
conventions:

  - GNU coreutils (grep, sort, tar, sed): `PATTERN [FILE]...` synopsis in bare CAPITALS, classic
    `-x, --xxx  description` option list.
  - curl: `<url>` synopsis in lowercase angle brackets, compact options at a single indentation
    level.
  - npm: `[<package-spec> ...]` synopsis on a line separate from "Usage:", options section as a
    compact list of brackets (not one per line, so no individual option is extracted, and that is
    the expected behaviour: no false detection rather than an invented one).

All the fixtures below are excerpts of real outputs captured locally (`curl --help`,
`grep --help`, etc.), not invented texts: it is the only way to check the heuristic against the
format that really caused the original bug.
"""
from __future__ import annotations

from mcp_forge.discovery.cli_app import CLIAppDiscovery
from mcp_forge.models import ForgeConfig, ForgeMode, NameStyle, SourceType


def _discovery() -> CLIAppDiscovery:
    config = ForgeConfig(source="tool", mode=ForgeMode.AUTO, output_dir="./out",
                          source_type=SourceType.CLI_APP, name_style=NameStyle.SHORT)
    return CLIAppDiscovery(config)


def _positional_names(help_text: str) -> dict[str, bool]:
    return dict(CLIAppDiscovery._extract_positional_args(help_text))


def _option_names(help_text: str) -> set[str]:
    """Names of the `-x`/`--xxx` flags only (excludes the positional arguments, which
    `_parse_options` returns in the same list)."""
    opts, _ = _discovery()._parse_options(help_text)
    return {p.name for p in opts if p.param_in != "positional"}


# ---------------------------------------------------------------------------
# curl: <name> convention, compact options with a 1-space indentation
# ---------------------------------------------------------------------------

_CURL_HELP = """\
Usage: curl [options...] <url>
 -d, --data <data>          HTTP POST data
 -f, --fail                 Fail fast with no output on HTTP errors
 -h, --help <category>      Get help for commands
 -i, --include              Include protocol response headers in the output
 -o, --output <file>        Write to file instead of stdout
 -O, --remote-name          Write output to a file named as the remote file
 -s, --silent               Silent mode
 -T, --upload-file <file>   Transfer local FILE to destination
 -u, --user <user:password> Server user and password
 -A, --user-agent <name>    Send User-Agent <name> to server
 -v, --verbose              Make the operation more talkative
 -V, --version              Show version number and quit

This is not the full help, this menu is stripped into categories.
"""


def test_curl_url_is_required_positional():
    assert _positional_names(_CURL_HELP) == {"url": True}


def test_curl_combined_short_long_flags_use_long_name():
    names = _option_names(_CURL_HELP)
    assert {"data", "fail", "output", "verbose", "version"} <= names
    # never the short letters alone
    assert not ({"d", "f", "o", "v"} & names)


# ---------------------------------------------------------------------------
# grep — convention GNU : MAJUSCULES nues (PATTERN, FILE)
# ---------------------------------------------------------------------------

_GREP_HELP = """\
Usage: grep [OPTION]... PATTERN [FILE]...
Search for PATTERN in each FILE or standard input.
PATTERN is, by default, a basic regular expression (BRE).
Example: grep -i 'hello world' menu.h main.c

Regexp selection and interpretation:
  -E, --extended-regexp     PATTERN is an extended regular expression (ERE)
  -F, --fixed-strings       PATTERN is a set of newline-separated strings
  -e, --regexp=PATTERN      use PATTERN for matching
  -i, --ignore-case         ignore case distinctions
  -w, --word-regexp         force PATTERN to match only whole words
  -x, --line-regexp         force PATTERN to match only whole lines

Miscellaneous:
  -s, --no-messages         suppress error messages
  -v, --invert-match        select non-matching lines
"""


def test_grep_pattern_required_file_optional():
    assert _positional_names(_GREP_HELP) == {"pattern": True, "file": False}


def test_grep_prose_description_after_usage_not_mistaken_for_synopsis():
    """"Search for PATTERN..." and "PATTERN is, by default... (BRE)." are not indented: they are
    description sentences, not a continuation of the synopsis. "BRE" must not appear as a
    positional."""
    names = _positional_names(_GREP_HELP)
    assert "bre" not in names
    assert len(names) == 2


def test_grep_boolean_and_valued_flags_detected():
    names = _option_names(_GREP_HELP)
    assert {"extended_regexp", "fixed_strings", "ignore_case",
            "word_regexp", "line_regexp", "no_messages", "invert_match"} <= names


# ---------------------------------------------------------------------------
# sort: two synopsis lines ("usage:" + "or:"), bare CAPITALS
# ---------------------------------------------------------------------------

_SORT_HELP = """\
Usage: sort [OPTION]... [FILE]...
  or:  sort [OPTION]... --files0-from=F
Write sorted concatenation of all FILE(s) to standard output.

With no FILE, or when FILE is -, read standard input.

Ordering options:

  -b, --ignore-leading-blanks  ignore leading blanks
  -d, --dictionary-order      consider only blanks and alphanumeric characters
  -f, --ignore-case           fold lower case to upper case characters
  -r, --reverse               reverse the result of comparisons
"""


def test_sort_file_optional_positional_from_first_synopsis_line():
    assert _positional_names(_SORT_HELP) == {"file": False}


def test_sort_options_detected():
    names = _option_names(_SORT_HELP)
    assert {"ignore_leading_blanks", "dictionary_order", "ignore_case", "reverse"} <= names


# ---------------------------------------------------------------------------
# tar: multi-line prose preamble before the options, several aliases
# ---------------------------------------------------------------------------

_TAR_HELP = """\
Usage: tar [OPTION...] [FILE]...
GNU 'tar' saves many files together into a single tape or disk archive, and can
restore individual files from the archive.

Examples:
  tar -cf archive.tar foo bar  # Create archive.tar from files foo and bar.

 Main operation mode:
  -c, --create               create a new archive
      --delete               delete from the archive (not on mag tapes!)
  -t, --list                 list the contents of an archive
  -u, --update               only append files newer than copy in archive
  -x, --extract, --get       extract files from an archive
"""


def test_tar_file_optional_positional():
    assert _positional_names(_TAR_HELP) == {"file": False}


def test_tar_long_only_flag_without_short_form_detected():
    """`--delete` has no short form at all: it must still be detected (not only the combined
    `-x, --xxx` entries)."""
    names = _option_names(_TAR_HELP)
    assert {"create", "delete", "list", "update"} <= names


# ---------------------------------------------------------------------------
# sed: option entries ALWAYS on 2 lines (flag, then the description
# indented below), the most demanding format for joining lines
# ---------------------------------------------------------------------------

_SED_HELP = """\
Usage: sed [OPTION]... {script-only-if-no-other-script} [input-file]...

  -n, --quiet, --silent
                 suppress automatic printing of pattern space
      --debug
                 annotate program execution
  --follow-symlinks
                 follow symlinks when processing in place
  -b, --binary
                 open files in binary mode (CR+LFs are not processed specially)
  --posix
                 disable all GNU extensions.
"""


def test_sed_two_line_entries_all_detected():
    """Every sed option has its description on the NEXT line: the most systematic case of this
    format, not an isolated exception. Note: "-n, --quiet, --silent" (3 aliases) keeps only the
    last one ("silent"), a known and accepted limit rather than losing the whole entry."""
    names = _option_names(_SED_HELP)
    assert {"silent", "debug", "follow_symlinks", "binary", "posix"} <= names


def test_sed_positional_uses_a_convention_not_covered_by_this_heuristic():
    """`{script-only-if-no-other-script} [input-file]...` uses lowercase hyphenated words, without
    `<>` or CAPITALS: a third convention this heuristic does not claim to cover (see the module
    docstring). It documents the limit rather than hoping for a result it cannot produce: empty
    list, no false positive."""
    assert _positional_names(_SED_HELP) == {}


# ---------------------------------------------------------------------------
# npm: synopsis on a line separate from "Usage:", options section as a
# compact list of brackets (not one per line)
# ---------------------------------------------------------------------------

_NPM_HELP = """\
Install a package

Usage:
npm install [<package-spec> ...]

Options:
[-S|--save|--no-save|--save-prod|--save-dev|--save-optional|--save-peer|--save-bundle]
[-E|--save-exact] [-g|--global]

aliases: add, i, in, ins, inst, insta, instal, isnt, isnta, isntal, isntall
"""


def test_npm_package_spec_optional_positional_on_line_after_bare_usage():
    """"Usage:" is alone on its line; the real content follows, not indented: it must still be
    recognised as the synopsis (not as prose)."""
    assert _positional_names(_NPM_HELP) == {"package_spec": False}


def test_npm_compact_bracket_options_produce_no_false_positive():
    """npm's Options: section lists the flags in a heap between brackets, not one line per option:
    the parser must invent NOTHING rather than guess option names from a format it does not
    understand."""
    names = _option_names(_NPM_HELP)
    assert names == set()


# ---------------------------------------------------------------------------
# Heterogeneous / unconventional formats: no crash, silent degradation
# (empty list) rather than invented noise.
# ---------------------------------------------------------------------------

_UNZIP_HELP = """\
UnZip 6.00 of 20 April 2009, by Info-ZIP.  Maintained by C. Spieler.

Usage: unzip [-Z] [-opts[modifiers]] file[.zip] [list] [-x xlist] [-d exdir]
  Default action is to extract files in list, except those in xlist, to exdir.

  -p  extract files to pipe, no messages     -l  list files (short format)
  -f  freshen existing files, create none    -t  test compressed archive data
"""

_OPENSSL_VERSION_HELP = """\
Usage: version [options]

General options:
 -help  Display this summary

Output options:
 -a     Show all data
 -b     Show build date
"""

_FIND_HELP = """\
Usage: find [-H] [-L] [-P] [-Olevel] [-D debugopts] [path...] [expression]

Default path is the current directory; default expression is -print.
"""


def test_heterogeneous_formats_never_raise():
    for text in (_UNZIP_HELP, _OPENSSL_VERSION_HELP, _FIND_HELP):
        # Must never raise, whatever the format.
        _positional_names(text)
        _option_names(text)


def test_find_lowercase_bracketed_words_not_falsely_captured_as_positional():
    """find uses `[path...]`/`[expression]` (lowercase, without <>): a convention the heuristic
    does not claim to cover. It must not invent a wrong result from `-Olevel` or `debugopts`
    either."""
    names = _positional_names(_FIND_HELP)
    assert "olevel" not in names
    assert "debugopts" not in names
