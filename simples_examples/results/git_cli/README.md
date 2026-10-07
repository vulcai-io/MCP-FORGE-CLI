# CLI tool example

**Source:** `git`

**Score:** 8.4/10 (22 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates CLI wrapping: mcp-forge inspects `git --help` and its subcommands to generate tools that invoke the real `git` binary via subprocess, with flags and positional arguments inferred automatically.

---

Enables version control workflows by executing core Git subcommands for repository management, including initializing projects, staging changes, committing history, and handling branches and remotes.

Généré par **mcp-forge**.

## Installation

```bash
pip install -r requirements.txt
```

## Lancement

```bash
python server.py
```

## Test avec MCP Inspector

```bash
mcp dev server.py
```

## Tools disponibles (22)

### `clone`

Clone a repository into a new directory

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `repo` | `str` | yes | Positional argument: repo |
| `dir` | `str | None` | no | Positional argument: dir |
| `verbose` | `bool | None` | no | be more verbose |
| `quiet` | `bool | None` | no | be more quiet |
| `progress` | `bool | None` | no | force progress reporting |
| `no_checkout` | `bool | None` | no | don't create a checkout |
| `checkout` | `bool | None` | no | opposite of --no-checkout |
| `bare` | `bool | None` | no | create a bare repository |
| `mirror` | `bool | None` | no | create a mirror repository (implies bare) |
| `local` | `bool | None` | no | to clone from a local repository |
| `no_hardlinks` | `bool | None` | no | don't use local hardlinks, always copy |
| `hardlinks` | `bool | None` | no | opposite of --no-hardlinks |
| `shared` | `bool | None` | no | setup as shared repository |
| `jobs` | `int | None` | no | number of submodules cloned in parallel |
| `template` | `str | None` | no | directory from which templates will be used |
| `reference` | `str | None` | no | reference repository |
| `reference_if_able` | `str | None` | no | reference repository |
| `dissociate` | `bool | None` | no | use --reference only while cloning |
| `origin` | `str | None` | no | use <name> instead of 'origin' to track upstream |
| `branch` | `str | None` | no | checkout <branch> instead of the remote's HEAD |
| `upload_pack` | `str | None` | no | path to git-upload-pack on the remote |
| `depth` | `str | None` | no | create a shallow clone of that depth |
| `shallow_since` | `str | None` | no | create a shallow clone since a specific time |
| `shallow_exclude` | `str | None` | no | deepen history of shallow clone, excluding rev |
| `single_branch` | `bool | None` | no | clone only one branch, HEAD or --branch |
| `no_tags` | `bool | None` | no | don't clone any tags, and make later fetches not to follow them |
| `tags` | `bool | None` | no | opposite of --no-tags |
| `shallow_submodules` | `bool | None` | no | any cloned submodules will be shallow |
| `separate_git_dir` | `str | None` | no | separate git dir from working tree |
| `server_option` | `str | None` | no | option to transmit |
| `ipv4` | `bool | None` | no | use IPv4 addresses only |
| `ipv6` | `bool | None` | no | use IPv6 addresses only |
| `filter` | `str | None` | no | object filtering |
| `also_filter_submodules` | `bool | None` | no | apply partial clone filters to submodules |
| `remote_submodules` | `bool | None` | no | any cloned submodules will use their remote-tracking branch |
| `sparse` | `bool | None` | no | initialize sparse-checkout file to include only files at root |
| `bundle_uri` | `str | None` | no | a URI for downloading bundles before fetching from origin remote |
---
### `init`

[--separate-git-dir <git-dir>] [--object-format=<format>] [-b <branch-name> | --initial-branch=<branch-name>] [--shared[=<permissions>]] [<directory>]

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `directory` | `str | None` | no | Positional argument: directory |
| `quiet` | `bool | None` | no | be quiet |
| `separate_git_dir` | `str | None` | no | separate git dir from working tree |
| `initial_branch` | `str | None` | no | override the name of the initial branch |
| `object_format` | `str | None` | no | specify the hash algorithm to use |
---
### `add`

Add file contents to the index

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `pathspec` | `str` | yes | Positional argument: pathspec |
| `dry_run` | `bool | None` | no | dry run |
| `verbose` | `bool | None` | no | be verbose |
| `interactive` | `bool | None` | no | interactive picking |
| `patch` | `bool | None` | no | select hunks interactively |
| `edit` | `bool | None` | no | edit current diff and apply |
| `force` | `bool | None` | no | allow adding otherwise ignored files |
| `update` | `bool | None` | no | update tracked files |
| `renormalize` | `bool | None` | no | renormalize EOL of tracked files (implies -u) |
| `intent_to_add` | `bool | None` | no | record only the fact that the path will be added later |
| `all` | `bool | None` | no | add changes from all tracked and untracked files |
| `refresh` | `bool | None` | no | don't add, only refresh the index |
| `ignore_errors` | `bool | None` | no | just skip files which cannot be added because of errors |
| `sparse` | `bool | None` | no | allow updating entries outside of the sparse-checkout cone |
| `pathspec_from_file` | `str | None` | no | read pathspec from file |
| `pathspec_file_nul` | `bool | None` | no | with --pathspec-from-file, pathspec elements are separated with NUL character |
---
### `mv`

Move or rename a file, a directory, or a symlink

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `source` | `str` | yes | Positional argument: source |
| `destination` | `str` | yes | Positional argument: destination |
| `verbose` | `bool | None` | no | be verbose |
| `dry_run` | `bool | None` | no | dry run |
| `force` | `bool | None` | no | force move/rename even if target exists |
| `k` | `bool | None` | no | skip move/rename errors |
| `sparse` | `bool | None` | no | allow updating entries outside of the sparse-checkout cone |
---
### `restore`

Restore working tree files

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `file` | `str` | yes | Positional argument: file |
| `source` | `str | None` | no | which tree-ish to checkout from |
| `staged` | `bool | None` | no | restore the index |
| `worktree` | `bool | None` | no | restore the working tree (default) |
| `ignore_unmerged` | `bool | None` | no | ignore unmerged entries |
| `overlay` | `bool | None` | no | use overlay mode |
| `quiet` | `bool | None` | no | suppress progress reporting |
| `progress` | `bool | None` | no | force progress reporting |
| `merge` | `bool | None` | no | perform a 3-way merge with the new branch |
| `conflict` | `str | None` | no | conflict style (merge, diff3, or zdiff3) |
| `ours` | `bool | None` | no | checkout our version for unmerged files |
| `theirs` | `bool | None` | no | checkout their version for unmerged files |
| `patch` | `bool | None` | no | select hunks interactively |
| `ignore_skip_worktree_bits` | `bool | None` | no | do not limit pathspecs to sparse entries only |
| `pathspec_from_file` | `str | None` | no | read pathspec from file |
| `pathspec_file_nul` | `bool | None` | no | with --pathspec-from-file, pathspec elements are separated with NUL character |
---
### `rm`

[--quiet] [--pathspec-from-file=<file> [--pathspec-file-nul]] [--] [<pathspec>...]

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `pathspec` | `str | None` | no | Positional argument: pathspec |
| `dry_run` | `bool | None` | no | dry run |
| `quiet` | `bool | None` | no | do not list removed files |
| `cached` | `bool | None` | no | only remove from the index |
| `force` | `bool | None` | no | override the up-to-date check |
| `r` | `bool | None` | no | allow recursive removal |
| `sparse` | `bool | None` | no | allow updating entries outside of the sparse-checkout cone |
| `pathspec_from_file` | `str | None` | no | read pathspec from file |
| `pathspec_file_nul` | `bool | None` | no | with --pathspec-from-file, pathspec elements are separated with NUL character |
---
### `bisect`

or: git bisect (good|bad) [<rev>...] or: git bisect terms [--term-good | --term-bad] or: git bisect skip [(<rev>|<range>)...] or: git bisect next or: git bisect reset [<commit>] or: git bisect visualize or: git bisect replay <logfile> or: git bisect log or: git bisect run <cmd> [<arg>...]

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `bad` | `str | None` | no | Positional argument: bad |
| `good` | `str | None` | no | Positional argument: good |
| `pathspec` | `str | None` | no | Positional argument: pathspec |
| `rev` | `str | None` | no | Positional argument: rev |
| `commit` | `str | None` | no | Positional argument: commit |
| `logfile` | `str | None` | no | Positional argument: logfile |
| `cmd` | `str | None` | no | Positional argument: cmd |
---
### `diff`

or: git diff [<options>] --cached [--merge-base] [<commit>] [--] [<path>...] or: git diff [<options>] [--merge-base] <commit> [<commit>...] <commit> [--] [<path>...] or: git diff [<options>] <commit>...<commit> [--] [<path>...] or: git diff [<options>] <blob> <blob> or: git diff [<options>] --no-index [--] <path> <path> common diff options:

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `commit` | `str | None` | no | Positional argument: commit |
| `path` | `str | None` | no | Positional argument: path |
| `blob` | `str | None` | no | Positional argument: blob |
| `z` | `bool | None` | no | output diff-raw with lines terminated with NUL. |
| `p` | `bool | None` | no | output patch format. |
| `u` | `bool | None` | no | synonym for -p. |
| `patch_with_raw` | `bool | None` | no | output both a patch and the diff-raw format. |
| `stat` | `bool | None` | no | show diffstat instead of patch. |
| `numstat` | `bool | None` | no | show numeric diffstat instead of patch. |
| `patch_with_stat` | `bool | None` | no | output a patch and prepend its diffstat. |
| `name_only` | `bool | None` | no | show only names of changed files. |
| `full_index` | `bool | None` | no | show full object name on index lines. |
| `R` | `bool | None` | no | swap input file pairs. |
| `B` | `bool | None` | no | detect complete rewrites. |
| `M` | `bool | None` | no | detect renames. |
| `C` | `bool | None` | no | detect copies. |
| `find_copies_harder` | `bool | None` | no | try unchanged files as candidate for copy detection. |
| `pickaxe_all` | `bool | None` | no | show all files diff when -S is used and hit is found. |
| `a` | `bool | None` | no | --text    treat all files as text. |
---
### `grep`

Print lines matching a pattern

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `pattern` | `str` | yes | Positional argument: pattern |
| `rev` | `str | None` | no | Positional argument: rev |
| `path` | `str | None` | no | Positional argument: path |
| `no_index` | `bool | None` | no | find in contents not managed by git |
| `index` | `bool | None` | no | opposite of --no-index |
| `untracked` | `bool | None` | no | search in both tracked and untracked files |
| `exclude_standard` | `bool | None` | no | ignore files specified via '.gitignore' |
| `recurse_submodules` | `bool | None` | no | recursively search in each submodule |
| `invert_match` | `bool | None` | no | show non-matching lines |
| `ignore_case` | `bool | None` | no | case insensitive matching |
| `word_regexp` | `bool | None` | no | match patterns only at word boundaries |
| `text` | `bool | None` | no | process binary files as text |
| `I` | `bool | None` | no | don't match patterns in binary files |
| `textconv` | `bool | None` | no | process binary files with textconv filters |
| `recursive` | `bool | None` | no | search in subdirectories (default) |
| `max_depth` | `int | None` | no | descend at most <n> levels |
| `extended_regexp` | `bool | None` | no | use extended POSIX regular expressions |
| `basic_regexp` | `bool | None` | no | use basic POSIX regular expressions (default) |
| `fixed_strings` | `bool | None` | no | interpret patterns as fixed strings |
| `perl_regexp` | `bool | None` | no | use Perl-compatible regular expressions |
| `line_number` | `bool | None` | no | show line numbers |
| `column` | `bool | None` | no | show column number of first match |
| `h` | `bool | None` | no | don't show filenames |
| `H` | `bool | None` | no | show filenames |
| `full_name` | `bool | None` | no | show filenames relative to top directory |
| `files_with_matches` | `bool | None` | no | show only filenames instead of matching lines |
| `name_only` | `bool | None` | no | synonym for --files-with-matches |
| `files_without_match` | `bool | None` | no | show only the names of files without match |
| `null` | `bool | None` | no | print NUL after filenames |
| `only_matching` | `bool | None` | no | show only matching parts of a line |
| `count` | `bool | None` | no | show the number of matches instead of matching lines |
| `break_` | `bool | None` | no | print empty line between matches from different files |
| `heading` | `bool | None` | no | show filename only once above matches from same file |
| `context` | `int | None` | no | show <n> context lines before and after matches |
| `before_context` | `int | None` | no | show <n> context lines before matches |
| `after_context` | `int | None` | no | show <n> context lines after matches |
| `threads` | `int | None` | no | use <n> worker threads |
| `show_function` | `bool | None` | no | show a line with the function name before matches |
| `function_context` | `bool | None` | no | show the surrounding function |
| `f` | `str | None` | no | read patterns from file |
| `e` | `str | None` | no | match <pattern> |
| `and_` | `bool | None` | no | combine patterns specified with -e |
| `quiet` | `bool | None` | no | indicate hit with exit status without output |
| `all_match` | `bool | None` | no | show only matches from files that match all patterns |
| `ext_grep` | `bool | None` | no | allow calling of grep(1) (ignored by this build) |
| `max_count` | `int | None` | no | maximum number of results per file |
---
### `log`

or: git show [<options>] <object>...

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `revision_range` | `str | None` | no | Positional argument: revision_range |
| `path` | `str | None` | no | Positional argument: path |
| `object` | `str | None` | no | Positional argument: object |
| `quiet` | `bool | None` | no | suppress diff output |
| `source` | `bool | None` | no | show source |
| `use_mailmap` | `bool | None` | no | use mail map file |
| `mailmap` | `bool | None` | no | alias of --use-mailmap |
| `clear_decorations` | `bool | None` | no | clear all previously-defined decoration filters |
| `decorate_refs` | `str | None` | no | only decorate refs that match <pattern> |
| `decorate_refs_exclude` | `str | None` | no | do not decorate refs that match <pattern> |
---
### `show`

or: git show [<options>] <object>...

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `revision_range` | `str | None` | no | Positional argument: revision_range |
| `path` | `str | None` | no | Positional argument: path |
| `object` | `str | None` | no | Positional argument: object |
| `quiet` | `bool | None` | no | suppress diff output |
| `source` | `bool | None` | no | show source |
| `use_mailmap` | `bool | None` | no | use mail map file |
| `mailmap` | `bool | None` | no | alias of --use-mailmap |
| `clear_decorations` | `bool | None` | no | clear all previously-defined decoration filters |
| `decorate_refs` | `str | None` | no | only decorate refs that match <pattern> |
| `decorate_refs_exclude` | `str | None` | no | do not decorate refs that match <pattern> |
---
### `status`

Show the working tree status

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `pathspec` | `str | None` | no | Positional argument: pathspec |
| `verbose` | `bool | None` | no | be verbose |
| `short` | `bool | None` | no | show status concisely |
| `branch` | `bool | None` | no | show branch information |
| `show_stash` | `bool | None` | no | show stash information |
| `ahead_behind` | `bool | None` | no | compute full ahead/behind values |
| `long` | `bool | None` | no | show status in long format (default) |
| `null` | `bool | None` | no | terminate entries with NUL |
| `no_renames` | `bool | None` | no | do not detect renames |
| `renames` | `bool | None` | no | opposite of --no-renames |
---
### `branch`

or: git branch [<options>] [-f] [--recurse-submodules] <branch-name> [<start-point>] or: git branch [<options>] [-l] [<pattern>...] or: git branch [<options>] [-r] (-d | -D) <branch-name>... or: git branch [<options>] (-m | -M) [<old-branch>] <new-branch> or: git branch [<options>] (-c | -C) [<old-branch>] <new-branch> or: git branch [<options>] [-r | -a] [--points-at] or: git branch [<options>] [-r | -a] [--format] Generic options

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `branch_name` | `str | None` | no | Positional argument: branch_name |
| `start_point` | `str | None` | no | Positional argument: start_point |
| `pattern` | `str | None` | no | Positional argument: pattern |
| `new_branch` | `str | None` | no | Positional argument: new_branch |
| `verbose` | `bool | None` | no | show hash and subject, give twice for upstream branch |
| `quiet` | `bool | None` | no | suppress informational messages |
| `set_upstream_to` | `str | None` | no | change the upstream info |
| `remotes` | `bool | None` | no | act on remote-tracking branches |
| `contains` | `str | None` | no | print only branches that contain the commit |
| `no_contains` | `str | None` | no | print only branches that don't contain the commit |
| `all` | `bool | None` | no | list both remote-tracking and local branches |
| `delete` | `bool | None` | no | delete fully merged branch |
| `D` | `bool | None` | no | delete branch (even if not merged) |
| `move` | `bool | None` | no | move/rename a branch and its reflog |
| `M` | `bool | None` | no | move/rename a branch, even if target exists |
| `omit_empty` | `bool | None` | no | do not output a newline after empty formatted refs |
| `copy` | `bool | None` | no | copy a branch and its reflog |
| `C` | `bool | None` | no | copy a branch, even if target exists |
| `list` | `bool | None` | no | list branch names |
| `show_current` | `bool | None` | no | show current branch name |
| `create_reflog` | `bool | None` | no | create the branch's reflog |
| `edit_description` | `bool | None` | no | edit the description for the branch |
| `force` | `bool | None` | no | force creation, move/rename, deletion |
| `merged` | `str | None` | no | print only branches that are merged |
| `no_merged` | `str | None` | no | print only branches that are not merged |
| `sort` | `str | None` | no | field name to sort on |
| `points_at` | `str | None` | no | print only branches of the object |
| `ignore_case` | `bool | None` | no | sorting and filtering are case insensitive |
| `recurse_submodules` | `bool | None` | no | recurse through submodules |
| `format` | `str | None` | no | format to use for the output |
---
### `commit`

[--dry-run] [(-c | -C | --squash) <commit> | --fixup [(amend|reword):]<commit>)] [-F <file> | -m <msg>] [--reset-author] [--allow-empty] [--allow-empty-message] [--no-verify] [-e] [--author=<author>] [--date=<date>] [--cleanup=<mode>] [--[no-]status] [-i | -o] [--pathspec-from-file=<file> [--pathspec-file-nul]] [(--trailer <token>[(=|:)<value>])...] [-S[<keyid>]] [--] [<pathspec>...]

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `pathspec` | `str | None` | no | Positional argument: pathspec |
| `quiet` | `bool | None` | no | suppress summary after successful commit |
| `verbose` | `bool | None` | no | show diff in commit message template |
| `file` | `str | None` | no | read message from file |
| `author` | `str | None` | no | override author for commit |
| `date` | `str | None` | no | override date for commit |
| `message` | `str | None` | no | commit message |
| `reedit_message` | `str | None` | no | reuse and edit message from specified commit |
| `reuse_message` | `str | None` | no | reuse message from specified commit |
| `squash` | `str | None` | no | use autosquash formatted message to squash specified commit |
| `reset_author` | `bool | None` | no | the commit is authored by me now (used with -C/-c/--amend) |
| `trailer` | `str | None` | no | add custom trailer(s) |
| `signoff` | `bool | None` | no | add a Signed-off-by trailer |
| `template` | `str | None` | no | use specified template file |
| `edit` | `bool | None` | no | force edit of commit |
| `status` | `bool | None` | no | include status in commit message template |
| `all` | `bool | None` | no | commit all changed files |
| `include` | `bool | None` | no | add specified files to index for commit |
| `interactive` | `bool | None` | no | interactively add files |
| `patch` | `bool | None` | no | interactively add changes |
| `only` | `bool | None` | no | commit only specified files |
| `no_verify` | `bool | None` | no | bypass pre-commit and commit-msg hooks |
| `verify` | `bool | None` | no | opposite of --no-verify |
| `dry_run` | `bool | None` | no | show what would be committed |
| `short` | `bool | None` | no | show status concisely |
| `branch` | `bool | None` | no | show branch information |
| `ahead_behind` | `bool | None` | no | compute full ahead/behind values |
| `porcelain` | `bool | None` | no | machine-readable output |
| `long` | `bool | None` | no | show status in long format (default) |
| `null` | `bool | None` | no | terminate entries with NUL |
| `amend` | `bool | None` | no | amend previous commit |
| `no_post_rewrite` | `bool | None` | no | bypass post-rewrite hook |
| `post_rewrite` | `bool | None` | no | opposite of --no-post-rewrite |
| `pathspec_from_file` | `str | None` | no | read pathspec from file |
| `pathspec_file_nul` | `bool | None` | no | with --pathspec-from-file, pathspec elements are separated with NUL character |
---
### `merge`

