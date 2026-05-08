import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from ctx.emit import diff_env, format_bash, format_fish
from ctx.resolver import LeafNode


class RunnerError(Exception):
    """Raised for pre-execution errors (bad cwd, etc.)."""


def run_leaf(
    leaf: LeafNode,
    project_root: Path,
    shell: str,
    env_dump_path: Path | None,
) -> int:
    """
    Execute all commands in `leaf.run` under a single subprocess that
    matches the parent shell (`bash`, `zsh`, or `fish`). The YAML
    author writes commands in the same shell dialect as their
    interactive shell.

    If `leaf.source_rc` is true, the subprocess first sources the
    user's rc file for that shell (so functions / aliases / PATH from
    the rc are available to the command).

    If `env_dump_path` is given, writes the env writeback source (in
    `shell` syntax) to it on success. On failure the file is left
    untouched so shell wrappers skip sourcing.
    """
    cwd = _resolve_cwd(project_root, leaf.cwd)

    # env values are baseline (diff ignores them if the command doesn't
    # touch them). export values are applied to the subprocess env BUT
    # kept out of the baseline, so they always show up in the diff and
    # thus flow back to the parent shell.
    baseline_env = os.environ.copy()
    baseline_env.update(leaf.env)
    subprocess_env = baseline_env.copy()
    subprocess_env.update(leaf.export)

    commands = _substitute_args(leaf.run, leaf.args)

    # Tempfile for the subprocess to dump env -0 into.
    with tempfile.NamedTemporaryFile(
        prefix="ctx-raw-env-", delete=False
    ) as tmp:
        raw_env_path = Path(tmp.name)

    try:
        argv, script = _build_script(shell, commands, cwd, raw_env_path, leaf.source_rc)
        completed = subprocess.run(
            argv + [script],
            env=subprocess_env,
            cwd=cwd,
        )
        rc = completed.returncode

        if rc == 0 and env_dump_path is not None:
            final_env = _parse_env_nul(raw_env_path.read_bytes())
            added, removed = diff_env(baseline_env, final_env)
            # Only create env_dump_path when there is something to
            # write. The wrapper used `mktemp -u` so the path does not
            # exist yet; an empty diff means the wrapper finds nothing
            # to source AND nothing to rm.
            if added or removed:
                source = _format_for_shell(shell, added, removed)
                env_dump_path.write_text(source)

        return rc
    finally:
        try:
            raw_env_path.unlink()
        except FileNotFoundError:
            pass


_ARGS_PATTERN = re.compile(r"\{args(?:\|([^{}]*))?\}")


def _substitute_args(commands: list[str], args: list[str]) -> list[str]:
    """
    Replace every occurrence of {args} or {args|<default>} in each
    command. {args} → shlex.join(args) (empty string if no args).
    {args|foo bar} → "foo bar" when args is empty, else shlex.join(args).

    The default is inserted verbatim (not re-quoted) so the YAML author
    can control its shape directly. Inside the default, '{' and '}' are
    not allowed (the regex uses [^{}] to keep nesting out).
    """
    joined = shlex.join(args) if args else None

    def replace(match: re.Match[str]) -> str:
        if joined is not None:
            return joined
        default = match.group(1)
        return default if default is not None else ""

    return [_ARGS_PATTERN.sub(replace, cmd) for cmd in commands]


def _resolve_cwd(project_root: Path, cwd: str | None) -> Path:
    target = project_root if cwd is None else (project_root / cwd)
    target = target.resolve()
    if not target.is_dir():
        raise RunnerError(f"cwd does not exist: {target}")
    return target


# --- Per-shell script builders -------------------------------------------


def _build_script(
    shell: str,
    commands: list[str],
    cwd: Path,
    raw_env_path: Path,
    source_rc: bool,
) -> tuple[list[str], str]:
    """
    Return `(argv, script)` for the chosen shell. argv is the command
    to launch; script is the string piped in as `-c`.
    """
    if shell == "fish":
        return (["fish", "-c"], _build_fish_script(commands, cwd, raw_env_path, source_rc))
    if shell == "zsh":
        return (["zsh", "-c"], _build_bashlike_script("zsh", commands, cwd, raw_env_path, source_rc))
    # bash is the default for any other value (validation upstream limits
    # `shell` to bash/zsh/fish anyway).
    return (["bash", "-c"], _build_bashlike_script("bash", commands, cwd, raw_env_path, source_rc))


