# CLAUDE.md — notes for future sessions on this repo

Keep this file short. Record only things that (a) are easy to get wrong
and (b) aren't obvious from just reading the code or the README.

## Working agreement with the user (do NOT deviate)

1. **Don't create `docs/superpowers/specs/` or `docs/superpowers/plans/`
   files** unless the user explicitly asks. When a superpowers skill
   (brainstorming, writing-plans) wants to save a design or plan
   document, skip the file write and keep it in chat.
2. **Don't run `git commit`** (or `git add` + commit) unless the user
   explicitly asks. Leave changes in the working tree after editing so
   the user can review. Read-only git (`status`, `diff`, `log`) is
   fine.

## What this is

A Python CLI (`ctx-bin`, wrapped as a shell function `ctx`) that reads a
hierarchical `context.yaml` and runs its leaves in one of two modes:

- **source mode (default)**: ctx-bin writes a generated shell script to
  `$CTX_SOURCE_SCRIPT`; the wrapper `source`s it in the parent shell.
  Every shell side effect — env, functions, aliases, `conda activate` —
  persists. Not all-or-nothing: a mid-run failure leaves earlier
  mutations in the parent shell.
- **subprocess mode** (`mode: subprocess`): ctx-bin runs commands under
  `$SHELL -c`, diffs `env -0` before/after, writes fish/bash writeback
  to `$CTX_ENV_DUMP`; the wrapper sources that. All-or-nothing on env
  writeback. Only env vars flow back (no functions / aliases).

User-facing docs live in `README.md`.

## Commands

```bash
uv sync --group dev                     # create .venv + install deps
uv run pytest                           # full suite (~2s)
uv run pytest tests/test_integration.py # real shell subprocess tests
uv tool install --reinstall .           # install ctx-bin into uv tool env
```

Integration tests spawn real `bash` / `zsh` / `fish` and invoke ctx-bin
via `uv --directory {REPO_ROOT} run ctx-bin` — they do **not** rely on
`uv tool install` having run. zsh and fish tests auto-skip if missing.

## Layout

```
src/ctx/
  cli.py         argv dispatch + --shell= flag + shellinit reservation
  config.py      find_yaml() walks up; load_and_validate() schema checks
  resolver.py    pure fn: tokens → LeafNode | GroupListing
  runner.py      source mode writes $CTX_SOURCE_SCRIPT; subprocess mode
                 execs under $SHELL -c + diffs env to $CTX_ENV_DUMP
  emit.py        pure fns: diff_env, format_bash, format_fish (subprocess
                 mode only)
  shellinit.py   wrapper templates emitted by `ctx-bin shellinit <shell>`

shells/ctx.{bash,zsh,fish}    static copies of shellinit() output
docs/superpowers/{specs,plans}/   design + implementation docs
tests/test_*.py                pytest, one per module + test_integration.py
```

## Invariants that will break silently if violated

1. **`shells/ctx.{bash,zsh,fish}` must byte-match `shellinit(<shell>)` output.**
   Enforced by `test_static_wrapper_matches_shellinit` (in
   `tests/test_integration.py`). If you edit `shellinit.py`'s templates,
   update the static files too — the drift test compares after stripping
   the leading comment header only.

2. **The wrapper must not create any file until ctx-bin writes to it.**
   Both `$CTX_ENV_DUMP` (subprocess mode) and `$CTX_SOURCE_SCRIPT`
   (source mode) use `mktemp -u` (name only, no file). Combined with:
   runner only writes the relevant file when it has content. Combined
   with: wrapper cleanup is guarded by `[ -e ]` / `test -e`. Rationale:
   a stray `removed '...'` trailer was visible to users who had
   `alias rm='rm -v'`. See regression tests
   `test_bash_wrapper_no_tmpfile_when_yaml_missing` and
   `test_bash_wrapper_ignores_rm_alias`.

3. **Wrapper cleanup must use `command rm`**, not bare `rm`. Users often
   alias or function-shadow `rm`; `command` bypasses both.

4. **Commands execute under the parent shell (`--shell=bash|zsh|fish`)**,
   not always bash. In source mode the parent shell literally `source`s
   the emitted script. In subprocess mode the runner launches
   `$shell -c`. The `--shell=` flag decides both the executor and the
   syntax of the emitted scripts. YAML commands must be written in the
   user's shell dialect.

5. **`resolver.py` and `emit.py` are pure functions** — no filesystem,
   no subprocess. This is intentional so their tests use in-memory
   dicts. Keep it that way.

6. **Reserved subcommand: `shellinit`**. Intercepted in `cli.py` before
   YAML loading. User-defined `commands.shellinit` is shadowed. Adding
   more reserved names? Document them in README §"Reserved names".

7. **Env keys never written back to parent shell (subprocess mode only)**:
   `PWD`, `OLDPWD`, `SHLVL`, `_`, `PPID`, anything starting with
   `_CTX_`, plus `PS1..PS4` and `BASH_*`. Defined in `FILTERED_KEYS`
   in `emit.py`. Source mode doesn't diff, so this list does not apply
   to it — the sourced script simply `export`s what it `export`s.

8. **Source mode leaks on failure**. A mid-run failure in source mode
   leaves any earlier mutations in the parent shell. This is the
   explicit tradeoff for getting functions/aliases/conda working.
   Subprocess mode is still the right default when all-or-nothing
   matters; pick `mode: subprocess` explicitly.

