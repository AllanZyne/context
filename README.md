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
  prod:
    cwd: ./app
    env:
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
$ ctx build prod        # run build.prod.run
$ ctx test -k login     # forward args via {args}
$ ctx activate          # env changes flow back
```

## `context.yaml`

Top-level is a mapping of command names. A **leaf** has a `run` key; a
**group** doesn't. Nest groups freely: `ctx deploy staging k8s`.

### Leaf fields

| Field       | Type     | Description |
|-------------|----------|-------------|
| `run`       | str \| list[str] | Commands run in one shell process, in your parent shell's syntax. Fail-fast on first error. A bare string is shorthand for a one-element list. |
| `desc`      | str      | Shown in `ctx` listing. |
| `cwd`       | str      | Relative to `context.yaml`'s directory. |
| `env`       | mapping  | Set for this run only. Changes don't flow back unless the command itself mutates them. |
| `export`    | mapping  | Like `env`, but values always flow back to your shell. Can't share keys with `env`. |
| `source_rc` | bool     | Default `false`. If `true`, source your rc (`~/.bashrc` / `~/.zshrc` / `config.fish`) before `run:` — gives access to your functions, aliases, PATH. |

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

- Commands run under your parent shell — write `run:` in that shell's
  syntax (fish users use fish syntax).
- Env writeback is **all-or-nothing**: a failing command drops all changes.
- Shell-internal vars (`PWD`, `SHLVL`, `PS1`, `LINES`, `BASH_*`, etc.)
  are never written back.
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