def _build_bashlike_script(
    shell: str,
    commands: list[str],
    cwd: Path,
    raw_env_path: Path,
    source_rc: bool,
) -> str:
    """
    Script for bash or zsh (POSIX-compatible enough for our needs).

    Order matters:
      1. cd into cwd (fail fast if broken — no `set -e` yet so rc can
         use idioms like `grep foo || true` without tripping).
      2. Source rc if requested. We swallow rc errors so a user with
         a noisy rc doesn't break ctx; a broken rc surfaces via the
         command's stderr below.
      3. `set -e` so the user's `run:` commands fail fast.
      4. Run commands, each preceded by a dim `$ cmd` echo.
      5. Dump env with `env -0` on success.
    """
    lines = [f"cd {shlex.quote(str(cwd))}"]
    if source_rc:
        rc_path = _rc_path_for(shell)
        # Quiet the rc: suppress its stdout/stderr so noisy prompts or
        # `fastfetch` calls don't pollute ctx output. Users who want to
        # see it can set source_rc: false and source explicitly.
        lines.append(f"[ -r {shlex.quote(str(rc_path))} ] "
                     f"&& . {shlex.quote(str(rc_path))} >/dev/null 2>&1 || true")
    lines.append("set -e")
    for cmd in commands:
        lines.append(f"printf '\\033[2m$ %s\\033[0m\\n' {shlex.quote(cmd)}")
        lines.append(cmd)
    lines.append(f"env -0 > {shlex.quote(str(raw_env_path))}")
    return "\n".join(lines) + "\n"


def _build_fish_script(
    commands: list[str],
    cwd: Path,
    raw_env_path: Path,
    source_rc: bool,
) -> str:
    """
    Script for fish. fish differs from bash/zsh:
      - No `set -e`; we propagate failures manually with `or exit $status`.
      - Its equivalent of `source ~/.bashrc` is simply `source
        ~/.config/fish/config.fish`. fish reads config.fish automatically
        on startup of an interactive shell BUT `fish -c "..."` is
        non-interactive and skips it, so source_rc=true still has work.
      - fish doesn't have `printf` built-in the same way; we use the
        standalone /usr/bin/printf (or whatever's on PATH), which is
        portable.
    """
    lines = [f"cd {_fish_single_quote(str(cwd))}"]
    if source_rc:
        rc_path = _rc_path_for("fish")
        lines.append(
            f"test -r {_fish_single_quote(str(rc_path))}; "
            f"and source {_fish_single_quote(str(rc_path))} "
            f">/dev/null 2>&1"
        )
    for cmd in commands:
        # Echo the command (dim) then run it, propagating non-zero.
        lines.append(
            f"printf '\\033[2m$ %s\\033[0m\\n' {_fish_single_quote(cmd)}"
        )
        lines.append(f"{cmd}")
        lines.append("or exit $status")
    lines.append(f"env -0 > {_fish_single_quote(str(raw_env_path))}")
    return "\n".join(lines) + "\n"


def _fish_single_quote(s: str) -> str:
    """fish single-quote a string. Inside '...' fish only needs to
    escape `\\` and `'`."""
    escaped = s.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _rc_path_for(shell: str) -> Path:
    """Canonical rc file for a given shell, rooted in $HOME."""
    home = Path(os.path.expanduser("~"))
    if shell == "zsh":
        # Respect $ZDOTDIR if set (zsh convention).
        zdotdir = os.environ.get("ZDOTDIR")
        return Path(zdotdir) / ".zshrc" if zdotdir else home / ".zshrc"
    if shell == "fish":
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else home / ".config"
        return base / "fish" / "config.fish"
    # bash
    return home / ".bashrc"


# --- env parsing ---------------------------------------------------------


def _parse_env_nul(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for chunk in data.split(b"\x00"):
        if not chunk:
            continue
        try:
            key, _, value = chunk.decode("utf-8", "replace").partition("=")
        except Exception:
            continue
        if key:
            result[key] = value
    return result


def _format_for_shell(
    shell: str,
    added: dict[str, str],
    removed: set[str],
) -> str:
    if shell == "fish":
        return format_fish(added, removed)
    # bash and zsh share the same output.
    return format_bash(added, removed)
