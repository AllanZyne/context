# ctx

Run hierarchical commands defined in a project's `context.yaml`, with
environment-variable changes automatically propagated back to your
shell (bash/zsh/fish).

## Install

```bash
uv tool install git+https://your-git-host/ctx  # or: uv tool install .
```

Then add one line to your shell rc:

```bash
# ~/.bashrc or ~/.zshrc
eval "$(ctx-bin shellinit bash)"   # or: zsh

# ~/.config/fish/config.fish
ctx-bin shellinit fish | source
```

## Usage

Create a `context.yaml` at your project root:

```yaml
commands:
  init:
    desc: Install deps
    run:
      - uv sync
  build:
    prod:
      cwd: ./app
      env:
        NODE_ENV: production
      run:
        - docker build -t app:prod .
    dev:
      run:
        - docker build -t app:dev .
  activate:
    run:
      - source .venv/bin/activate   # VIRTUAL_ENV propagates back
```

Then, from any directory under the project:

```
$ ctx init                # runs commands.init.run
$ ctx build prod          # runs commands.build.prod.run
$ ctx activate            # env changes flow back to your shell
$ echo $VIRTUAL_ENV       # now set
```

## Behavior notes

- All commands execute under `/bin/bash` with `set -e` — pipes,
  `source`, and bash variable expansion work regardless of your
  interactive shell.
- env writeback only happens on full success. One failed command
  drops all env changes.
- `PWD`, `OLDPWD`, `SHLVL`, `_`, and `PPID` are never written back.

## Development

```bash
uv sync --group dev
uv run pytest
```
