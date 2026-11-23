"""Read a shell command line the way a guard needs to: which programs run, with which arguments.

Stdlib only. Not a shell: it never expands variables or globs and never runs anything. It splits a
command into simple commands, drops heredoc bodies and comments, keeps quoted text as one argument
(so a flag-shaped word inside a commit message is an argument value, not a flag), looks inside
`$(...)`, backticks, `bash -c '...'` and `eval`, and strips runner prefixes (`env`, `sudo`,
`timeout`, ...). What it cannot see (variables, globs, scripts piped into a shell) stays unseen;
the Stop-time diff check is the authority for those.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_DEPTH = 3
SEPARATORS = {";", "&&", "||", "|", "|&", "&", "(", ")", "\n"}
OUT_REDIRECTS = {">", ">>", ">|", "&>", "&>>"}
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
# runner prefixes: name -> options that take a value
WRAPPERS = {
    "sudo": {"-u", "-g", "-C", "-h", "-p", "-U"}, "env": {"-u", "-C", "-S"}, "nice": {"-n"},
    "ionice": {"-c", "-n", "-p"}, "timeout": {"-s", "-k"}, "nohup": set(), "time": set(),
    "command": set(), "exec": {"-a"}, "builtin": set(), "stdbuf": {"-i", "-o", "-e"},
    "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-a", "-E"}, "setsid": set(), "chronic": set(),
}


@dataclass
class Simple:
    """One simple command: `A=1 prog arg ... > out`."""
    argv: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    writes: list[str] = field(default_factory=list)   # targets of output redirections
    reads: list[str] = field(default_factory=list)    # targets of input redirections

    @property
    def prog(self) -> str:
        return self.argv[0].rsplit("/", 1)[-1] if self.argv else ""


def _lex(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Tokens as (kind, text) with kind 'w' (word) or 'o' (operator), plus the bodies of command
    substitutions found on the way. Never raises: an unterminated quote runs to the end."""
    tokens: list[tuple[str, str]] = []
    subs: list[str] = []
    word: list[str] = []
    in_word = False
    heredocs: list[tuple[str, bool]] = []
    i, n = 0, len(text)

    def flush() -> None:
        nonlocal in_word
        if in_word:
            tokens.append(("w", "".join(word)))
            word.clear()
            in_word = False

    def matching_paren(start: int) -> int:
        depth, j, quote = 1, start, ""
        while j < n:
            c = text[j]
            if quote:
                if c == "\\" and quote == '"':
                    j += 1
                elif c == quote:
                    quote = ""
            elif c in "'\"":
                quote = c
            elif c == "\\":
                j += 1
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return j
            j += 1
        return n

    def substitution(j: int) -> int:
        """`text[j]` is the `(` of `$(`; record the body, return the index after the `)`."""
        end = matching_paren(j + 1)
        subs.append(text[j + 1:end])
        return end + 1

    while i < n:
        c = text[i]
        if c == "\n":
            flush()
            tokens.append(("o", "\n"))
            i += 1
            for delimiter, strip_tabs in heredocs:  # the bodies start on the next line
                while i < n:
                    end = text.find("\n", i)
                    end = n if end < 0 else end
                    line = text[i:end]
                    i = min(end + 1, n)
                    if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                        break
            heredocs.clear()
            continue
        if c in " \t":
            flush()
            i += 1
            continue
        if c == "#" and not in_word:
            end = text.find("\n", i)
            i = n if end < 0 else end
            continue
        if c == "\\":
            if i + 1 < n and text[i + 1] == "\n":
                i += 2
                continue
            word.append(text[i + 1:i + 2])
            in_word = True
            i += 2
            continue
        if c == "'":
            end = text.find("'", i + 1)
            end = n if end < 0 else end
            word.append(text[i + 1:end])
            in_word = True
            i = end + 1
            continue
        if c == '"':
            in_word = True
            i += 1
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    word.append(text[i + 1])
                    i += 2
                elif text.startswith("$(", i):
                    i = substitution(i + 1)
                elif text[i] == "`":
                    end = text.find("`", i + 1)
                    end = n if end < 0 else end
                    subs.append(text[i + 1:end])
                    i = end + 1
                else:
                    word.append(text[i])
                    i += 1
            i += 1
            continue
        if text.startswith("$(", i):
            in_word = True
            i = substitution(i + 1)
            continue
        if c == "`":
            end = text.find("`", i + 1)
            end = n if end < 0 else end
            subs.append(text[i + 1:end])
            in_word = True
            i = end + 1
            continue
        if text.startswith(("<(", ">("), i):
            in_word = True
            i = substitution(i + 1)
            continue
        if text.startswith("<<", i) and not text.startswith("<<<", i):
            flush()
            i += 2
            strip_tabs = text.startswith("-", i)
            i += strip_tabs
            match = re.match(r"[ \t]*(['\"]?)([^\s'\"<>|;&()]+)\1", text[i:])
            if match:
                heredocs.append((match[2].lstrip("\\"), strip_tabs))
                i += match.end()
            continue
        matched = next((op for op in ("&>>", "<<<", "&&", "||", "|&", "&>", ">>", ">|", ">&", "<&",
                                      ";", "|", "&", "(", ")", ">", "<") if text.startswith(op, i)), None)
        if matched:
            if matched in (">", ">>", ">|", ">&", "<", "<&") and in_word and "".join(word).isdigit():
                word.clear()  # the fd number of `2>file`
                in_word = False
            flush()
            tokens.append(("o", matched))
            i += len(matched)
            continue
        word.append(c)
        in_word = True
        i += 1
    flush()
    return tokens, subs


