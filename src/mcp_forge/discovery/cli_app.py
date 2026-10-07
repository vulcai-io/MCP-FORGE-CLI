"""
Discovery à partir d'une application CLI locale.

Stratégie :
  1. Lancer <commande> --help pour obtenir la description globale
  2. Détecter les sous-commandes dans la sortie
  3. Pour chaque sous-commande, lancer <commande> <sous-cmd> --help
  4. Parser options/flags -> ToolParameter
  5. Chaque sous-commande -> un DiscoveredTool
"""
from __future__ import annotations

import keyword
import re
import shlex
import subprocess
from dataclasses import dataclass, field

from rich.console import Console

from mcp_forge.models import (
    AuthScheme,
    AuthType,
    DiscoveredTool,
    DiscoveryResult,
    ForgeConfig,
    ParameterType,
    SourceType,
    ToolParameter,
)

console = Console()

_MAX_DEPTH = 2
_TIMEOUT = 10

_SUBCOMMAND_PATTERNS = [
    re.compile(r"^\s{2,4}([a-z][a-z0-9_-]+)\s{2,}(.+)$", re.MULTILINE),
    re.compile(r"^\s{2,4}([a-z][a-z0-9_-]+)\s*$", re.MULTILINE),
]

_OPTION_PATTERN = re.compile(
    r"(?:^|\s)"
    # `*` (pas `?`) : certains outils documentent 3 alias ou plus sur la même
    # entrée (ex: sed "-n, --quiet, --silent") — un seul "?" ne consommait
    # que le premier alias longue-forme et cassait le match entier.
    r"(-[a-zA-Z](?:,\s*--[a-z][a-z0-9_-]*)*"
    r"|--[a-z][a-z0-9_-]*)"
    r"(?:[ \t]+([A-Z_]+|\[.*?\]|<[a-zA-Z][a-zA-Z0-9_-]*>))?"
    # Séparateur et fin de description restreints à l'espace horizontal :
    # `\s` engloberait aussi le saut de ligne, ce qui laisserait une entrée
    # sans description sur SA propre ligne "avaler" toute la ligne suivante
    # (donc une autre option entière) comme si c'était sa description.
    r"[ \t]{2,}(.+?)(?=[ \t]{2,}-|\n|$)",
    re.MULTILINE,
)

# Détecte le début d'une entrée d'option (flag indenté en tête de ligne),
# utilisé pour recoller les entrées sur 2 lignes (flag seul, description sur
# la ligne suivante — cf. `_merge_wrapped_option_lines`).
_FLAG_START_RE = re.compile(r"^(\s{1,8})(-[a-zA-Z][^\s]*|--[a-zA-Z][^\s]*)")

_SUBCOMMAND_SECTION_HEADERS = re.compile(
    r"^(?:available\s+)?(?:commands?|subcommands?|actions?)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_VALUE_TYPE_MAP: dict[str, ParameterType] = {
    "FILE": ParameterType.STRING,
    "PATH": ParameterType.STRING,
    "DIR": ParameterType.STRING,
    "URL": ParameterType.STRING,
    "TEXT": ParameterType.STRING,
    "STRING": ParameterType.STRING,
    "STR": ParameterType.STRING,
    "NAME": ParameterType.STRING,
    "INT": ParameterType.INTEGER,
    "INTEGER": ParameterType.INTEGER,
    "N": ParameterType.INTEGER,
    "NUM": ParameterType.INTEGER,
    "NUMBER": ParameterType.INTEGER,
    "FLOAT": ParameterType.NUMBER,
}

_RESERVED_WORDS = {
    "help", "version", "options", "flags", "arguments", "usage",
    "global", "commands", "subcommands", "available",
}

# Placeholders génériques dans une synopsis (ex: `[<options>]`) qui ne
# représentent aucun argument positionnel réel — juste "des flags vont ici".
_POSITIONAL_PLACEHOLDER_WORDS = {"options", "option", "opts", "flags", "args", "arg"}


@dataclass
class _CLICommand:
    name: str
    args: list[str]
    description: str = ""
    options: list[ToolParameter] = field(default_factory=list)