or: git merge --abort or: git merge --continue

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `commit` | `str | None` | no | Positional argument: commit |
| `n` | `bool | None` | no | do not show a diffstat at the end of the merge |
| `stat` | `bool | None` | no | show a diffstat at the end of the merge |
| `summary` | `bool | None` | no | (synonym to --stat) |
| `squash` | `bool | None` | no | create a single commit instead of doing a merge |
| `edit` | `bool | None` | no | edit message before committing |
| `ff` | `bool | None` | no | allow fast-forward (default) |
| `ff_only` | `bool | None` | no | abort if fast-forward is not possible |
| `rerere_autoupdate` | `bool | None` | no | update the index with reused conflict resolution if possible |
| `verify_signatures` | `bool | None` | no | verify that the named commit has a valid GPG signature |
| `strategy` | `str | None` | no | merge strategy to use |
| `message` | `str | None` | no | merge commit message (for a non-fast-forward merge) |
| `file` | `str | None` | no | read message from file |
| `into_name` | `str | None` | no | use <name> instead of the real target |
| `verbose` | `bool | None` | no | be more verbose |
| `quiet` | `bool | None` | no | be more quiet |
| `abort` | `bool | None` | no | abort the current in-progress merge |
| `quit` | `bool | None` | no | --abort but leave index and working tree alone |
| `continue_` | `bool | None` | no | continue the current in-progress merge |
| `allow_unrelated_histories` | `bool | None` | no | allow merging unrelated histories |
| `progress` | `bool | None` | no | force progress reporting |
| `autostash` | `bool | None` | no | automatically stash/stash pop before and after |
| `overwrite_ignore` | `bool | None` | no | update ignored files (default) |
| `signoff` | `bool | None` | no | add a Signed-off-by trailer |
| `no_verify` | `bool | None` | no | bypass pre-merge-commit and commit-msg hooks |
| `verify` | `bool | None` | no | opposite of --no-verify |
---
### `rebase`

