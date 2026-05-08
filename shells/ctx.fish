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
    set -l _ctx_src (mktemp -u -t ctx-src.XXXXXX)
    or return 1
    CTX_ENV_DUMP=$_ctx_dump CTX_SOURCE_SCRIPT=$_ctx_src \
        command ctx-bin --shell=fish $argv
    set -l _ctx_rc $status
    if test $_ctx_rc -eq 0
        if test -s $_ctx_src
            source $_ctx_src
            set _ctx_rc $status
        else if test -s $_ctx_dump
            source $_ctx_dump
        end
    end
    if test -e $_ctx_dump
        command rm -f $_ctx_dump
    end
    if test -e $_ctx_src
        command rm -f $_ctx_src
    end
    return $_ctx_rc
end
