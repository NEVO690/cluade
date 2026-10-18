from __future__ import annotations

from app.rendering.markdown_renderer import (
    display_language,
    highlight_code_html,
    markdown_to_html,
    normalize_language,
    split_segments,
)


def test_raw_html_is_escaped_not_rendered() -> None:
    html = markdown_to_html("Hi <script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n<div onclick=x>a</div>")
    assert "<script" not in html
    assert "<img" not in html
    assert "<div" not in html
    assert "&lt;script&gt;" in html


def test_unsafe_link_schemes_are_removed() -> None:
    html = markdown_to_html("[a](javascript:alert(1)) [b](file:///C:/x) [c](https://example.com) [d](mailto:x@y.z)")
    assert "javascript:" not in html
    assert "file:" not in html
    assert 'href="https://example.com"' in html
    assert 'href="mailto:x@y.z"' in html


def test_images_are_never_loaded() -> None:
    html = markdown_to_html("![diagram](https://example.com/a.png)")
    assert "<img" not in html
    assert 'href="https://example.com/a.png"' in html
    assert "[diagram]" in html


def test_markdown_features() -> None:
    html = markdown_to_html("# Title\n\n**bold** and `code`\n\n- one\n- two\n\n|a|b|\n|-|-|\n|1|2|")
    assert "<h1>" in html and "<strong>bold</strong>" in html and "<code>code</code>" in html
    assert "<li>one</li>" in html
    assert "<table" in html and 'border="1"' in html


def test_split_segments_prose_and_code() -> None:
    text = "Intro\n\n```python\nprint('hi')\n```\n\nOutro\n~~~\nraw\n~~~"
    segments = split_segments(text)
    assert [(s.kind, s.language) for s in segments] == [
        ("markdown", ""),
        ("code", "python"),
        ("markdown", ""),
        ("code", ""),
    ]
    assert segments[1].text == "print('hi')"
    assert all(s.closed for s in segments)


def test_split_segments_handles_streaming_unclosed_fence() -> None:
    segments = split_segments("Here:\n```luau\nlocal x = 1\n")
    assert segments[-1].kind == "code"
    assert segments[-1].language == "luau"
    assert segments[-1].closed is False


def test_fence_inside_code_with_shorter_marker_does_not_close() -> None:
    segments = split_segments("````md\n```js\nx\n```\n````")
    assert len(segments) == 1
    assert "```js" in segments[0].text


def test_language_aliases() -> None:
    assert normalize_language("Luau") == "lua"
    assert normalize_language("C#") == "csharp"
    assert normalize_language("c++") == "cpp"
    assert display_language("csharp") == "C#"
    assert display_language("") == "code"


def test_highlighting_produces_inline_styles_and_escapes() -> None:
    html = highlight_code_html("if a < b: print('<x>')", "python", dark=True)
    assert "style=" in html
    assert "<x>" not in html and "&lt;" in html
    plain = highlight_code_html("<b>plain</b>", "no-such-language", dark=False)
    assert "<b>" not in plain