or: git rebase [-i] [options] [--exec <cmd>] [--onto <newbase>] --root [<branch>] or: git rebase --continue | --abort | --skip | --edit-todo

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `branch` | `str | None` | no | Positional argument: branch |
| `no_verify` | `bool | None` | no | allow pre-rebase hook to run |
| `verify` | `bool | None` | no | opposite of --no-verify |
| `quiet` | `bool | None` | no | be quiet. implies --no-stat |
| `verbose` | `bool | None` | no | display a diffstat of what changed upstream |
| `no_stat` | `bool | None` | no | do not show diffstat of what changed upstream |
| `stat` | `bool | None` | no | opposite of --no-stat |
| `signoff` | `bool | None` | no | add a Signed-off-by trailer to each commit |
| `committer_date_is_author_date` | `bool | None` | no | make committer date match author date |
| `reset_author_date` | `bool | None` | no | ignore author date and use current date |
| `C` | `int | None` | no | passed to 'git apply' |
| `ignore_whitespace` | `bool | None` | no | ignore changes in whitespace |
| `whitespace` | `str | None` | no | passed to 'git apply' |
| `force_rebase` | `bool | None` | no | cherry-pick all commits, even if unchanged |
| `no_ff` | `bool | None` | no | cherry-pick all commits, even if unchanged |
| `ff` | `bool | None` | no | opposite of --no-ff |
| `continue_` | `bool | None` | no | continue |
| `skip` | `bool | None` | no | skip current patch and continue |
| `abort` | `bool | None` | no | abort and check out the original branch |
| `quit` | `bool | None` | no | abort but keep HEAD where it is |
| `edit_todo` | `bool | None` | no | edit the todo list during an interactive rebase |
| `show_current_patch` | `bool | None` | no | show the patch file being applied or merged |
| `apply` | `bool | None` | no | use apply strategies to rebase |
| `merge` | `bool | None` | no | use merging strategies to rebase |
| `interactive` | `bool | None` | no | let the user edit the list of commits to rebase |
| `rerere_autoupdate` | `bool | None` | no | update the index with reused conflict resolution if possible |
| `autosquash` | `bool | None` | no | move commits that begin with squash!/fixup! under -i |
| `update_refs` | `bool | None` | no | update branches that point to commits that are being rebased |
| `autostash` | `bool | None` | no | automatically stash/stash pop before and after |
| `exec` | `str | None` | no | add exec lines after each commit of the editable list |
| `fork_point` | `bool | None` | no | use 'merge-base --fork-point' to refine upstream |
| `strategy` | `str | None` | no | use the given merge strategy |
| `strategy_option` | `str | None` | no | pass the argument through to the merge strategy |
| `root` | `bool | None` | no | rebase all reachable commits up to the root(s) |
| `reschedule_failed_exec` | `bool | None` | no | automatically re-schedule any `exec` that fails |
| `reapply_cherry_picks` | `bool | None` | no | apply all changes, even those already present upstream |
---
### `reset`

