# Guide d'utilisation — git_cli

Ce serveur MCP a été généré par **[mcp-forge](https://mcp-forge.vulcai.io)**.
Il expose 22 outil(s) via le protocole MCP (Model Context Protocol).

---

## 1. Lancement local

```bash
pip install -r requirements.txt
python server.py
```

Testez avec MCP Inspector :

```bash
mcp dev server.py
```

> Sans `MCP_SERVER_TOKEN`, le serveur est ouvert (mode développement local). Définissez `MCP_SERVER_TOKEN` pour sécuriser les connexions.

---

## 2. Déploiement remote (SSE)

Pour déployer le serveur et le connecter depuis Claude.ai / Cursor :

```bash
MCP_SERVER_URL=https://mon-serveur.exemple.com \
MCP_SERVER_TOKEN=mon_secret \
BEARER_TOKEN=votre_cle_api \
python server.py
```

### Variables d'environnement

| Variable | Rôle | Quand la définir |
|----------|------|-----------------|
| `MCP_SERVER_URL` | URL publique du serveur (ex: `https://mon-serveur.com`) | Toujours en remote |
| `MCP_SERVER_TOKEN` | Mot de passe pour se connecter au serveur MCP | Toujours en remote |
| `BEARER_TOKEN` | Clé API à utiliser pour appeler l'API downstream | **Mode partagé** : une seule clé pour tous |
| `OAUTH_ALLOWED_REDIRECT_HOSTS` | Whitelist des hôtes autorisés pour `redirect_uri` OAuth (ex: `claude.ai,cursor.sh`) | **Obligatoire en production** — voir ci-dessous |

> ⚠️ **Sécurité OAuth — `OAUTH_ALLOWED_REDIRECT_HOSTS` doit être défini en production.**
>
> Sans cette variable, le serveur n'autorise que `localhost` et `127.0.0.1` comme `redirect_uri`.
> En production, définissez-la avec les hôtes exacts de vos clients MCP :
>
> ```bash
> OAUTH_ALLOWED_REDIRECT_HOSTS=claude.ai,cursor.sh,app.monentreprise.com \
> MCP_SERVER_URL=https://mon-serveur.exemple.com \
> python server.py
> ```
>
> Une `redirect_uri` non autorisée retourne HTTP 400 `invalid_request` (prévention open redirect).

> **Mode proxy** (multi-utilisateurs) : si vous ne définissez pas `BEARER_TOKEN`, chaque utilisateur devra entrer sa propre clé API lors de la connexion OAuth. Chaque appel utilisera alors sa propre clé. Utile si chacun a son propre compte sur l'API.

**Connexion OAuth (recommandé)** — sans copier-coller de token :

1. Dans Claude.ai : **Paramètres → Connecteurs → +**
2. URL : `https://mon-serveur.exemple.com/sse`
3. Cliquez **Ajouter** → une page de login s'ouvre → entrez votre `MCP_SERVER_TOKEN`

**Connexion directe par token** :

URL : `https://mon-serveur.exemple.com/sse?token=<MCP_SERVER_TOKEN>`

---

## 3. Connexion depuis Claude.ai (local)

Dans Paramètres → Connecteurs → + :
- **URL** : `http://localhost:8000/sse?token=<votre_clé_api>`

---

## 4. Connexion depuis Cursor

Ajoutez dans `~/.cursor/mcp.json` (ou `.cursor/mcp.json` à la racine du projet) :

```json
{
  "mcpServers": {
    "git_cli": {
      "url": "http://localhost:8000/sse",
      "headers": {
        "Authorization": "Bearer <votre_clé_api>"
      }
    }
  }
}
```

---

## 5. Connexion depuis Claude Code (CLI)

```bash
claude mcp add git_cli \
  --transport sse \
  --url "http://localhost:8000/sse" \
  --header "Authorization: Bearer <votre_clé_api>"
```

Ou ajoutez manuellement dans `.claude/settings.json` :

```json
{
  "mcpServers": {
    "git_cli": {
      "type": "sse",
      "url": "http://localhost:8000/sse",
      "headers": {
        "Authorization": "Bearer <votre_clé_api>"
      }
    }
  }
}
```

---

## 6. Outils disponibles

### `clone`

Clone a repository into a new directory

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `repo` | `str` | ✅ | Positional argument: repo |
| `dir` | `str | None` | — | Positional argument: dir |
| `verbose` | `bool | None` | — | be more verbose |
| `quiet` | `bool | None` | — | be more quiet |
| `progress` | `bool | None` | — | force progress reporting |
| `no_checkout` | `bool | None` | — | don't create a checkout |
| `checkout` | `bool | None` | — | opposite of --no-checkout |
| `bare` | `bool | None` | — | create a bare repository |
| `mirror` | `bool | None` | — | create a mirror repository (implies bare) |
| `local` | `bool | None` | — | to clone from a local repository |
| `no_hardlinks` | `bool | None` | — | don't use local hardlinks, always copy |
| `hardlinks` | `bool | None` | — | opposite of --no-hardlinks |
| `shared` | `bool | None` | — | setup as shared repository |
| `jobs` | `int | None` | — | number of submodules cloned in parallel |
| `template` | `str | None` | — | directory from which templates will be used |
| `reference` | `str | None` | — | reference repository |
| `reference_if_able` | `str | None` | — | reference repository |
| `dissociate` | `bool | None` | — | use --reference only while cloning |
| `origin` | `str | None` | — | use <name> instead of 'origin' to track upstream |
| `branch` | `str | None` | — | checkout <branch> instead of the remote's HEAD |
| `upload_pack` | `str | None` | — | path to git-upload-pack on the remote |
| `depth` | `str | None` | — | create a shallow clone of that depth |
| `shallow_since` | `str | None` | — | create a shallow clone since a specific time |
| `shallow_exclude` | `str | None` | — | deepen history of shallow clone, excluding rev |
| `single_branch` | `bool | None` | — | clone only one branch, HEAD or --branch |
| `no_tags` | `bool | None` | — | don't clone any tags, and make later fetches not to follow them |
| `tags` | `bool | None` | — | opposite of --no-tags |
| `shallow_submodules` | `bool | None` | — | any cloned submodules will be shallow |
| `separate_git_dir` | `str | None` | — | separate git dir from working tree |
| `server_option` | `str | None` | — | option to transmit |
| `ipv4` | `bool | None` | — | use IPv4 addresses only |
| `ipv6` | `bool | None` | — | use IPv6 addresses only |
| `filter` | `str | None` | — | object filtering |
| `also_filter_submodules` | `bool | None` | — | apply partial clone filters to submodules |
| `remote_submodules` | `bool | None` | — | any cloned submodules will use their remote-tracking branch |
| `sparse` | `bool | None` | — | initialize sparse-checkout file to include only files at root |
| `bundle_uri` | `str | None` | — | a URI for downloading bundles before fetching from origin remote |

### `init`

[--separate-git-dir <git-dir>] [--object-format=<format>] [-b <branch-name> | --initial-branch=<branch-name>] [--shared[=<permissions>]] [<directory>]

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `directory` | `str | None` | — | Positional argument: directory |
| `quiet` | `bool | None` | — | be quiet |
| `separate_git_dir` | `str | None` | — | separate git dir from working tree |
| `initial_branch` | `str | None` | — | override the name of the initial branch |
| `object_format` | `str | None` | — | specify the hash algorithm to use |

### `add`

Add file contents to the index

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `pathspec` | `str` | ✅ | Positional argument: pathspec |
| `dry_run` | `bool | None` | — | dry run |
| `verbose` | `bool | None` | — | be verbose |
| `interactive` | `bool | None` | — | interactive picking |
| `patch` | `bool | None` | — | select hunks interactively |
| `edit` | `bool | None` | — | edit current diff and apply |
| `force` | `bool | None` | — | allow adding otherwise ignored files |
| `update` | `bool | None` | — | update tracked files |
| `renormalize` | `bool | None` | — | renormalize EOL of tracked files (implies -u) |
| `intent_to_add` | `bool | None` | — | record only the fact that the path will be added later |
| `all` | `bool | None` | — | add changes from all tracked and untracked files |
| `refresh` | `bool | None` | — | don't add, only refresh the index |
| `ignore_errors` | `bool | None` | — | just skip files which cannot be added because of errors |
| `sparse` | `bool | None` | — | allow updating entries outside of the sparse-checkout cone |
| `pathspec_from_file` | `str | None` | — | read pathspec from file |
| `pathspec_file_nul` | `bool | None` | — | with --pathspec-from-file, pathspec elements are separated with NUL character |

### `mv`

Move or rename a file, a directory, or a symlink

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `source` | `str` | ✅ | Positional argument: source |
| `destination` | `str` | ✅ | Positional argument: destination |
| `verbose` | `bool | None` | — | be verbose |
| `dry_run` | `bool | None` | — | dry run |
| `force` | `bool | None` | — | force move/rename even if target exists |
| `k` | `bool | None` | — | skip move/rename errors |
| `sparse` | `bool | None` | — | allow updating entries outside of the sparse-checkout cone |

### `restore`

Restore working tree files

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `file` | `str` | ✅ | Positional argument: file |
| `source` | `str | None` | — | which tree-ish to checkout from |
| `staged` | `bool | None` | — | restore the index |
| `worktree` | `bool | None` | — | restore the working tree (default) |
| `ignore_unmerged` | `bool | None` | — | ignore unmerged entries |
| `overlay` | `bool | None` | — | use overlay mode |
| `quiet` | `bool | None` | — | suppress progress reporting |
| `progress` | `bool | None` | — | force progress reporting |
| `merge` | `bool | None` | — | perform a 3-way merge with the new branch |
| `conflict` | `str | None` | — | conflict style (merge, diff3, or zdiff3) |
| `ours` | `bool | None` | — | checkout our version for unmerged files |
| `theirs` | `bool | None` | — | checkout their version for unmerged files |
| `patch` | `bool | None` | — | select hunks interactively |
| `ignore_skip_worktree_bits` | `bool | None` | — | do not limit pathspecs to sparse entries only |
| `pathspec_from_file` | `str | None` | — | read pathspec from file |
| `pathspec_file_nul` | `bool | None` | — | with --pathspec-from-file, pathspec elements are separated with NUL character |

### `rm`

[--quiet] [--pathspec-from-file=<file> [--pathspec-file-nul]] [--] [<pathspec>...]

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `pathspec` | `str | None` | — | Positional argument: pathspec |
| `dry_run` | `bool | None` | — | dry run |
| `quiet` | `bool | None` | — | do not list removed files |
| `cached` | `bool | None` | — | only remove from the index |
| `force` | `bool | None` | — | override the up-to-date check |
| `r` | `bool | None` | — | allow recursive removal |
| `sparse` | `bool | None` | — | allow updating entries outside of the sparse-checkout cone |
| `pathspec_from_file` | `str | None` | — | read pathspec from file |
| `pathspec_file_nul` | `bool | None` | — | with --pathspec-from-file, pathspec elements are separated with NUL character |

### `bisect`

or: git bisect (good|bad) [<rev>...] or: git bisect terms [--term-good | --term-bad] or: git bisect skip [(<rev>|<range>)...] or: git bisect next or: git bisect reset [<commit>] or: git bisect visualize or: git bisect replay <logfile> or: git bisect log or: git bisect run <cmd> [<arg>...]

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `bad` | `str | None` | — | Positional argument: bad |
| `good` | `str | None` | — | Positional argument: good |
| `pathspec` | `str | None` | — | Positional argument: pathspec |
| `rev` | `str | None` | — | Positional argument: rev |
| `commit` | `str | None` | — | Positional argument: commit |
| `logfile` | `str | None` | — | Positional argument: logfile |
| `cmd` | `str | None` | — | Positional argument: cmd |

### `diff`

or: git diff [<options>] --cached [--merge-base] [<commit>] [--] [<path>...] or: git diff [<options>] [--merge-base] <commit> [<commit>...] <commit> [--] [<path>...] or: git diff [<options>] <commit>...<commit> [--] [<path>...] or: git diff [<options>] <blob> <blob> or: git diff [<options>] --no-index [--] <path> <path> common diff options:

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `commit` | `str | None` | — | Positional argument: commit |
| `path` | `str | None` | — | Positional argument: path |
| `blob` | `str | None` | — | Positional argument: blob |
| `z` | `bool | None` | — | output diff-raw with lines terminated with NUL. |
| `p` | `bool | None` | — | output patch format. |
| `u` | `bool | None` | — | synonym for -p. |
| `patch_with_raw` | `bool | None` | — | output both a patch and the diff-raw format. |
| `stat` | `bool | None` | — | show diffstat instead of patch. |
| `numstat` | `bool | None` | — | show numeric diffstat instead of patch. |
| `patch_with_stat` | `bool | None` | — | output a patch and prepend its diffstat. |
| `name_only` | `bool | None` | — | show only names of changed files. |
| `full_index` | `bool | None` | — | show full object name on index lines. |
| `R` | `bool | None` | — | swap input file pairs. |
| `B` | `bool | None` | — | detect complete rewrites. |
| `M` | `bool | None` | — | detect renames. |
| `C` | `bool | None` | — | detect copies. |
| `find_copies_harder` | `bool | None` | — | try unchanged files as candidate for copy detection. |
| `pickaxe_all` | `bool | None` | — | show all files diff when -S is used and hit is found. |
| `a` | `bool | None` | — | --text    treat all files as text. |

### `grep`

Print lines matching a pattern

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `pattern` | `str` | ✅ | Positional argument: pattern |
| `rev` | `str | None` | — | Positional argument: rev |
| `path` | `str | None` | — | Positional argument: path |
| `no_index` | `bool | None` | — | find in contents not managed by git |
| `index` | `bool | None` | — | opposite of --no-index |
| `untracked` | `bool | None` | — | search in both tracked and untracked files |
| `exclude_standard` | `bool | None` | — | ignore files specified via '.gitignore' |
| `recurse_submodules` | `bool | None` | — | recursively search in each submodule |
| `invert_match` | `bool | None` | — | show non-matching lines |
| `ignore_case` | `bool | None` | — | case insensitive matching |
| `word_regexp` | `bool | None` | — | match patterns only at word boundaries |
| `text` | `bool | None` | — | process binary files as text |
| `I` | `bool | None` | — | don't match patterns in binary files |
| `textconv` | `bool | None` | — | process binary files with textconv filters |
| `recursive` | `bool | None` | — | search in subdirectories (default) |
| `max_depth` | `int | None` | — | descend at most <n> levels |
| `extended_regexp` | `bool | None` | — | use extended POSIX regular expressions |
| `basic_regexp` | `bool | None` | — | use basic POSIX regular expressions (default) |
| `fixed_strings` | `bool | None` | — | interpret patterns as fixed strings |
| `perl_regexp` | `bool | None` | — | use Perl-compatible regular expressions |
| `line_number` | `bool | None` | — | show line numbers |
| `column` | `bool | None` | — | show column number of first match |
| `h` | `bool | None` | — | don't show filenames |
| `H` | `bool | None` | — | show filenames |
| `full_name` | `bool | None` | — | show filenames relative to top directory |
| `files_with_matches` | `bool | None` | — | show only filenames instead of matching lines |
| `name_only` | `bool | None` | — | synonym for --files-with-matches |
| `files_without_match` | `bool | None` | — | show only the names of files without match |
| `null` | `bool | None` | — | print NUL after filenames |
| `only_matching` | `bool | None` | — | show only matching parts of a line |
| `count` | `bool | None` | — | show the number of matches instead of matching lines |
| `break_` | `bool | None` | — | print empty line between matches from different files |
| `heading` | `bool | None` | — | show filename only once above matches from same file |
| `context` | `int | None` | — | show <n> context lines before and after matches |
| `before_context` | `int | None` | — | show <n> context lines before matches |
| `after_context` | `int | None` | — | show <n> context lines after matches |
| `threads` | `int | None` | — | use <n> worker threads |
| `show_function` | `bool | None` | — | show a line with the function name before matches |
| `function_context` | `bool | None` | — | show the surrounding function |
| `f` | `str | None` | — | read patterns from file |
| `e` | `str | None` | — | match <pattern> |
| `and_` | `bool | None` | — | combine patterns specified with -e |
| `quiet` | `bool | None` | — | indicate hit with exit status without output |
| `all_match` | `bool | None` | — | show only matches from files that match all patterns |
| `ext_grep` | `bool | None` | — | allow calling of grep(1) (ignored by this build) |
| `max_count` | `int | None` | — | maximum number of results per file |

### `log`

or: git show [<options>] <object>...

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `revision_range` | `str | None` | — | Positional argument: revision_range |
| `path` | `str | None` | — | Positional argument: path |
| `object` | `str | None` | — | Positional argument: object |
| `quiet` | `bool | None` | — | suppress diff output |
| `source` | `bool | None` | — | show source |
| `use_mailmap` | `bool | None` | — | use mail map file |
| `mailmap` | `bool | None` | — | alias of --use-mailmap |
| `clear_decorations` | `bool | None` | — | clear all previously-defined decoration filters |
| `decorate_refs` | `str | None` | — | only decorate refs that match <pattern> |
| `decorate_refs_exclude` | `str | None` | — | do not decorate refs that match <pattern> |

### `show`

or: git show [<options>] <object>...

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `revision_range` | `str | None` | — | Positional argument: revision_range |
| `path` | `str | None` | — | Positional argument: path |
| `object` | `str | None` | — | Positional argument: object |
| `quiet` | `bool | None` | — | suppress diff output |
| `source` | `bool | None` | — | show source |
| `use_mailmap` | `bool | None` | — | use mail map file |
| `mailmap` | `bool | None` | — | alias of --use-mailmap |
| `clear_decorations` | `bool | None` | — | clear all previously-defined decoration filters |
| `decorate_refs` | `str | None` | — | only decorate refs that match <pattern> |
| `decorate_refs_exclude` | `str | None` | — | do not decorate refs that match <pattern> |

### `status`

Show the working tree status

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `pathspec` | `str | None` | — | Positional argument: pathspec |
| `verbose` | `bool | None` | — | be verbose |
| `short` | `bool | None` | — | show status concisely |
| `branch` | `bool | None` | — | show branch information |
| `show_stash` | `bool | None` | — | show stash information |
| `ahead_behind` | `bool | None` | — | compute full ahead/behind values |
| `long` | `bool | None` | — | show status in long format (default) |
| `null` | `bool | None` | — | terminate entries with NUL |
| `no_renames` | `bool | None` | — | do not detect renames |
| `renames` | `bool | None` | — | opposite of --no-renames |

### `branch`

or: git branch [<options>] [-f] [--recurse-submodules] <branch-name> [<start-point>] or: git branch [<options>] [-l] [<pattern>...] or: git branch [<options>] [-r] (-d | -D) <branch-name>... or: git branch [<options>] (-m | -M) [<old-branch>] <new-branch> or: git branch [<options>] (-c | -C) [<old-branch>] <new-branch> or: git branch [<options>] [-r | -a] [--points-at] or: git branch [<options>] [-r | -a] [--format] Generic options

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `branch_name` | `str | None` | — | Positional argument: branch_name |
| `start_point` | `str | None` | — | Positional argument: start_point |
| `pattern` | `str | None` | — | Positional argument: pattern |
| `new_branch` | `str | None` | — | Positional argument: new_branch |
| `verbose` | `bool | None` | — | show hash and subject, give twice for upstream branch |
| `quiet` | `bool | None` | — | suppress informational messages |
| `set_upstream_to` | `str | None` | — | change the upstream info |
| `remotes` | `bool | None` | — | act on remote-tracking branches |
| `contains` | `str | None` | — | print only branches that contain the commit |
| `no_contains` | `str | None` | — | print only branches that don't contain the commit |
| `all` | `bool | None` | — | list both remote-tracking and local branches |
| `delete` | `bool | None` | — | delete fully merged branch |
| `D` | `bool | None` | — | delete branch (even if not merged) |
| `move` | `bool | None` | — | move/rename a branch and its reflog |
| `M` | `bool | None` | — | move/rename a branch, even if target exists |
| `omit_empty` | `bool | None` | — | do not output a newline after empty formatted refs |
| `copy` | `bool | None` | — | copy a branch and its reflog |
| `C` | `bool | None` | — | copy a branch, even if target exists |
| `list` | `bool | None` | — | list branch names |
| `show_current` | `bool | None` | — | show current branch name |
| `create_reflog` | `bool | None` | — | create the branch's reflog |
| `edit_description` | `bool | None` | — | edit the description for the branch |
| `force` | `bool | None` | — | force creation, move/rename, deletion |
| `merged` | `str | None` | — | print only branches that are merged |
| `no_merged` | `str | None` | — | print only branches that are not merged |
| `sort` | `str | None` | — | field name to sort on |
| `points_at` | `str | None` | — | print only branches of the object |
| `ignore_case` | `bool | None` | — | sorting and filtering are case insensitive |
| `recurse_submodules` | `bool | None` | — | recurse through submodules |
| `format` | `str | None` | — | format to use for the output |

### `commit`

[--dry-run] [(-c | -C | --squash) <commit> | --fixup [(amend|reword):]<commit>)] [-F <file> | -m <msg>] [--reset-author] [--allow-empty] [--allow-empty-message] [--no-verify] [-e] [--author=<author>] [--date=<date>] [--cleanup=<mode>] [--[no-]status] [-i | -o] [--pathspec-from-file=<file> [--pathspec-file-nul]] [(--trailer <token>[(=|:)<value>])...] [-S[<keyid>]] [--] [<pathspec>...]

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `pathspec` | `str | None` | — | Positional argument: pathspec |
| `quiet` | `bool | None` | — | suppress summary after successful commit |
| `verbose` | `bool | None` | — | show diff in commit message template |
| `file` | `str | None` | — | read message from file |
| `author` | `str | None` | — | override author for commit |
| `date` | `str | None` | — | override date for commit |
| `message` | `str | None` | — | commit message |
| `reedit_message` | `str | None` | — | reuse and edit message from specified commit |
| `reuse_message` | `str | None` | — | reuse message from specified commit |
| `squash` | `str | None` | — | use autosquash formatted message to squash specified commit |
| `reset_author` | `bool | None` | — | the commit is authored by me now (used with -C/-c/--amend) |
| `trailer` | `str | None` | — | add custom trailer(s) |
| `signoff` | `bool | None` | — | add a Signed-off-by trailer |
| `template` | `str | None` | — | use specified template file |
| `edit` | `bool | None` | — | force edit of commit |
| `status` | `bool | None` | — | include status in commit message template |
| `all` | `bool | None` | — | commit all changed files |
| `include` | `bool | None` | — | add specified files to index for commit |
| `interactive` | `bool | None` | — | interactively add files |
| `patch` | `bool | None` | — | interactively add changes |
| `only` | `bool | None` | — | commit only specified files |
| `no_verify` | `bool | None` | — | bypass pre-commit and commit-msg hooks |
| `verify` | `bool | None` | — | opposite of --no-verify |
| `dry_run` | `bool | None` | — | show what would be committed |
| `short` | `bool | None` | — | show status concisely |
| `branch` | `bool | None` | — | show branch information |
| `ahead_behind` | `bool | None` | — | compute full ahead/behind values |
| `porcelain` | `bool | None` | — | machine-readable output |
| `long` | `bool | None` | — | show status in long format (default) |
| `null` | `bool | None` | — | terminate entries with NUL |
| `amend` | `bool | None` | — | amend previous commit |
| `no_post_rewrite` | `bool | None` | — | bypass post-rewrite hook |
| `post_rewrite` | `bool | None` | — | opposite of --no-post-rewrite |
| `pathspec_from_file` | `str | None` | — | read pathspec from file |
| `pathspec_file_nul` | `bool | None` | — | with --pathspec-from-file, pathspec elements are separated with NUL character |

