# ctx shell integration for zsh.
#
# This file is a static copy of what `ctx-bin shellinit zsh` emits.
# Both installation methods are supported:
#
#   A) Installed binary only (no repo access):
#        eval "$(ctx-bin shellinit zsh)"       # add to ~/.zshrc
#
#   B) Source this file directly (if you have the repo checked out):
#        source /path/to/ctx/shells/ctx.zsh    # add to ~/.zshrc

ctx() {
  local _ctx_dump
  _ctx_dump=$(mktemp -u -t ctx-env.XXXXXX) || return 1
  CTX_ENV_DUMP="$_ctx_dump" command ctx-bin --shell=zsh "$@"
  local _ctx_rc=$?
  if [ $_ctx_rc -eq 0 ] && [ -s "$_ctx_dump" ]; then
    . "$_ctx_dump"
  fi
  [ -e "$_ctx_dump" ] && command rm -f "$_ctx_dump"
  return $_ctx_rc
}