or: git reset [-q] [<tree-ish>] [--] <pathspec>... or: git reset [-q] [--pathspec-from-file [--pathspec-file-nul]] [<tree-ish>] or: git reset --patch [<tree-ish>] [--] [<pathspec>...] or: DEPRECATED: git reset [-q] [--stdin [-z]] [<tree-ish>]

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `commit` | `str | None` | no | Positional argument: commit |
| `tree_ish` | `str | None` | no | Positional argument: tree_ish |
| `pathspec` | `str | None` | no | Positional argument: pathspec |
| `quiet` | `bool | None` | no | be quiet, only report errors |
| `no_refresh` | `bool | None` | no | skip refreshing the index after reset |
| `refresh` | `bool | None` | no | opposite of --no-refresh |
| `mixed` | `bool | None` | no | reset HEAD and index |
| `soft` | `bool | None` | no | reset only HEAD |
| `hard` | `bool | None` | no | reset HEAD, index and working tree |
| `merge` | `bool | None` | no | reset HEAD, index and working tree |
| `keep` | `bool | None` | no | reset HEAD but keep local changes |
| `patch` | `bool | None` | no | select hunks interactively |
| `intent_to_add` | `bool | None` | no | record only the fact that removed paths will be added later |
| `pathspec_from_file` | `str | None` | no | read pathspec from file |
| `pathspec_file_nul` | `bool | None` | no | with --pathspec-from-file, pathspec elements are separated with NUL character |
| `z` | `bool | None` | no | DEPRECATED (use --pathspec-file-nul instead): paths are separated with NUL character |
| `stdin` | `bool | None` | no | DEPRECATED (use --pathspec-from-file=- instead): read paths from <stdin> |
---
### `switch`