### `merge`

or: git merge --abort or: git merge --continue

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `commit` | `str | None` | — | Positional argument: commit |
| `n` | `bool | None` | — | do not show a diffstat at the end of the merge |
| `stat` | `bool | None` | — | show a diffstat at the end of the merge |
| `summary` | `bool | None` | — | (synonym to --stat) |
| `squash` | `bool | None` | — | create a single commit instead of doing a merge |
| `edit` | `bool | None` | — | edit message before committing |
| `ff` | `bool | None` | — | allow fast-forward (default) |
| `ff_only` | `bool | None` | — | abort if fast-forward is not possible |
| `rerere_autoupdate` | `bool | None` | — | update the index with reused conflict resolution if possible |
| `verify_signatures` | `bool | None` | — | verify that the named commit has a valid GPG signature |
| `strategy` | `str | None` | — | merge strategy to use |
| `message` | `str | None` | — | merge commit message (for a non-fast-forward merge) |
| `file` | `str | None` | — | read message from file |
| `into_name` | `str | None` | — | use <name> instead of the real target |
| `verbose` | `bool | None` | — | be more verbose |
| `quiet` | `bool | None` | — | be more quiet |
| `abort` | `bool | None` | — | abort the current in-progress merge |
| `quit` | `bool | None` | — | --abort but leave index and working tree alone |
| `continue_` | `bool | None` | — | continue the current in-progress merge |
| `allow_unrelated_histories` | `bool | None` | — | allow merging unrelated histories |
| `progress` | `bool | None` | — | force progress reporting |
| `autostash` | `bool | None` | — | automatically stash/stash pop before and after |
| `overwrite_ignore` | `bool | None` | — | update ignored files (default) |
| `signoff` | `bool | None` | — | add a Signed-off-by trailer |
| `no_verify` | `bool | None` | — | bypass pre-merge-commit and commit-msg hooks |
| `verify` | `bool | None` | — | opposite of --no-verify |