class CLIAppDiscovery:
    def __init__(self, config: ForgeConfig):
        self.config = config
        self.cmd_parts = shlex.split(config.source)

    def discover(self) -> DiscoveryResult:
        console.print("[bold]>> Analyse de l'application CLI...[/bold]")

        root_help = self._run_help(self.cmd_parts)
        if root_help is None:
            raise ValueError(f"Impossible de lancer '{' '.join(self.cmd_parts)} --help'")

        title, root_description = self._parse_header(root_help)
        title = title or self.cmd_parts[-1]

        subcommands = self._detect_subcommands(root_help)
        console.print(f"[dim]  {len(subcommands)} sous-commande(s) détectée(s)[/dim]")

        tools: list[DiscoveredTool] = []

        if subcommands:
            for sub_name, sub_desc in subcommands:
                cmd_args = self.cmd_parts + [sub_name]
                sub_help = self._run_help(cmd_args)
                _, detailed_desc = self._parse_header(sub_help or "")
                options, flags = self._parse_options(sub_help or "")

                # Niveau 2 : sous-sous-commandes (ex: git remote add)
                if sub_help and _MAX_DEPTH >= 2:
                    nested = self._detect_subcommands(sub_help)
                    for nested_name, nested_desc in nested:
                        nested_args = cmd_args + [nested_name]
                        nested_help = self._run_help(nested_args)
                        _, nested_detailed = self._parse_header(nested_help or "")
                        nested_opts, nested_flags = self._parse_options(nested_help or "")
                        tools.append(self._build_tool(
                            name=f"{sub_name}_{nested_name}",
                            cmd_args=nested_args,
                            description=nested_detailed or nested_desc or f"{sub_name} {nested_name}",
                            options=nested_opts,
                            param_flags=nested_flags,
                        ))

                tools.append(self._build_tool(
                    name=sub_name,
                    cmd_args=cmd_args,
                    description=detailed_desc or sub_desc or sub_name,
                    options=options,
                    param_flags=flags,
                ))
        else:
            # Pas de sous-commandes : la commande entière est un tool
            options, flags = self._parse_options(root_help)
            tools.append(self._build_tool(
                name=self._normalize_name(title),
                cmd_args=self.cmd_parts,
                description=root_description or title,
                options=options,
                param_flags=flags,
            ))

        console.print(f"[green][OK] {len(tools)} outil(s) MCP extrait(s)[/green]")

        auth_schemes = self._detect_auth(root_help)

        return DiscoveryResult(
            source_type=SourceType.CLI_APP,
            source_path=self.config.source,
            title=title,
            description=root_description,
            tools=tools,
            auth_schemes=auth_schemes,
        )

    # ------------------------------------------------------------------
    # Détection de l'authentification
    # ------------------------------------------------------------------

    # Flags CLI indiquant un token/clé d'API (Bearer)
    _AUTH_FLAG_RE = re.compile(r"--(?:token|api.key|access.token|auth.token|bearer)\b", re.IGNORECASE)
    # Flags indiquant des credentials OAuth2
    _OAUTH_FLAG_RE = re.compile(r"--client.(?:id|secret)\b", re.IGNORECASE)
    # Flags Basic Auth
    _BASIC_FLAG_RE = re.compile(r"--(?:username|password|user|pass)\b", re.IGNORECASE)

    def _detect_auth(self, help_text: str | None) -> list[AuthScheme]:
        """Détecte le type d'auth depuis les flags globaux de la CLI."""
        if not help_text:
            return []

        if self._OAUTH_FLAG_RE.search(help_text):
            return [AuthScheme(type=AuthType.OAUTH2, param_name="Authorization",
                               param_in="header", env_var="OAUTH2_TOKEN")]
        if self._BASIC_FLAG_RE.search(help_text):
            return [AuthScheme(type=AuthType.BASIC, param_name="Authorization",
                               param_in="header", env_var="BASIC_AUTH")]
        if self._AUTH_FLAG_RE.search(help_text):
            return [AuthScheme(type=AuthType.BEARER, param_name="Authorization",
                               param_in="header", env_var="BEARER_TOKEN")]
        return []

    # ------------------------------------------------------------------
    # Exécution subprocess
    # ------------------------------------------------------------------

    def _run_help(self, cmd_args: list[str]) -> str | None:
        for help_flag in ["--help", "-h"]:
            try:
                result = subprocess.run(
                    cmd_args + [help_flag],
                    capture_output=True,
                    text=True,
                    timeout=_TIMEOUT,
                )
                output = result.stdout or result.stderr
                if output.strip():
                    return output
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
            except Exception:
                continue
        # Essai avec "help" comme sous-commande (ex: git help commit)
        try:
            result = subprocess.run(
                [cmd_args[0], "help"] + cmd_args[1:],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
            output = result.stdout or result.stderr
            if output.strip():
                return output
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_header(self, help_text: str) -> tuple[str, str]:
        lines = [ln.rstrip() for ln in help_text.splitlines() if ln.strip()]
        title = lines[0].strip() if lines else ""
        title = re.sub(r"^(?:usage|name)\s*:?\s*", "", title, flags=re.IGNORECASE).strip()
        desc_lines = []
        for line in lines[1:]:
            if re.match(r"^[A-Z][A-Z\s]+:$", line.strip()):
                break
            if line.strip().startswith("-"):
                break
            desc_lines.append(line.strip())
        return title, " ".join(ln for ln in desc_lines if ln)

    def _detect_subcommands(self, help_text: str) -> list[tuple[str, str]]:
        section_match = _SUBCOMMAND_SECTION_HEADERS.search(help_text)
        search_text = help_text[section_match.end():] if section_match else help_text

        found: dict[str, str] = {}
        for pattern in _SUBCOMMAND_PATTERNS:
            for m in pattern.finditer(search_text):
                name = m.group(1)
                desc = m.group(2).strip() if len(m.groups()) > 1 else ""
                if name not in _RESERVED_WORDS and name not in found:
                    found[name] = desc
        return list(found.items())

    _USAGE_PREFIX_RE = re.compile(r"^\s*(?:usage|or)\s*:\s*", re.IGNORECASE)

    # Deux conventions courantes pour documenter un argument positionnel :
    #   - `<nom>` / `[<nom>]`           (git, npm, curl, la plupart des CLI POSIX récentes)
    #   - `NOM` / `[NOM]` / `NOM...`    (GNU coreutils : grep PATTERN, tar [FILE]..., sort [FILE]...)
    # Les deux sont cherchées par token ; le premier groupe qui matche gagne.
    _POSITIONAL_TOKEN_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9_-]*)>|\b([A-Z][A-Z0-9_]+)\b")
    _FLAG_RE = re.compile(r"^--?[a-zA-Z]")

    @classmethod
    def _extract_positional_args(cls, help_text: str) -> list[tuple[str, bool]]:
        """Détecte les arguments positionnels depuis la ligne de synopsis
        ("usage: ..."), dans l'ordre d'apparition.

        Best-effort, deux conventions reconnues (voir `_POSITIONAL_TOKEN_RE`).
        Un token sans crochets englobants est requis, `[...]` est optionnel.
        Un token qui est la valeur d'un flag (`-m <msg>`, `--cleanup=<mode>`,
        `-u<mode>`, `--file FILE`) est ignoré — ce n'est pas un positional
        indépendant. Les placeholders génériques (`[<options>]`, `[OPTION]...`)
        sont filtrés. Ne prétend pas couvrir toutes les conventions CLI
        existantes ; retourne une liste vide si rien de reconnaissable n'est
        trouvé plutôt que de deviner au hasard."""
        lines = help_text.splitlines()
        # Une "forme" = une ligne "usage:"/"or:" éventuellement suivie de
        # lignes de continuation indentées (ex: `git tag`, `git commit`) —
        # celles-ci sont rattachées (concaténées) à la forme en cours, pas
        # traitées comme des formes séparées. Nécessaire pour deux raisons :
        # (1) une parenthèse/crochet ouvert sur une ligne et fermé sur la
        # continuation suivante serait mal compté si on repartait de
        # profondeur 0 à chaque ligne physique ; (2) un token qui n'apparaît
        # que sur la continuation (ex: `<tagname>` après le `usage:` de
        # `git tag`) doit compter comme faisant partie de LA MÊME forme que
        # le `usage:` précédent, pas une forme distincte où il serait seul.
        usage_lines: list[str] = []
        started = False
        for line in lines:
            stripped = line.strip()
            if not started:
                if cls._USAGE_PREFIX_RE.match(stripped):
                    started = True
                    content = cls._USAGE_PREFIX_RE.sub("", stripped)
                    if content:
                        usage_lines.append(content)
                    # sinon "Usage:" est seul sur sa ligne (ex: npm) — la
                    # commande elle-même suit sur la ligne d'après, sans
                    # forcément être indentée ; on l'acceptera ci-dessous
                    # puisque `usage_lines` est encore vide.
                continue
            if not stripped or stripped.startswith("-"):
                break  # ligne vide ou début de la liste des options : fin du synopsis
            is_new_form = bool(cls._USAGE_PREFIX_RE.match(stripped))
            indent = len(line) - len(line.lstrip())
            if usage_lines and indent == 0 and not is_new_form:
                # Une fois qu'on a déjà du contenu de synopsis, une ligne non
                # indentée (et qui n'introduit pas une nouvelle forme "or:")
                # est un texte de description (ex: "Search for PATTERN...").
                break
            content = cls._USAGE_PREFIX_RE.sub("", stripped) if is_new_form else stripped
            if is_new_form or not usage_lines:
                usage_lines.append(content)
            else:
                usage_lines[-1] = usage_lines[-1] + " " + content
        if not usage_lines:
            return []

        # Un positional n'est requis globalement que s'il est requis dans
        # TOUTES les formes où il apparaît, ET qu'il apparaît dans TOUTES
        # les formes (pas seulement certaines) — sinon il existe au moins
        # une façon valide d'appeler la commande sans lui, donc il doit
        # être optionnel. Avant ce fix, seule la PREMIÈRE forme rencontrée
        # décidait (via un `seen` global), ce qui rendait `git log`/`diff`/
        # `fetch`/`branch`/`reset` obligatoires sur un argument alors que
        # leur forme la plus courante (sans cet argument) est parfaitement
        # valide — bug réel signalé par l'évaluateur qualité.
        order: list[str] = []
        per_form_required: dict[str, list[bool]] = {}
        for usage_line in usage_lines:
            tokens = usage_line.split()
            depth = 0
            form_seen: set[str] = set()
            for i, tok in enumerate(tokens):
                m = cls._POSITIONAL_TOKEN_RE.search(tok)
                if m:
                    raw = m.group(1) or m.group(2)
                    prefix = tok[:m.start()]
                    is_label = m.group(2) and tok[m.end():].startswith(":")
                    if "-" in prefix or is_label:
                        # valeur attachée au flag (--cleanup=<mode>, -u<mode>) ou
                        # préfixe-étiquette de type "DEPRECATED: git reset ..."
                        pass
                    else:
                        prev_raw = tokens[i - 1] if i > 0 else ""
                        prev = prev_raw.strip("[]()")
                        # "prev" ne consomme la valeur courante que s'il s'agit d'un
                        # flag "nu" (pas déjà pourvu d'une valeur via = ou <...>) ET
                        # que ce flag n'est pas déjà un groupe optionnel COMPLET en
                        # lui-même (ex: "[-e]", ouvert ET fermé dans le même token) —
                        # sinon rien n'indique qu'il "attend" une valeur, le token
                        # suivant est un positional indépendant. Sans cette
                        # distinction, fusionner les lignes de continuation (voir
                        # plus haut) faisait percuter un <nom> débutant sa PROPRE
                        # ligne contre le "[-x]" de la ligne précédente, l'avalant
                        # à tort comme si c'était sa valeur (ex: `git tag`, où
                        # <tagname> suit "[-e]" sur la ligne suivante).
                        prev_self_contained = prev_raw.startswith("[") and prev_raw.endswith("]")
                        prev_is_bare_flag = (
                            cls._FLAG_RE.match(prev) and "<" not in prev and "=" not in prev
                            and not prev_self_contained
                        )
                        if not prev_is_bare_flag:
                            name = raw.replace("-", "_").lower()
                            if not (keyword.iskeyword(name) or name in form_seen
                                    or name in _POSITIONAL_PLACEHOLDER_WORDS):
                                form_seen.add(name)
                                local_depth = depth + prefix.count("[") - prefix.count("]")
                                if name not in per_form_required:
                                    order.append(name)
                                    per_form_required[name] = []
                                per_form_required[name].append(local_depth <= 0)
                depth += tok.count("[") - tok.count("]")

        num_forms = len(usage_lines)
        return [
            (name, len(per_form_required[name]) == num_forms and all(per_form_required[name]))
            for name in order
        ]

    @staticmethod
    def _merge_wrapped_option_lines(help_text: str) -> str:
        """Prépare le texte d'aide pour le parseur d'options mono-ligne :

        1. Retire l'idiome git `--[no-]xxx` (bascule bool/valeur documentée
           en une seule entrée) pour obtenir `--xxx`, une forme de flag
           standard. Sans ça, la quasi-totalité des flags booléens de git
           (`--[no-]verbose`, `--[no-]bare`, ...) sont invisibles : les
           crochets littéraux cassent le pattern `--[a-z][a-z0-9_-]*`.
        2. Recolle les entrées d'option étalées sur 2 lignes (flag seul sur
           la 1ère ligne, description sur la 2e, plus indentée — ex:
           "-m, --message <message>\\n    commit message") en une seule
           ligne, pour que le parseur existant (mono-ligne) les détecte.
        """
        text = re.sub(r"\[no-\]", "", help_text)
        lines = text.splitlines()
        merged: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            m = _FLAG_START_RE.match(line)
            if m and i + 1 < len(lines):
                indent = len(m.group(1))
                rest = line[m.end():]
                has_same_line_desc = bool(re.search(r"\s{2,}\S", rest))
                if not has_same_line_desc:
                    next_line = lines[i + 1]
                    next_stripped = next_line.strip()
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if (next_stripped and next_indent > indent
                            and not _FLAG_START_RE.match(next_line)):
                        line = line.rstrip() + "  " + next_stripped
                        i += 1
            merged.append(line)
            i += 1
        return "\n".join(merged)

    def _parse_options(self, help_text: str) -> tuple[list[ToolParameter], dict[str, str]]:
        """Retourne (params, param_flags) où param_flags mappe nom_python >> flag_cli."""
        params: list[ToolParameter] = []
        param_flags: dict[str, str] = {}
        seen: set[str] = set()

        for name, required in self._extract_positional_args(help_text):
            if name in seen:
                continue
            seen.add(name)
            params.append(ToolParameter(
                name=name,
                type=ParameterType.STRING,
                description=f"Positional argument: {name}",
                required=required,
                default=None if required else "",
                param_in="positional",
            ))

        # Ignore le bloc de synopsis ("usage: ...") avant de chercher des
        # options : une ligne comme "or: git diff [...] --cached [...]"
        # peut sinon être faussement reconnue comme une entrée d'option.
        lines = help_text.splitlines()
        first_flag_idx = next((i for i, ln in enumerate(lines) if _FLAG_START_RE.match(ln)), 0)
        options_section = "\n".join(lines[first_flag_idx:])

        merged_help_text = self._merge_wrapped_option_lines(options_section)
        for m in _OPTION_PATTERN.finditer(merged_help_text):
            flag = m.group(1).strip()
            value_hint = (m.group(2) or "").strip()
            description = (m.group(3) or "").strip()

            if "--" in flag:
                # Forme longue prioritaire pour le nom Python, même si une
                # forme courte est aussi présente (ex: "-v, --verbose").
                raw_name = flag.rsplit("--", 1)[-1].strip().replace("-", "_")
                has_long = True
            elif flag.startswith("-") and len(flag) == 2:
                raw_name = flag[1:]
                has_long = False
            else:
                continue

            # Le seuil de longueur ne s'applique qu'aux noms dérivés d'une
            # forme longue (garde-fou contre un mauvais parsing) : un flag
            # purement court fait toujours 1 caractère par construction
            # (ex: "-x"), ce n'est pas un signe d'erreur ici.
            if raw_name in seen or (has_long and len(raw_name) < 2):
                continue

            # Sanitise les mots-clés Python (and, or, continue, etc.)
            name = f"{raw_name}_" if keyword.iskeyword(raw_name) else raw_name
            original_flag = f"--{raw_name.replace('_', '-')}" if has_long else f"-{raw_name}"
            if name != raw_name or not has_long:
                param_flags[name] = original_flag

            seen.add(raw_name)

            if value_hint:
                hint_clean = value_hint.strip("<>[]")
                ptype = _VALUE_TYPE_MAP.get(hint_clean.upper(), ParameterType.STRING)
                # Une valeur entre crochets — carrés `[...]` ou chevrons
                # `<...>` — est optionnelle par convention ; seule une
                # forme ALLCAPS nue (ex: "--output FILE") est traitée
                # comme obligatoire dès que le flag est utilisé.
                required = value_hint[0] not in "[<"
            else:
                ptype = ParameterType.BOOLEAN
                required = False

            default = None
            dm = re.search(r"\(default[=:\s]+([^)]+)\)", description, re.IGNORECASE)
            if dm:
                default = dm.group(1).strip()

            params.append(ToolParameter(
                name=name,
                type=ptype,
                description=description,
                required=required,
                default=default,
            ))

        return params, param_flags

    # ------------------------------------------------------------------
    # Construction du tool
    # ------------------------------------------------------------------

    def _build_tool(
        self,
        name: str,
        cmd_args: list[str],
        description: str,
        options: list[ToolParameter],
        param_flags: dict[str, str] | None = None,
    ) -> DiscoveredTool:
        return DiscoveredTool(
            name=self._normalize_name(name),
            description=description,
            parameters=options,
            tags=["cli"],
            metadata={"cmd": cmd_args, "param_flags": param_flags or {}},
        )

    @staticmethod
    def _normalize_name(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
