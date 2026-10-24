from graph import _style_prompt, merge_node, parse_json_response


def test_parse_json_response_raw_array():
    raw = '[{"file":"a.py","line":1,"severity":"error","message":"bad"}]'
    assert parse_json_response(raw) == [
        {"file": "a.py", "line": 1, "severity": "error", "message": "bad"}
    ]


def test_parse_json_response_fenced_block():
    raw = """Here you go:
```json
[{"file":"b.py","line":2,"severity":"warning","message":"smell"}]
```
"""
    assert parse_json_response(raw) == [
        {"file": "b.py", "line": 2, "severity": "warning", "message": "smell"}
    ]


def test_parse_json_response_invalid_returns_empty():
    assert parse_json_response("not-json") == []


def test_merge_node_deduplicates_findings():
    finding = {
        "file": "a.py",
        "line": 1,
        "agent": "security",
        "message": "injection",
    }
    result = merge_node({"findings": [finding, finding.copy(), {**finding, "line": 2}]})
    assert len(result["findings"]) == 2


def test_style_prompt_includes_patterns():
    prompt = _style_prompt({"patterns": ["prefer early returns"], "diff": "", "findings": []})
    assert "prefer early returns" in prompt


def test_style_prompt_handles_empty_patterns():
    prompt = _style_prompt({"patterns": [], "diff": "", "findings": []})
    assert "None" in prompt
