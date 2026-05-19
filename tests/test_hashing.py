from ai_use.hashing import hash_line, hash_lines, normalize_line


def test_normalize_line_trims_edges_and_line_endings():
    assert normalize_line("  value = 1\r\n") == "value = 1"


def test_hash_line_uses_normalized_content():
    assert hash_line("value = 1\n") == hash_line("  value = 1")


def test_hash_lines_includes_blank_lines():
    assert len(hash_lines("a\n\nb")) == 3
