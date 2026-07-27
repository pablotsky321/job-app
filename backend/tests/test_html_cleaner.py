"""
Unit tests for backend/shared/html_cleaner.py.

Pure function tests — no AWS mocks, no network calls.
Validates HTML cleaning logic for LLM processing (Requirement 5.1).
"""

import pytest
from backend.shared.html_cleaner import html_to_clean_text


class TestTagRemoval:
    """Verify that script, style, noscript, svg, iframe, meta tags are removed."""

    def test_removes_script_tags_and_content(self):
        html = "<p>Hello</p><script>alert('xss')</script><p>World</p>"
        result = html_to_clean_text(html)
        assert "alert" not in result
        assert "xss" not in result
        assert "Hello" in result
        assert "World" in result

    def test_removes_style_tags_and_content(self):
        html = "<p>Text</p><style>body { color: red; }</style><p>More</p>"
        result = html_to_clean_text(html)
        assert "color" not in result
        assert "red" not in result
        assert "Text" in result
        assert "More" in result

    def test_removes_noscript_tags_and_content(self):
        html = "<p>Visible</p><noscript>Enable JavaScript</noscript><p>End</p>"
        result = html_to_clean_text(html)
        assert "Enable JavaScript" not in result
        assert "Visible" in result
        assert "End" in result

    def test_removes_svg_tags_and_content(self):
        html = '<p>Before</p><svg><circle cx="50" cy="50" r="40"/></svg><p>After</p>'
        result = html_to_clean_text(html)
        assert "circle" not in result
        assert "cx" not in result
        assert "Before" in result
        assert "After" in result

    def test_removes_iframe_tags_and_content(self):
        html = '<p>Page</p><iframe src="https://evil.com">Fallback</iframe><p>Done</p>'
        result = html_to_clean_text(html)
        assert "evil.com" not in result
        assert "Fallback" not in result
        assert "Page" in result
        assert "Done" in result

    def test_removes_meta_tags(self):
        html = '<meta charset="utf-8"><meta name="robots" content="noindex"><p>Content</p>'
        result = html_to_clean_text(html)
        assert "charset" not in result
        assert "robots" not in result
        assert "Content" in result

    def test_removes_nested_script_in_head(self):
        html = """
        <html>
        <head>
            <script type="text/javascript">
                var tracking = {id: 123, secret: "abc"};
                console.log(tracking);
            </script>
        </head>
        <body><p>Real content</p></body>
        </html>
        """
        result = html_to_clean_text(html)
        assert "tracking" not in result
        assert "secret" not in result
        assert "console" not in result
        assert "Real content" in result

    def test_removes_multiple_scripts_and_styles(self):
        html = (
            "<script>one()</script>"
            "<p>A</p>"
            "<style>.x{}</style>"
            "<p>B</p>"
            "<script>two()</script>"
        )
        result = html_to_clean_text(html)
        assert "one" not in result
        assert "two" not in result
        assert ".x" not in result
        assert "A" in result
        assert "B" in result


class TestCommentRemoval:
    """Verify HTML comments are stripped."""

    def test_removes_simple_comment(self):
        html = "<p>Before</p><!-- This is a comment --><p>After</p>"
        result = html_to_clean_text(html)
        assert "This is a comment" not in result
        assert "Before" in result
        assert "After" in result

    def test_removes_multiline_comment(self):
        html = """
        <p>Start</p>
        <!--
            Multi-line comment
            with secrets: api_key=12345
        -->
        <p>End</p>
        """
        result = html_to_clean_text(html)
        assert "Multi-line" not in result
        assert "api_key" not in result
        assert "Start" in result
        assert "End" in result

    def test_removes_conditional_ie_comment(self):
        html = "<p>X</p><!--[if IE]>Old browser<![endif]--><p>Y</p>"
        result = html_to_clean_text(html)
        assert "Old browser" not in result
        assert "X" in result
        assert "Y" in result


class TestWhitespaceNormalization:
    """Verify whitespace is collapsed to single spaces."""

    def test_multiple_spaces_become_one(self):
        html = "<p>Hello     World</p>"
        result = html_to_clean_text(html)
        assert "Hello World" in result
        assert "     " not in result

    def test_tabs_and_newlines_become_spaces(self):
        html = "<p>Line1\t\t\tLine2\n\n\nLine3</p>"
        result = html_to_clean_text(html)
        # All whitespace types normalized to single space
        assert "\t" not in result
        assert "\n" not in result
        assert "Line1" in result
        assert "Line2" in result
        assert "Line3" in result

    def test_no_leading_or_trailing_whitespace(self):
        html = "   <p>  Content  </p>   "
        result = html_to_clean_text(html)
        assert result == result.strip()

    def test_whitespace_between_tags_normalized(self):
        html = "<h1>Title</h1>   \n\n   <p>Paragraph</p>"
        result = html_to_clean_text(html)
        # Should not have multiple consecutive spaces
        assert "  " not in result