Switch branches

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `branch` | `str | None` | no | Positional argument: branch |
| `create` | `str | None` | no | create and switch to a new branch |
| `force_create` | `str | None` | no | create/reset and switch to a branch |
| `guess` | `bool | None` | no | second guess 'git switch <no-such-branch>' |
| `discard_changes` | `bool | None` | no | throw away local modifications |
| `quiet` | `bool | None` | no | suppress progress reporting |
| `progress` | `bool | None` | no | force progress reporting |
| `merge` | `bool | None` | no | perform a 3-way merge with the new branch |
| `conflict` | `str | None` | no | conflict style (merge, diff3, or zdiff3) |
| `detach` | `bool | None` | no | detach HEAD at named commit |
| `force` | `bool | None` | no | force checkout (throw away local modifications) |
| `orphan` | `str | None` | no | new unparented branch |
| `overwrite_ignore` | `bool | None` | no | update ignored files (default) |
| `ignore_other_worktrees` | `bool | None` | no | do not check if another worktree is holding the given ref |
---
### `tag`

<tagname> [<commit> | <object>] or: git tag -d <tagname>... or: git tag [-n[<num>]] -l [--contains <commit>] [--no-contains <commit>] [--points-at <object>] [--column[=<options>] | --no-column] [--create-reflog] [--sort=<key>] [--format=<format>] [--merged <commit>] [--no-merged <commit>] [<pattern>...] or: git tag -v [--format=<format>] <tagname>...

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `tagname` | `str | None` | no | Positional argument: tagname |
| `commit` | `str | None` | no | Positional argument: commit |
| `object` | `str | None` | no | Positional argument: object |
| `pattern` | `str | None` | no | Positional argument: pattern |
| `list` | `bool | None` | no | list tag names |
| `delete` | `bool | None` | no | delete tags |
| `verify` | `bool | None` | no | verify tags |
| `annotate` | `bool | None` | no | annotated tag, needs a message |
| `message` | `str | None` | no | tag message |
| `file` | `str | None` | no | read message from file |
| `edit` | `bool | None` | no | force edit of tag message |
| `sign` | `bool | None` | no | annotated and GPG-signed tag |
| `local_user` | `str | None` | no | use another key to sign the tag |
| `force` | `bool | None` | no | replace the tag if exists |
| `create_reflog` | `bool | None` | no | create a reflog |
| `contains` | `str | None` | no | print only tags that contain the commit |
| `no_contains` | `str | None` | no | print only tags that don't contain the commit |
| `merged` | `str | None` | no | print only tags that are merged |
| `no_merged` | `str | None` | no | print only tags that are not merged |
| `omit_empty` | `bool | None` | no | do not output a newline after empty formatted refs |
| `sort` | `str | None` | no | field name to sort on |
| `points_at` | `str | None` | no | print only tags of the object |
| `format` | `str | None` | no | format to use for the output |
| `ignore_case` | `bool | None` | no | sorting and filtering are case insensitive |
---
### `fetch`