### `rebase`

or: git rebase [-i] [options] [--exec <cmd>] [--onto <newbase>] --root [<branch>] or: git rebase --continue | --abort | --skip | --edit-todo

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `branch` | `str | None` | — | Positional argument: branch |
| `no_verify` | `bool | None` | — | allow pre-rebase hook to run |
| `verify` | `bool | None` | — | opposite of --no-verify |
| `quiet` | `bool | None` | — | be quiet. implies --no-stat |
| `verbose` | `bool | None` | — | display a diffstat of what changed upstream |
| `no_stat` | `bool | None` | — | do not show diffstat of what changed upstream |
| `stat` | `bool | None` | — | opposite of --no-stat |
| `signoff` | `bool | None` | — | add a Signed-off-by trailer to each commit |
| `committer_date_is_author_date` | `bool | None` | — | make committer date match author date |
| `reset_author_date` | `bool | None` | — | ignore author date and use current date |
| `C` | `int | None` | — | passed to 'git apply' |
| `ignore_whitespace` | `bool | None` | — | ignore changes in whitespace |
| `whitespace` | `str | None` | — | passed to 'git apply' |
| `force_rebase` | `bool | None` | — | cherry-pick all commits, even if unchanged |
| `no_ff` | `bool | None` | — | cherry-pick all commits, even if unchanged |
| `ff` | `bool | None` | — | opposite of --no-ff |
| `continue_` | `bool | None` | — | continue |
| `skip` | `bool | None` | — | skip current patch and continue |
| `abort` | `bool | None` | — | abort and check out the original branch |
| `quit` | `bool | None` | — | abort but keep HEAD where it is |
| `edit_todo` | `bool | None` | — | edit the todo list during an interactive rebase |
| `show_current_patch` | `bool | None` | — | show the patch file being applied or merged |
| `apply` | `bool | None` | — | use apply strategies to rebase |
| `merge` | `bool | None` | — | use merging strategies to rebase |
| `interactive` | `bool | None` | — | let the user edit the list of commits to rebase |
| `rerere_autoupdate` | `bool | None` | — | update the index with reused conflict resolution if possible |
| `autosquash` | `bool | None` | — | move commits that begin with squash!/fixup! under -i |
| `update_refs` | `bool | None` | — | update branches that point to commits that are being rebased |
| `autostash` | `bool | None` | — | automatically stash/stash pop before and after |
| `exec` | `str | None` | — | add exec lines after each commit of the editable list |
| `fork_point` | `bool | None` | — | use 'merge-base --fork-point' to refine upstream |
| `strategy` | `str | None` | — | use the given merge strategy |
| `strategy_option` | `str | None` | — | pass the argument through to the merge strategy |
| `root` | `bool | None` | — | rebase all reachable commits up to the root(s) |
| `reschedule_failed_exec` | `bool | None` | — | automatically re-schedule any `exec` that fails |
| `reapply_cherry_picks` | `bool | None` | — | apply all changes, even those already present upstream |

