import pytest

from ctx.shellinit import shellinit, SUPPORTED_SHELLS


def test_bash_wrapper_contents():
    src = shellinit("bash")
    assert "ctx()" in src
    assert "command ctx-bin" in src
    assert "--shell=bash" in src
    assert "CTX_ENV_DUMP" in src
    assert ". \"$_ctx_dump\"" in src  # source via "." with quoted var


def test_zsh_differs_only_in_shell_flag():
    bash = shellinit("bash")
    zsh = shellinit("zsh")
    assert zsh.replace("--shell=zsh", "--shell=bash") == bash


def test_fish_wrapper_contents():
    src = shellinit("fish")
    assert "function ctx" in src
    assert "command ctx-bin --shell=fish $argv" in src
    assert "source $_ctx_dump" in src
    assert "CTX_ENV_DUMP=$_ctx_dump" in src


def test_unsupported_shell_rejected():
    with pytest.raises(ValueError):
        shellinit("powershell")


def test_supported_shells():
    assert SUPPORTED_SHELLS == ("bash", "zsh", "fish")
