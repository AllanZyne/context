FILTERED_KEYS: frozenset[str] = frozenset({
    "PWD", "OLDPWD", "SHLVL", "_", "PPID",
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


def format_fish(added_or_changed: dict[str, str], removed: set[str]) -> str:
    """Stub — implemented in Task 6."""
    raise NotImplementedError("format_fish is implemented in Task 6")