### `reset`

or: git reset [-q] [<tree-ish>] [--] <pathspec>... or: git reset [-q] [--pathspec-from-file [--pathspec-file-nul]] [<tree-ish>] or: git reset --patch [<tree-ish>] [--] [<pathspec>...] or: DEPRECATED: git reset [-q] [--stdin [-z]] [<tree-ish>]

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `commit` | `str | None` | — | Positional argument: commit |
| `tree_ish` | `str | None` | — | Positional argument: tree_ish |
| `pathspec` | `str | None` | — | Positional argument: pathspec |
| `quiet` | `bool | None` | — | be quiet, only report errors |
| `no_refresh` | `bool | None` | — | skip refreshing the index after reset |
| `refresh` | `bool | None` | — | opposite of --no-refresh |
| `mixed` | `bool | None` | — | reset HEAD and index |
| `soft` | `bool | None` | — | reset only HEAD |
| `hard` | `bool | None` | — | reset HEAD, index and working tree |
| `merge` | `bool | None` | — | reset HEAD, index and working tree |
| `keep` | `bool | None` | — | reset HEAD but keep local changes |
| `patch` | `bool | None` | — | select hunks interactively |
| `intent_to_add` | `bool | None` | — | record only the fact that removed paths will be added later |
| `pathspec_from_file` | `str | None` | — | read pathspec from file |
| `pathspec_file_nul` | `bool | None` | — | with --pathspec-from-file, pathspec elements are separated with NUL character |
| `z` | `bool | None` | — | DEPRECATED (use --pathspec-file-nul instead): paths are separated with NUL character |
| `stdin` | `bool | None` | — | DEPRECATED (use --pathspec-from-file=- instead): read paths from <stdin> |

