FILTERED_KEYS: frozenset[str] = frozenset({
    # Directory / process state that each shell manages for itself.
    "PWD", "OLDPWD", "SHLVL", "_", "PPID",
    # Interactive-shell variables that bash -c does not inherit;
    # without this, a no-op ctx call would emit spurious `unset`
    # lines and corrupt the user's prompt.
    "PS1", "PS2", "PS3", "PS4",
    "LINES", "COLUMNS",
    "BASH_ARGC", "BASH_ARGV", "BASH_LINENO", "BASH_SOURCE",
    "FUNCNAME", "GROUPS", "DIRSTACK",
})


def _is_internal(key: str) -> bool:
    return key in FILTERED_KEYS or key.startswith("_CTX_")


def diff_env(
    before: dict[str, str],
    after: dict[str, str],
) -> tuple[dict[str, str], set[str]]:
    """
    Returns ({added_or_changed_key: new_value}, {removed_keys}).
    Keys in FILTERED_KEYS or starting with _CTX_ are excluded.
    """
    added_or_changed: dict[str, str] = {}
    for k, v in after.items():
        if _is_internal(k):
            continue
        if before.get(k) != v:
            added_or_changed[k] = v
    removed = {
        k for k in before
        if k not in after and not _is_internal(k)
    }
    return added_or_changed, removed


def _bash_ansi_c_quote(value: str) -> str:
    """Return a bash $'...' ANSI-C-quoted string that is byte-safe."""
    out = []
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == "'":
            out.append("\\'")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7f:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return "$'" + "".join(out) + "'"


def format_bash(
    added_or_changed: dict[str, str],
    removed: set[str],
) -> str:
    """Emit bash/zsh source that, when sourced, applies the diff."""
    lines: list[str] = []
    for k in sorted(added_or_changed):
        lines.append(f"export {k}={_bash_ansi_c_quote(added_or_changed[k])}")
    for k in sorted(removed):
        lines.append(f"unset {k}")
    return "\n".join(lines) + ("\n" if lines else "")


def _fish_quote(value: str) -> str:
    """
    Quote `value` for fish.

    Simple case: if the value contains no control bytes, wrap in single
    quotes and escape `\\` and `'`.

    Control-byte case: split into safe single-quoted runs interleaved
    with \\xNN escapes outside quotes. fish concatenates adjacent tokens.
    """
    def has_control(s: str) -> bool:
        return any(ord(c) < 0x20 or ord(c) == 0x7f for c in s)

    if not has_control(value):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"

    parts: list[str] = []
    buf: list[str] = []
    for ch in value:
        if ord(ch) < 0x20 or ord(ch) == 0x7f:
            if buf:
                seg = "".join(buf).replace("\\", "\\\\").replace("'", "\\'")
                parts.append(f"'{seg}'")
                buf = []
            parts.append(f"\\x{ord(ch):02x}")
        else:
            buf.append(ch)
    if buf:
        seg = "".join(buf).replace("\\", "\\\\").replace("'", "\\'")
        parts.append(f"'{seg}'")
    return "".join(parts) if parts else "''"


def format_fish(
    added_or_changed: dict[str, str],
    removed: set[str],
) -> str:
    lines: list[str] = []
    for k in sorted(added_or_changed):
        lines.append(f"set -gx {k} {_fish_quote(added_or_changed[k])}")
    for k in sorted(removed):
        lines.append(f"set -e {k}")
    return "\n".join(lines) + ("\n" if lines else "")
