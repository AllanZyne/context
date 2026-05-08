from ctx.emit import diff_env, format_bash, format_fish, FILTERED_KEYS


def test_diff_env_added_changed_removed():
    before = {"KEEP": "1", "CHANGE": "old", "DROP": "x"}
    after = {"KEEP": "1", "CHANGE": "new", "ADD": "y"}
    added_or_changed, removed = diff_env(before, after)
    assert added_or_changed == {"CHANGE": "new", "ADD": "y"}
    assert removed == {"DROP"}


def test_diff_env_filters_shell_internals():
    before = {"PWD": "/a", "FOO": "1"}
    after = {"PWD": "/b", "FOO": "2", "OLDPWD": "/a", "_CTX_TMP": "x"}
    added_or_changed, removed = diff_env(before, after)
    assert added_or_changed == {"FOO": "2"}
    assert removed == set()


def test_filtered_keys_contents():
    assert {"PWD", "OLDPWD", "SHLVL", "_", "PPID"} <= FILTERED_KEYS


def test_format_bash_basic():
    out = format_bash({"FOO": "bar"}, {"OLD"})
    assert "export FOO=$'bar'" in out
    assert "unset OLD" in out
    assert out.endswith("\n")


def test_format_bash_handles_single_quote_and_newline():
    out = format_bash({"X": "it's\nfine"}, set())
    assert out == "export X=$'it\\'s\\nfine'\n"


def test_format_bash_control_bytes_escaped():
    out = format_bash({"X": "a\x01b"}, set())
    assert "\\x01" in out


def test_format_bash_empty_diff_is_empty_string():
    assert format_bash({}, set()) == ""


def test_format_bash_deterministic_ordering():
    out = format_bash({"B": "2", "A": "1"}, {"Y", "X"})
    lines = out.strip().split("\n")
    assert lines == [
        "export A=$'1'",
        "export B=$'2'",
        "unset X",
        "unset Y",
    ]


def test_format_fish_basic():
    out = format_fish({"FOO": "bar"}, {"OLD"})
    assert "set -gx FOO 'bar'" in out
    assert "set -e OLD" in out
    assert out.endswith("\n")


def test_format_fish_escapes_single_quote_and_backslash():
    out = format_fish({"X": r"it's a \path"}, set())
    # fish single-quoted strings only escape \' and \\
    assert out == "set -gx X 'it\\'s a \\\\path'\n"


def test_format_fish_control_bytes_via_hex():
    out = format_fish({"X": "a\x01b"}, set())
    # Values with control bytes cannot live inside '...', we fall back
    # to concatenation of safe quoted segments and \xNN escapes.
    # Expect that the output can be re-sourced by fish and produces "a\x01b".
    assert "\\x01" in out or "\\X01" in out


def test_format_fish_empty_diff_is_empty_string():
    assert format_fish({}, set()) == ""
