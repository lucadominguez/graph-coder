from graph_coder.redaction import REDACTED, redact


def test_recursive_secret_key_redaction():
    data = {"token": "abc", "nested": [{"api_key": "k", "safe": "ok"}], "safe": "visible"}
    redacted = redact(data)
    assert redacted["token"] == REDACTED
    assert redacted["nested"][0]["api_key"] == REDACTED
    assert redacted["safe"] == "visible"


def test_string_pattern_redaction():
    text = redact("Authorization: Bearer abc.def password=hunter2 api-key=xyz")
    assert "abc.def" not in text
    assert "hunter2" not in text
    assert "xyz" not in text
    assert text.count(REDACTED) == 3
