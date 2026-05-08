SUPPORTED_SHELLS: tuple[str, ...] = ("bash", "zsh", "fish")


_BASH_TEMPLATE = """\
ctx() {{
  local _ctx_dump
  _ctx_dump=$(mktemp -u -t ctx-env.XXXXXX) || return 1
  CTX_ENV_DUMP="$_ctx_dump" command ctx-bin --shell={shell} "$@"
  local _ctx_rc=$?
  if [ $_ctx_rc -eq 0 ] && [ -s "$_ctx_dump" ]; then
    . "$_ctx_dump"
  fi
  [ -e "$_ctx_dump" ] && command rm -f "$_ctx_dump"
  return $_ctx_rc
}}
"""

_FISH_TEMPLATE = """\
function ctx
    set -l _ctx_dump (mktemp -u -t ctx-env.XXXXXX)
    or return 1
    CTX_ENV_DUMP=$_ctx_dump command ctx-bin --shell=fish $argv
    set -l _ctx_rc $status
    if test $_ctx_rc -eq 0 -a -s $_ctx_dump
        source $_ctx_dump
    end
    if test -e $_ctx_dump
        command rm -f $_ctx_dump
    end
    return $_ctx_rc
end
"""


def shellinit(shell: str) -> str:
    """Return the wrapper source to be eval'd (bash/zsh) or sourced (fish)."""
    if shell not in SUPPORTED_SHELLS:
        raise ValueError(
            f"unsupported shell {shell!r}; expected one of {SUPPORTED_SHELLS}"
        )
    if shell == "fish":
        return _FISH_TEMPLATE
    return _BASH_TEMPLATE.format(shell=shell)