### `switch`

Switch branches

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `branch` | `str | None` | — | Positional argument: branch |
| `create` | `str | None` | — | create and switch to a new branch |
| `force_create` | `str | None` | — | create/reset and switch to a branch |
| `guess` | `bool | None` | — | second guess 'git switch <no-such-branch>' |
| `discard_changes` | `bool | None` | — | throw away local modifications |
| `quiet` | `bool | None` | — | suppress progress reporting |
| `progress` | `bool | None` | — | force progress reporting |
| `merge` | `bool | None` | — | perform a 3-way merge with the new branch |
| `conflict` | `str | None` | — | conflict style (merge, diff3, or zdiff3) |
| `detach` | `bool | None` | — | detach HEAD at named commit |
| `force` | `bool | None` | — | force checkout (throw away local modifications) |
| `orphan` | `str | None` | — | new unparented branch |
| `overwrite_ignore` | `bool | None` | — | update ignored files (default) |
| `ignore_other_worktrees` | `bool | None` | — | do not check if another worktree is holding the given ref |

### `tag`

<tagname> [<commit> | <object>] or: git tag -d <tagname>... or: git tag [-n[<num>]] -l [--contains <commit>] [--no-contains <commit>] [--points-at <object>] [--column[=<options>] | --no-column] [--create-reflog] [--sort=<key>] [--format=<format>] [--merged <commit>] [--no-merged <commit>] [<pattern>...] or: git tag -v [--format=<format>] <tagname>...

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `tagname` | `str | None` | — | Positional argument: tagname |
| `commit` | `str | None` | — | Positional argument: commit |
| `object` | `str | None` | — | Positional argument: object |
| `pattern` | `str | None` | — | Positional argument: pattern |
| `list` | `bool | None` | — | list tag names |
| `delete` | `bool | None` | — | delete tags |
| `verify` | `bool | None` | — | verify tags |
| `annotate` | `bool | None` | — | annotated tag, needs a message |
| `message` | `str | None` | — | tag message |
| `file` | `str | None` | — | read message from file |
| `edit` | `bool | None` | — | force edit of tag message |
| `sign` | `bool | None` | — | annotated and GPG-signed tag |
| `local_user` | `str | None` | — | use another key to sign the tag |
| `force` | `bool | None` | — | replace the tag if exists |
| `create_reflog` | `bool | None` | — | create a reflog |
| `contains` | `str | None` | — | print only tags that contain the commit |
| `no_contains` | `str | None` | — | print only tags that don't contain the commit |
| `merged` | `str | None` | — | print only tags that are merged |
| `no_merged` | `str | None` | — | print only tags that are not merged |
| `omit_empty` | `bool | None` | — | do not output a newline after empty formatted refs |
| `sort` | `str | None` | — | field name to sort on |
| `points_at` | `str | None` | — | print only tags of the object |
| `format` | `str | None` | — | format to use for the output |
| `ignore_case` | `bool | None` | — | sorting and filtering are case insensitive |

