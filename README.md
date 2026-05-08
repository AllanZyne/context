# ctx

Per-project command runner driven by `context.yaml`. Works in bash,
zsh, and fish; env changes made by commands flow back to your shell.

## Install

```bash
uv tool install git+https://github.com/AllanZyne/context
```

Or from a local clone:

```bash
git clone https://github.com/AllanZyne/context.git && cd context
uv tool install --reinstall .
```

Then add one line to your shell rc:

```bash
# ~/.bashrc                        eval "$(ctx-bin shellinit bash)"
# ~/.zshrc                         eval "$(ctx-bin shellinit zsh)"
# ~/.config/fish/config.fish       ctx-bin shellinit fish | source
```

Open a new shell. `ctx` is now available.

**Upgrade:** `uv tool upgrade ctx` (or `git pull && uv tool install --reinstall .`).

## Quick start

Drop a `context.yaml` at your project root:

```yaml
init:
  desc: Install deps
  run:
    - uv sync

test:
  run:
    - pytest {args}               # ctx test -k login  →  pytest -k login

build:
  mode: subprocess                # isolate long build from your shell
  cwd: ./app
  export:
    NODE_ENV: production
  run:
    - docker build -t app:prod .

activate:
  run:
    - source .venv/bin/activate   # VIRTUAL_ENV persists in your shell
```

```
$ ctx                   # list available commands
$ ctx init              # run init.run
$ ctx build             # run build.run
$ ctx test -k login     # forward args via {args}
$ ctx activate          # env / conda / aliases flow into your shell
```

## `context.yaml`

Top-level is a mapping of command names. A **leaf** has a `run` key; a
**group** doesn't. Nest groups freely: `ctx deploy staging k8s`.

### Leaf fields

| Field    | Type             | Description |
|----------|------------------|-------------|
| `run`    | str \| list[str] | Commands run in your parent shell's syntax. Fail-fast on first error. A bare string is shorthand for a one-element list. |
| `desc`   | str              | Shown in `ctx` listing. |
| `cwd`    | str              | Relative to `context.yaml`'s directory. Restored after the run. |
| `export` | mapping          | Set as env vars before `run:`. They persist in your shell in source mode; in subprocess mode they always show up in the writeback. |
| `mode`   | str              | `source` (default) or `subprocess`. See below. |

### `source` vs `subprocess`

`source` (default) runs the `run:` commands **inside your current shell**
by sourcing a generated script. Shell functions, aliases, `conda
activate`, `source some.fish` — everything your shell can do works here,
and every side effect (env, functions, aliases) persists afterward.
Great for `init` / `activate` style leaves.

`subprocess` runs the commands under a clean `$SHELL -c …` subprocess
and flows only env-var changes back to your shell via a diff. Slower,
but gives an **all-or-nothing** guarantee: if any command fails, *none*
of the env changes leak into your shell. Use this for builds or any
long compound command where partial state would be confusing.

Both modes honor `cwd:`, `export:`, `{args}`, and fail-fast.

### `{args}` forwarding

```yaml
test:
  run:
    - pytest {args}          # ctx test -x -k login  →  pytest -x -k login
fmt:
  run:
    - ruff format {args|.}   # ctx fmt  →  ruff format .   (default)
```

- `{args}` substitutes extra tokens (shell-quoted).
- `{args|fallback}` inserts the `|` part verbatim when no args given.
- Without `{args}`, extra tokens still error (no accidental silent drop).

### Behavior

- Commands run in your parent shell's syntax (fish users use fish).
- `cwd:` is applied for the run and restored afterward.
- Subprocess mode only: shell-internal vars (`PWD`, `SHLVL`, `PS1`,
  `LINES`, `BASH_*`, etc.) are never written back.
- `shellinit` is reserved; a top-level `shellinit:` in your yaml is
  shadowed by the builtin.

### Exit codes

| Code | Meaning |
|------|---------|
| 0    | Command succeeded / listing shown. |
| 1    | Setup error (missing yaml, schema, bad `cwd`). |
| 2    | Resolution error (unknown subcommand, extra tokens). |
| n    | Propagated from the failing command. |

## Development

```bash
uv sync --group dev
uv run pytest
```
