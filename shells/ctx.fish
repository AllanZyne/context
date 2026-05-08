# ctx shell integration for fish.
#
# This file is a static copy of what `ctx-bin shellinit fish` emits.
# Both installation methods are supported:
#
#   A) Installed binary only (no repo access):
#        ctx-bin shellinit fish | source             # add to config.fish
#
#   B) Source this file directly (if you have the repo checked out):
#        source /path/to/ctx/shells/ctx.fish         # add to config.fish

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