### `fetch`

or: git fetch [<options>] <group> or: git fetch --multiple [<options>] [(<repository> | <group>)...] or: git fetch --all [<options>]

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `repository` | `str | None` | — | Positional argument: repository |
| `refspec` | `str | None` | — | Positional argument: refspec |
| `group` | `str | None` | — | Positional argument: group |
| `verbose` | `bool | None` | — | be more verbose |
| `quiet` | `bool | None` | — | be more quiet |
| `all` | `bool | None` | — | fetch from all remotes |
| `set_upstream` | `bool | None` | — | set upstream for git pull/fetch |
| `append` | `bool | None` | — | append to .git/FETCH_HEAD instead of overwriting |
| `atomic` | `bool | None` | — | use atomic transaction to update references |
| `upload_pack` | `str | None` | — | path to upload pack on remote end |
| `force` | `bool | None` | — | force overwrite of local reference |
| `multiple` | `bool | None` | — | fetch from multiple remotes |
| `tags` | `bool | None` | — | fetch all tags and associated objects |
| `n` | `bool | None` | — | do not fetch all tags (--no-tags) |
| `jobs` | `int | None` | — | number of submodules fetched in parallel |
| `prefetch` | `bool | None` | — | modify the refspec to place all refs within refs/prefetch/ |
| `prune` | `bool | None` | — | prune remote-tracking branches no longer on remote |
| `dry_run` | `bool | None` | — | dry run |
| `porcelain` | `bool | None` | — | machine-readable output |
| `write_fetch_head` | `bool | None` | — | write fetched references to the FETCH_HEAD file |
| `keep` | `bool | None` | — | keep downloaded pack |
| `update_head_ok` | `bool | None` | — | allow updating of HEAD ref |
| `progress` | `bool | None` | — | force progress reporting |
| `depth` | `str | None` | — | deepen history of shallow clone |
| `shallow_since` | `str | None` | — | deepen history of shallow repository based on time |
| `shallow_exclude` | `str | None` | — | deepen history of shallow clone, excluding rev |
| `deepen` | `int | None` | — | deepen history of shallow clone |
| `unshallow` | `bool | None` | — | convert to a complete repository |
| `refetch` | `bool | None` | — | re-fetch without negotiating common commits |
| `refmap` | `str | None` | — | specify fetch refmap |
| `server_option` | `str | None` | — | option to transmit |
| `ipv4` | `bool | None` | — | use IPv4 addresses only |
| `ipv6` | `bool | None` | — | use IPv6 addresses only |
| `negotiation_tip` | `str | None` | — | report that we have only objects reachable from this object |
| `filter` | `str | None` | — | object filtering |
| `auto_maintenance` | `bool | None` | — | run 'maintenance --auto' after fetching |
| `auto_gc` | `bool | None` | — | run 'maintenance --auto' after fetching |
| `show_forced_updates` | `bool | None` | — | check for forced-updates on all updated branches |
| `write_commit_graph` | `bool | None` | — | write the commit-graph after fetching |
| `stdin` | `bool | None` | — | accept refspecs from stdin |