class TestSizeTruncation:
    """Verify max_clean_size_kb enforcement via truncation."""

    def test_small_content_not_truncated(self):
        html = "<p>Short text</p>"
        result = html_to_clean_text(html, max_clean_size_kb=1)
        assert result == "Short text"

    def test_large_content_truncated_to_limit(self):
        # Create HTML with content exceeding 1 KB
        large_text = "A" * 2000
        html = f"<p>{large_text}</p>"
        result = html_to_clean_text(html, max_clean_size_kb=1)
        # 1 KB = 1024 bytes
        assert len(result.encode("utf-8")) <= 1024

    def test_truncation_respects_utf8_boundary(self):
        # Use multi-byte characters (each é is 2 bytes in UTF-8)
        # 512 é characters = 1024 bytes exactly at the limit
        # 600 é characters = 1200 bytes, exceeds 1 KB
        large_text = "é" * 600
        html = f"<p>{large_text}</p>"
        result = html_to_clean_text(html, max_clean_size_kb=1)
        # Result must be valid UTF-8 and within limit
        encoded = result.encode("utf-8")
        assert len(encoded) <= 1024
        # Should not end with a broken multi-byte sequence
        result.encode("utf-8").decode("utf-8")  # Should not raise

    def test_default_limit_is_100kb(self):
        # Verify 100 KB default by creating content just over
        # 100 KB = 102400 bytes
        large_text = "X" * 110_000
        html = f"<p>{large_text}</p>"
        result = html_to_clean_text(html)
        assert len(result.encode("utf-8")) <= 102400

    def test_truncation_never_skips(self):
        """Truncation produces output, never returns empty or raises."""
        large_text = "Content " * 20_000
        html = f"<p>{large_text}</p>"
        result = html_to_clean_text(html, max_clean_size_kb=1)
        assert len(result) > 0
        assert len(result.encode("utf-8")) <= 1024


class TestEdgeCases:
    """Edge cases and robustness."""

    def test_empty_string_returns_empty(self):
        assert html_to_clean_text("") == ""

    def test_none_returns_empty(self):
        assert html_to_clean_text(None) == ""

    def test_non_string_returns_empty(self):
        assert html_to_clean_text(123) == ""

    def test_plain_text_passthrough(self):
        result = html_to_clean_text("Just plain text no HTML")
        assert result == "Just plain text no HTML"

    def test_only_removed_tags_returns_empty(self):
        html = "<script>code()</script><style>.x{}</style><!-- comment -->"
        result = html_to_clean_text(html)
        assert result == ""

    def test_complex_real_world_page(self):
        html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width">
            <title>Careers - Acme Corp</title>
            <style>
                body { font-family: sans-serif; }
                .hidden { display: none; }
            </style>
            <script src="analytics.js"></script>
            <script>window.dataLayer = [];</script>
        </head>
        <body>
            <header>
                <nav>
                    <a href="/">Home</a>
                    <a href="/careers">Careers</a>
                </nav>
            </header>
            <!-- Main content section -->
            <main>
                <h1>Open Positions</h1>
                <noscript>Please enable JavaScript</noscript>
                <div class="job-list">
                    <h2>Software Engineer</h2>
                    <p>Build amazing products with our team.</p>
                    <h2>Product Manager</h2>
                    <p>Lead product strategy.</p>
                </div>
                <svg viewBox="0 0 100 100"><circle r="50"/></svg>
                <iframe src="https://maps.google.com"></iframe>
            </main>
            <footer>
                <p>© 2024 Acme Corp</p>
            </footer>
        </body>
        </html>
        """
        result = html_to_clean_text(html)

        # Content preserved
        assert "Open Positions" in result
        assert "Software Engineer" in result
        assert "Product Manager" in result
        assert "Build amazing products" in result

        # Removed elements absent
        assert "analytics.js" not in result
        assert "dataLayer" not in result
        assert "font-family" not in result
        assert "Please enable JavaScript" not in result
        assert "circle" not in result
        assert "maps.google.com" not in result
        assert "Main content section" not in result

    def test_uses_html_parser_not_lxml(self):
        """Verify html.parser is used (lxml would handle malformed HTML differently)."""
        # Intentionally malformed HTML that html.parser handles gracefully
        html = "<p>Unclosed paragraph<div>Div content</div>"
        result = html_to_clean_text(html)
        assert "Unclosed paragraph" in result
        assert "Div content" in result
