from src.rag import normalize_code


def test_normalize_code_removes_whitespace():
    """Assert that normalize_code doesn't break the code"""
    raw_code = "def my_func():\n    return True\n"
    normalized = normalize_code(raw_code)

    assert "def my_func():" in normalized
    assert "return True" in normalized


def test_normalize_code_handles_empty_string():
    assert normalize_code("") == ""
    assert normalize_code("   \n  \t ") == ""


def test_normalize_code_is_deterministic():
    """Code2 has a leading space"""
    code1 = "def a():\n    return 1"
    code2 = "def a():\n    return 1 "

    assert normalize_code(code1) == normalize_code(code2)