9. **Source mode restores `cwd` after the run**. The emitted script
   saves `$PWD`, `cd`s into the leaf's `cwd:`, runs, then `cd`s back —
   matching the prior subprocess-mode contract that `cwd:` is not a
   persistent shell side effect. Do not remove this: the user expects
   `ctx build prod` not to dump them in `./app/`.

## YAML schema quirks

- Top-level is **directly** the command mapping — no wrapper key.
  (`init: {run: [...]}`, not `commands: {init: {...}}`.)
- Leaf keys: `{run, desc, cwd, export, mode}`. A leaf with `run` plus
  any key outside that set is rejected.
- `export` values: scalars (str/int/bool) are coerced via `str()` at
  load time; lists/dicts rejected. In source mode the runner emits
  `export KEY=<shlex.quote(val)>` before running. In subprocess mode
  they go into the subprocess env but NOT the baseline — so they
  always appear in the writeback.
- `mode`: one of `"source"` (default) | `"subprocess"`. Validated in
  `config.py:_validate_leaf`; consumed in `runner.run_leaf` to
  dispatch.
- `run` accepts both a string and a list. A bare string is coerced to
  a one-element list at load time in `_validate_leaf` so every
  downstream consumer can assume `list[str]`.
- **`{args}` placeholder**: a leaf with `{args}` or `{args|default}`
  anywhere in its `run:` list opts into accepting extra CLI tokens.
  resolver detects via `_ARGS_RE`; runner substitutes via
  `_substitute_args` (shlex.join for safety). Without the placeholder,
  extra tokens still error as before. Substitution applies before the
  script is emitted/executed, same code path for both modes.
- **Source-mode script shape**: `_build_bashlike_source_script` and
  `_build_fish_source_script` emit a script that saves `$PWD`, `cd`s
  into leaf cwd, applies `export`s, runs each command (with a dim
  `$ cmd` echo), and on failure `return`s out of the sourced script
  with the non-zero status (after restoring PWD). fish uses
  `set -l _ctx_rc $status; if test $_ctx_rc -ne 0; ...; return
  $_ctx_rc; end` because there is no single-line equivalent of
  `|| return`.
- **Subprocess-mode script shape**: `_build_subprocess_bashlike` uses
  `set -e`; `_build_subprocess_fish` uses `or exit $status` after each
  command. The subprocess dumps its final env via `env -0` to a tmp
  path, which runner.py parses and diffs vs the starting env.
- **Group listing**: `GroupListing.children` is a **fully flattened**
  list of `GroupChild(name, desc)` — every reachable leaf, not just
  the immediate children. `name` is the space-joined relative path
  from the listed group down to the leaf (e.g. `"init clovis"`),
  which is exactly what the user would type after `ctx`. Groups
  themselves never appear as entries. resolver builds this via
  `_list_children` → `_walk_leaves`; cli.py renders two columns with
  padded alignment.

## Git / workflow gotchas

- The repo has had several branch flips (feature/ctx → squash-merge →
  main → fix/… etc.). If `docs/superpowers/specs/` looks "missing" in
  `git status`, it's almost certainly because commits for it landed on
  another branch. Run `git log <branch> -- docs/superpowers/` before
  panicking — the files are usually in history, just not checked out
  on the current branch. Restore with `git checkout <ref> -- docs/`.
- `uv.lock` should be committed. It was missed in the scaffold commit
  and added later.

## Common implementation tasks

- **Changing wrapper behavior**: edit `shellinit.py` templates AND
  `shells/*` in the same commit, or the drift test fails.
- **Changing the YAML schema**: update `config.py` validation, every
  test fixture (there are many in `test_config.py`, `test_cli.py`,
  `test_integration.py`), the spec, AND the README's reference table.
- **Adding a test that runs a real shell**: follow the
  `_has("bash") / skipif` pattern already in `test_integration.py`.
  Pass `env={**os.environ}` so PATH reaches the subprocess.
- **After editing anything under `src/ctx/`, before running a
  user-facing smoke test (NOT `pytest`)**, re-install the binary:

  ```bash
  uv tool install --reinstall .
  ```

  **Why:** `~/.local/bin/ctx-bin` is pinned to whatever code was
  installed last time. pytest imports from the repo directly
  (`pythonpath = ["src"]` in pyproject.toml) so unit tests always
  exercise fresh code, but `ctx` — the shell function from
  `shells/ctx.<shell>` — invokes `command ctx-bin`, which is the
  installed binary. Smoke tests silently keep testing stale code
  until you reinstall. Telltale sign: unit tests pass but an
  end-to-end smoke shows behavior matching old code (e.g. commands
  running under bash when `--shell=fish` should dispatch to fish).
- **A `PATH` with the shell binary is required for that shell's
  tests.** `shutil.which("zsh")` gates the `@pytest.mark.skipif`.
  If zsh/fish isn't on `PATH`, add it once for the test run —
  e.g. `PATH="/localdisk2/yzhao/miniforge3/bin:$PATH" uv run pytest`.
  Tests will silently skip otherwise, giving a false sense of
  coverage.

## Writing style

- No emojis in code or docs unless the user asks.
- README is user-facing and should stay opinionated ("do this"); this
  file is for implementer-facing quirks and invariants.
