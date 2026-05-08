import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from ctx.emit import diff_env, format_bash, format_fish
from ctx.resolver import ARGS_PLACEHOLDER, LeafNode


class RunnerError(Exception):
    """Raised for pre-execution errors (bad cwd, etc.)."""


def run_leaf(
    leaf: LeafNode,
    project_root: Path,
    shell: str,
    env_dump_path: Path | None,
) -> int:
    """
    Execute all commands in `leaf.run` under a single bash subprocess.

    If `env_dump_path` is given, writes the env writeback source (in
    `shell` syntax) to it on success. On failure the file is left
    untouched (caller is expected to have it empty or non-existent so
    that shell wrappers skip sourcing).
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

    # Tempfile for bash to dump env -0 into.
    with tempfile.NamedTemporaryFile(
        prefix="ctx-raw-env-", delete=False
    ) as tmp:
        raw_env_path = Path(tmp.name)

    try:
        script = _build_bash_script(commands, cwd, raw_env_path)
        completed = subprocess.run(
            ["bash", "-c", script],
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


def _build_bash_script(
    commands: list[str],
    cwd: Path,
    raw_env_path: Path,
) -> str:
    lines = [
        "set -e",
        f"cd {shlex.quote(str(cwd))}",
    ]
    for cmd in commands:
        lines.append(f"printf '\\033[2m$ %s\\033[0m\\n' {shlex.quote(cmd)}")
        lines.append(cmd)
    lines.append(f"env -0 > {shlex.quote(str(raw_env_path))}")
    return "\n".join(lines) + "\n"


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