or: git fetch [<options>] <group> or: git fetch --multiple [<options>] [(<repository> | <group>)...] or: git fetch --all [<options>]

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `repository` | `str | None` | no | Positional argument: repository |
| `refspec` | `str | None` | no | Positional argument: refspec |
| `group` | `str | None` | no | Positional argument: group |
| `verbose` | `bool | None` | no | be more verbose |
| `quiet` | `bool | None` | no | be more quiet |
| `all` | `bool | None` | no | fetch from all remotes |
| `set_upstream` | `bool | None` | no | set upstream for git pull/fetch |
| `append` | `bool | None` | no | append to .git/FETCH_HEAD instead of overwriting |
| `atomic` | `bool | None` | no | use atomic transaction to update references |
| `upload_pack` | `str | None` | no | path to upload pack on remote end |
| `force` | `bool | None` | no | force overwrite of local reference |
| `multiple` | `bool | None` | no | fetch from multiple remotes |
| `tags` | `bool | None` | no | fetch all tags and associated objects |
| `n` | `bool | None` | no | do not fetch all tags (--no-tags) |
| `jobs` | `int | None` | no | number of submodules fetched in parallel |
| `prefetch` | `bool | None` | no | modify the refspec to place all refs within refs/prefetch/ |
| `prune` | `bool | None` | no | prune remote-tracking branches no longer on remote |
| `dry_run` | `bool | None` | no | dry run |
| `porcelain` | `bool | None` | no | machine-readable output |
| `write_fetch_head` | `bool | None` | no | write fetched references to the FETCH_HEAD file |
| `keep` | `bool | None` | no | keep downloaded pack |
| `update_head_ok` | `bool | None` | no | allow updating of HEAD ref |
| `progress` | `bool | None` | no | force progress reporting |
| `depth` | `str | None` | no | deepen history of shallow clone |
| `shallow_since` | `str | None` | no | deepen history of shallow repository based on time |
| `shallow_exclude` | `str | None` | no | deepen history of shallow clone, excluding rev |
| `deepen` | `int | None` | no | deepen history of shallow clone |
| `unshallow` | `bool | None` | no | convert to a complete repository |
| `refetch` | `bool | None` | no | re-fetch without negotiating common commits |
| `refmap` | `str | None` | no | specify fetch refmap |
| `server_option` | `str | None` | no | option to transmit |
| `ipv4` | `bool | None` | no | use IPv4 addresses only |
| `ipv6` | `bool | None` | no | use IPv6 addresses only |
| `negotiation_tip` | `str | None` | no | report that we have only objects reachable from this object |
| `filter` | `str | None` | no | object filtering |
| `auto_maintenance` | `bool | None` | no | run 'maintenance --auto' after fetching |
| `auto_gc` | `bool | None` | no | run 'maintenance --auto' after fetching |
| `show_forced_updates` | `bool | None` | no | check for forced-updates on all updated branches |
| `write_commit_graph` | `bool | None` | no | write the commit-graph after fetching |
| `stdin` | `bool | None` | no | accept refspecs from stdin |
---
### `pull`