### `pull`

Fetch from and integrate with another repository or a local branch

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `repository` | `str | None` | — | Positional argument: repository |
| `refspec` | `str | None` | — | Positional argument: refspec |
| `verbose` | `bool | None` | — | be more verbose |
| `quiet` | `bool | None` | — | be more quiet |
| `progress` | `bool | None` | — | force progress reporting |
| `n` | `bool | None` | — | do not show a diffstat at the end of the merge |
| `stat` | `bool | None` | — | show a diffstat at the end of the merge |
| `squash` | `bool | None` | — | create a single commit instead of doing a merge |
| `commit` | `bool | None` | — | perform a commit if the merge succeeds (default) |
| `edit` | `bool | None` | — | edit message before committing |
| `ff` | `bool | None` | — | allow fast-forward |
| `ff_only` | `bool | None` | — | abort if fast-forward is not possible |
| `verify` | `bool | None` | — | control use of pre-merge-commit and commit-msg hooks |
| `verify_signatures` | `bool | None` | — | verify that the named commit has a valid GPG signature |
| `autostash` | `bool | None` | — | automatically stash/stash pop before and after |
| `strategy` | `str | None` | — | merge strategy to use |
| `allow_unrelated_histories` | `bool | None` | — | allow merging unrelated histories |
| `all` | `bool | None` | — | fetch from all remotes |
| `append` | `bool | None` | — | append to .git/FETCH_HEAD instead of overwriting |
| `upload_pack` | `str | None` | — | path to upload pack on remote end |
| `force` | `bool | None` | — | force overwrite of local branch |
| `tags` | `bool | None` | — | fetch all tags and associated objects |
| `prune` | `bool | None` | — | prune remote-tracking branches no longer on remote |
| `dry_run` | `bool | None` | — | dry run |
| `keep` | `bool | None` | — | keep downloaded pack |
| `depth` | `str | None` | — | deepen history of shallow clone |
| `shallow_since` | `str | None` | — | deepen history of shallow repository based on time |
| `shallow_exclude` | `str | None` | — | deepen history of shallow clone, excluding rev |
| `deepen` | `int | None` | — | deepen history of shallow clone |
| `unshallow` | `bool | None` | — | convert to a complete repository |
| `refmap` | `str | None` | — | specify fetch refmap |
| `server_option` | `str | None` | — | option to transmit |
| `ipv4` | `bool | None` | — | use IPv4 addresses only |
| `ipv6` | `bool | None` | — | use IPv6 addresses only |
| `negotiation_tip` | `str | None` | — | report that we have only objects reachable from this object |
| `show_forced_updates` | `bool | None` | — | check for forced-updates on all updated branches |
| `set_upstream` | `bool | None` | — | set upstream for git pull/fetch |

