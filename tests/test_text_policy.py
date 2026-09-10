from cursor_tts_mcp.core.text_policy import normalize_text, validate_speak_text


def test_normalize_collapse_whitespace():
    assert normalize_text("  a\n\tb  ") == "a b"


def test_validate_empty():
    text, code = validate_speak_text("   ", max_chars=80)
    assert text is None and code == "INVALID_TEXT"


def test_validate_too_long():
    text, code = validate_speak_text("啊" * 81, max_chars=80)
    assert text is None and code == "TEXT_TOO_LONG"


def test_validate_ok():
    text, code = validate_speak_text("接入测试成功", max_chars=80)
    assert text == "接入测试成功" and code is None