Fetch from and integrate with another repository or a local branch

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `repository` | `str | None` | no | Positional argument: repository |
| `refspec` | `str | None` | no | Positional argument: refspec |
| `verbose` | `bool | None` | no | be more verbose |
| `quiet` | `bool | None` | no | be more quiet |
| `progress` | `bool | None` | no | force progress reporting |
| `n` | `bool | None` | no | do not show a diffstat at the end of the merge |
| `stat` | `bool | None` | no | show a diffstat at the end of the merge |
| `squash` | `bool | None` | no | create a single commit instead of doing a merge |
| `commit` | `bool | None` | no | perform a commit if the merge succeeds (default) |
| `edit` | `bool | None` | no | edit message before committing |
| `ff` | `bool | None` | no | allow fast-forward |
| `ff_only` | `bool | None` | no | abort if fast-forward is not possible |
| `verify` | `bool | None` | no | control use of pre-merge-commit and commit-msg hooks |
| `verify_signatures` | `bool | None` | no | verify that the named commit has a valid GPG signature |
| `autostash` | `bool | None` | no | automatically stash/stash pop before and after |
| `strategy` | `str | None` | no | merge strategy to use |
| `allow_unrelated_histories` | `bool | None` | no | allow merging unrelated histories |
| `all` | `bool | None` | no | fetch from all remotes |
| `append` | `bool | None` | no | append to .git/FETCH_HEAD instead of overwriting |
| `upload_pack` | `str | None` | no | path to upload pack on remote end |
| `force` | `bool | None` | no | force overwrite of local branch |
| `tags` | `bool | None` | no | fetch all tags and associated objects |
| `prune` | `bool | None` | no | prune remote-tracking branches no longer on remote |
| `dry_run` | `bool | None` | no | dry run |
| `keep` | `bool | None` | no | keep downloaded pack |
| `depth` | `str | None` | no | deepen history of shallow clone |
| `shallow_since` | `str | None` | no | deepen history of shallow repository based on time |
| `shallow_exclude` | `str | None` | no | deepen history of shallow clone, excluding rev |
| `deepen` | `int | None` | no | deepen history of shallow clone |
| `unshallow` | `bool | None` | no | convert to a complete repository |
| `refmap` | `str | None` | no | specify fetch refmap |
| `server_option` | `str | None` | no | option to transmit |
| `ipv4` | `bool | None` | no | use IPv4 addresses only |
| `ipv6` | `bool | None` | no | use IPv6 addresses only |
| `negotiation_tip` | `str | None` | no | report that we have only objects reachable from this object |
| `show_forced_updates` | `bool | None` | no | check for forced-updates on all updated branches |
| `set_upstream` | `bool | None` | no | set upstream for git pull/fetch |
---
### `push`