def _unwrap(argv: list[str], env: dict[str, str]) -> list[str]:
    """Drop runner prefixes so argv[0] is the program that does the work."""
    while argv:
        name = argv[0].rsplit("/", 1)[-1]
        if name not in WRAPPERS:
            return argv
        takes_value = WRAPPERS[name]
        i = 1
        while i < len(argv):
            arg = argv[i]
            if name == "env" and ASSIGN.match(arg):
                key, _, value = arg.partition("=")
                env[key] = value
            elif arg.startswith("-") and arg != "-":
                if arg in takes_value:
                    i += 1
            elif name == "timeout" and re.fullmatch(r"[\d.]+[smhd]?", arg):
                pass
            else:
                break
            i += 1
        argv = argv[i:]
    return argv


def parse(command: str, _depth: int = 0) -> list[Simple]:
    """Every simple command in `command`, including those in substitutions and `sh -c` bodies."""
    if _depth > MAX_DEPTH or not isinstance(command, str):
        return []
    tokens, subs = _lex(command)
    out: list[Simple] = []
    current = Simple()
    pending = ""  # a redirection operator waiting for its target

    def close() -> None:
        nonlocal current
        if current.argv or current.env or current.writes or current.reads:
            current.argv = _unwrap(current.argv, current.env)
            out.append(current)
            out.extend(_nested(current, _depth))
        current = Simple()

    for kind, text in tokens:
        if kind == "o":
            if text in SEPARATORS:
                close()
                pending = ""
            else:
                pending = text
            continue
        if pending:
            if pending in OUT_REDIRECTS:
                current.writes.append(text)
            elif pending in ("<", "<<<"):
                if pending == "<":
                    current.reads.append(text)
            pending = ""
            continue
        if not current.argv and ASSIGN.match(text):
            key, _, value = text.partition("=")
            current.env[key] = value
            continue
        current.argv.append(text)
    close()
    for body in subs:
        out.extend(parse(body, _depth + 1))
    return out


def _nested(cmd: Simple, depth: int) -> list[Simple]:
    """Commands hidden in the arguments of a shell or `eval`."""
    if cmd.prog == "eval":
        return parse(" ".join(cmd.argv[1:]), depth + 1)
    if cmd.prog in SHELLS:
        for i, arg in enumerate(cmd.argv[1:], start=1):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", arg) and i + 1 < len(cmd.argv):
                return parse(cmd.argv[i + 1], depth + 1)
    return []


# ---------------------------------------------------------------- git

GIT_GLOBAL_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix",
                    "--config-env", "--list-cmds", "--attr-source"}


@dataclass
class Git:
    sub: str
    args: list[str]             # everything after the subcommand
    config: list[str]           # `-c key=value` overrides, lowercased keys
    directory: str | None = None


def git_call(cmd: Simple) -> Git | None:
    """The git subcommand of a simple command, skipping git's own global options."""
    if cmd.prog != "git":
        return None
    argv, config, directory, i = cmd.argv, [], None, 1
    while i < len(argv):
        arg = argv[i]
        if arg in GIT_GLOBAL_VALUE and i + 1 < len(argv):
            if arg == "-c":
                config.append(argv[i + 1])
            elif arg == "-C":
                directory = argv[i + 1]
            i += 2
        elif arg.startswith("-c") and "=" in arg and not arg.startswith("--"):
            config.append(arg[2:])
            i += 1
        elif arg.startswith("-"):
            i += 1
        else:
            keys = [c.partition("=")[0].lower() + "=" + c.partition("=")[2] for c in config]
            return Git(arg, argv[i + 1:], keys, directory)
    return None


def options(args: list[str], short_value: str = "", long_value: tuple[str, ...] = ()) -> tuple[set[str], list[str], list[str]]:
    """Split arguments into (short flag letters, long options without values, positionals).

    `short_value` lists the short options that take a value (`-m msg`, `-mmsg`); `long_value` the long
    ones (`--message msg`). Their values are skipped, so a value that looks like a flag is not one.
    Everything after `--` is positional.
    """
    shorts: set[str] = set()
    longs: list[str] = []
    positional: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            positional.extend(args[i + 1:])
            break
        if arg.startswith("--"):
            name = arg.partition("=")[0]
            longs.append(name)
            if "=" not in arg and any(full.startswith(name) for full in long_value):
                i += 1
        elif arg.startswith("-") and len(arg) > 1:
            for j, letter in enumerate(arg[1:], start=1):
                if letter in short_value:
                    if j == len(arg) - 1:
                        i += 1  # the value is the next argument
                    break
                shorts.add(letter)
        else:
            positional.append(arg)
        i += 1
    return shorts, longs, positional


def has_long(longs: list[str], full: str, minimum: int) -> bool:
    """True when one of `longs` is `full` or an abbreviation of it git would accept."""
    return any(full.startswith(name) and len(name) >= minimum for name in longs)
