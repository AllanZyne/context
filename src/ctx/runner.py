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
    source_script_path: Path | None = None,
) -> int:
    """
    Dispatch on leaf.mode.

    mode="source" (default):
      Generate a shell script and write it to `source_script_path` for
      the wrapper to source in the parent shell. Don't execute anything
      from Python. If `source_script_path` is None (e.g. user invoked
      ctx-bin directly without the wrapper), fall back to executing in
      a subprocess so the command isn't silently no-op.

    mode="subprocess":
      Execute the commands under a subprocess of `shell`, diff the env,
      and write a writeback file to `env_dump_path`. This is the
      original behavior.
    """
    cwd = _resolve_cwd(project_root, leaf.cwd)
    commands = _substitute_args(leaf.run, leaf.args)

    if leaf.mode == "source":
        if source_script_path is not None:
            script = _build_source_script(shell, commands, cwd, leaf.export)
            source_script_path.write_text(script)
            return 0
        # Degraded mode: no wrapper present. Still run the commands so
        # the user sees output, but env changes won't reach their shell.
        return _run_subprocess(leaf, cwd, shell, commands, env_dump_path=None)

    return _run_subprocess(leaf, cwd, shell, commands, env_dump_path=env_dump_path)


# --- Subprocess mode -----------------------------------------------------


def _run_subprocess(
    leaf: LeafNode,
    cwd: Path,
    shell: str,
    commands: list[str],
    env_dump_path: Path | None,
) -> int:
    # export values are applied to the subprocess env BUT kept out of
    # the baseline, so they always show up in the diff and thus flow
    # back to the parent shell.
    baseline_env = os.environ.copy()
    subprocess_env = baseline_env.copy()
    subprocess_env.update(leaf.export)

    with tempfile.NamedTemporaryFile(
        prefix="ctx-raw-env-", delete=False
    ) as tmp:
        raw_env_path = Path(tmp.name)

    try:
        argv, script = _build_subprocess_script(shell, commands, cwd, raw_env_path)
        completed = subprocess.run(
            argv + [script],
            env=subprocess_env,
            cwd=cwd,
        )
        rc = completed.returncode

        if rc == 0 and env_dump_path is not None:
            final_env = _parse_env_nul(raw_env_path.read_bytes())
            added, removed = diff_env(baseline_env, final_env)
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


# --- Source-mode script builder ------------------------------------------


def _build_source_script(
    shell: str,
    commands: list[str],
    cwd: Path,
    export: dict[str, str],
) -> str:
    """
    Build a script the parent shell will source. Behavior:
      - Save current dir, cd into leaf cwd, run commands, then cd back.
        (Only env changes persist; cwd changes do not — matches the old
        subprocess-mode contract.)
      - Apply `export` entries before running.
      - Fail-fast: the first failing command returns out of the sourced
        script with its status, leaving later commands un-run.
      - Each command is echoed in dim before running, matching
        subprocess mode.
    """
    if shell == "fish":
        return _build_fish_source_script(commands, cwd, export)
    return _build_bashlike_source_script(commands, cwd, export)


def _build_bashlike_source_script(
    commands: list[str],
    cwd: Path,
    export: dict[str, str],
) -> str:
    lines: list[str] = [
        "_ctx_prev_pwd=$PWD",
        f"cd {shlex.quote(str(cwd))} || return $?",
    ]
    for k, v in export.items():
        lines.append(f"export {k}={shlex.quote(v)}")
    for cmd in commands:
        lines.append(
            f"printf '\\033[2m$ %s\\033[0m\\n' {shlex.quote(cmd)}"
        )
        # Run the command, capture its status *before* any cleanup
        # commands (cd) overwrite $?, and return out of the sourced
        # script on failure. Keep $_ctx_rc set until after `return`
        # substitutes it.
        lines.append(cmd)
        lines.append(
            "_ctx_rc=$?; "
            'if [ $_ctx_rc -ne 0 ]; then '
            'cd "$_ctx_prev_pwd"; '
            "unset _ctx_prev_pwd; "
            "return $_ctx_rc; "
            "fi; "
            "unset _ctx_rc"
        )
    lines.append('cd "$_ctx_prev_pwd"')
    lines.append("unset _ctx_prev_pwd")
    return "\n".join(lines) + "\n"


def _build_fish_source_script(
    commands: list[str],
    cwd: Path,
    export: dict[str, str],
) -> str:
    lines: list[str] = [
        "set -l _ctx_prev_pwd $PWD",
        f"cd {_fish_single_quote(str(cwd))}; or return $status",
    ]
    for k, v in export.items():
        lines.append(f"set -gx {k} {_fish_single_quote(v)}")
    for cmd in commands:
        lines.append(
            f"printf '\\033[2m$ %s\\033[0m\\n' {_fish_single_quote(cmd)}"
        )
        # fish doesn't have a clean "return from source with status"
        # one-liner; use a status-preserving pattern.
        lines.append(cmd)
        lines.append(
            "set -l _ctx_rc $status; "
            "if test $_ctx_rc -ne 0; "
            "cd $_ctx_prev_pwd; "
            "return $_ctx_rc; "
            "end"
        )
    lines.append("cd $_ctx_prev_pwd")
    return "\n".join(lines) + "\n"


# --- Subprocess-mode script builders -------------------------------------


def _build_subprocess_script(
    shell: str,
    commands: list[str],
    cwd: Path,
    raw_env_path: Path,
) -> tuple[list[str], str]:
    if shell == "fish":
        return (["fish", "-c"], _build_subprocess_fish(commands, cwd, raw_env_path))
    if shell == "zsh":
        return (["zsh", "-c"], _build_subprocess_bashlike(commands, cwd, raw_env_path))
    return (["bash", "-c"], _build_subprocess_bashlike(commands, cwd, raw_env_path))


def _build_subprocess_bashlike(
    commands: list[str],
    cwd: Path,
    raw_env_path: Path,
) -> str:
    lines = [f"cd {shlex.quote(str(cwd))}", "set -e"]
    for cmd in commands:
        lines.append(f"printf '\\033[2m$ %s\\033[0m\\n' {shlex.quote(cmd)}")
        lines.append(cmd)
    lines.append(f"env -0 > {shlex.quote(str(raw_env_path))}")
    return "\n".join(lines) + "\n"


def _build_subprocess_fish(
    commands: list[str],
    cwd: Path,
    raw_env_path: Path,
) -> str:
    lines = [f"cd {_fish_single_quote(str(cwd))}"]
    for cmd in commands:
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
    return format_bash(added, removed)