Update remote refs along with associated objects

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `repository` | `str | None` | no | Positional argument: repository |
| `refspec` | `str | None` | no | Positional argument: refspec |
| `verbose` | `bool | None` | no | be more verbose |
| `quiet` | `bool | None` | no | be more quiet |
| `repo` | `str | None` | no | repository |
| `all` | `bool | None` | no | push all branches |
| `branches` | `bool | None` | no | alias of --all |
| `mirror` | `bool | None` | no | mirror all refs |
| `delete` | `bool | None` | no | delete refs |
| `tags` | `bool | None` | no | push tags (can't be used with --all or --branches or --mirror) |
| `dry_run` | `bool | None` | no | dry run |
| `porcelain` | `bool | None` | no | machine-readable output |
| `force` | `bool | None` | no | force updates |
| `force_if_includes` | `bool | None` | no | require remote updates to be integrated locally |
| `thin` | `bool | None` | no | use thin pack |
| `receive_pack` | `str | None` | no | receive pack program |
| `exec` | `str | None` | no | receive pack program |
| `set_upstream` | `bool | None` | no | set upstream for git pull/status |
| `progress` | `bool | None` | no | force progress reporting |
| `prune` | `bool | None` | no | prune locally removed refs |
| `no_verify` | `bool | None` | no | bypass pre-push hook |
| `verify` | `bool | None` | no | opposite of --no-verify |
| `follow_tags` | `bool | None` | no | push missing but relevant tags |
| `atomic` | `bool | None` | no | request atomic transaction on remote side |
| `push_option` | `str | None` | no | option to transmit |
| `ipv4` | `bool | None` | no | use IPv4 addresses only |
| `ipv6` | `bool | None` | no | use IPv6 addresses only |
---