### `push`

Update remote refs along with associated objects

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `repository` | `str | None` | — | Positional argument: repository |
| `refspec` | `str | None` | — | Positional argument: refspec |
| `verbose` | `bool | None` | — | be more verbose |
| `quiet` | `bool | None` | — | be more quiet |
| `repo` | `str | None` | — | repository |
| `all` | `bool | None` | — | push all branches |
| `branches` | `bool | None` | — | alias of --all |
| `mirror` | `bool | None` | — | mirror all refs |
| `delete` | `bool | None` | — | delete refs |
| `tags` | `bool | None` | — | push tags (can't be used with --all or --branches or --mirror) |
| `dry_run` | `bool | None` | — | dry run |
| `porcelain` | `bool | None` | — | machine-readable output |
| `force` | `bool | None` | — | force updates |
| `force_if_includes` | `bool | None` | — | require remote updates to be integrated locally |
| `thin` | `bool | None` | — | use thin pack |
| `receive_pack` | `str | None` | — | receive pack program |
| `exec` | `str | None` | — | receive pack program |
| `set_upstream` | `bool | None` | — | set upstream for git pull/status |
| `progress` | `bool | None` | — | force progress reporting |
| `prune` | `bool | None` | — | prune locally removed refs |
| `no_verify` | `bool | None` | — | bypass pre-push hook |
| `verify` | `bool | None` | — | opposite of --no-verify |
| `follow_tags` | `bool | None` | — | push missing but relevant tags |
| `atomic` | `bool | None` | — | request atomic transaction on remote side |
| `push_option` | `str | None` | — | option to transmit |
| `ipv4` | `bool | None` | — | use IPv4 addresses only |
| `ipv6` | `bool | None` | — | use IPv6 addresses only |

---

## 7. Pièges courants

- **0 tools générés** : fournissez l'URL de la spec OpenAPI (`/openapi.json`) plutôt que l'URL de base de l'API.
- **401 Unauthorized** : vérifiez que votre clé est bien passée (header `Authorization: Bearer <clé>` ou `?token=<clé>` dans l'URL).
- **Timeout** : les générations complexes peuvent prendre jusqu'à 2 minutes, c'est normal.

---

Généré avec ❤️ par [mcp-forge](https://mcp-forge.vulcai.io)
