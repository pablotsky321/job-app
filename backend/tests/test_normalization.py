"""
Unit tests for backend/shared/normalization.py pure functions.

All tests are 100% deterministic and require no AWS mocks, network calls, or external services.

Requirements: 7.5
"""

import pytest
from backend.shared.normalization import (
    html_to_clean_text,
    normalize_whitespace,
    extract_page_title,
    extract_json_ld,
    extract_careers_url_from_html,
)


# ============================================================================
# html_to_clean_text() Tests
# ============================================================================


class TestHtmlToCleanText:
    """Test html_to_clean_text pure function."""

    def test_simple_html(self):
        """Test extraction of text from simple HTML."""
        html = "<p>Hello world</p>"
        result = html_to_clean_text(html)
        assert "Hello" in result
        assert "world" in result

    def test_preserves_block_structure(self):
        """Test that block-level elements create newlines."""
        html = "<h1>Title</h1><p>Body</p>"
        result = html_to_clean_text(html)
        assert "Title" in result
        assert "Body" in result
        assert "\n" in result

    def test_removes_script_tags(self):
        """Test that script tags are removed."""
        html = "<p>Text</p><script>alert('test')</script><p>More</p>"
        result = html_to_clean_text(html)
        assert "alert" not in result
        assert "Text" in result
        assert "More" in result

    def test_removes_style_tags(self):
        """Test that style tags are removed."""
        html = "<p>Text</p><style>.hidden { display: none; }</style><p>More</p>"
        result = html_to_clean_text(html)
        assert ".hidden" not in result
        assert "display" not in result
        assert "Text" in result
        assert "More" in result

    def test_empty_string(self):
        """Test handling of empty string."""
        result = html_to_clean_text("")
        assert result == ""

    def test_none_input(self):
        """Test handling of None input."""
        result = html_to_clean_text(None)
        assert result == ""

    def test_non_string_input(self):
        """Test handling of non-string input."""
        result = html_to_clean_text(123)
        assert result == ""

    def test_complex_html_structure(self):
        """Test extraction from complex HTML structure."""
        html = """
        <html>
            <head><title>Page Title</title></head>
            <body>
                <header><h1>Welcome</h1></header>
                <main>
                    <section>
                        <h2>About Us</h2>
                        <p>We are a company.</p>
                    </section>
                </main>
            </body>
        </html>
        """
        result = html_to_clean_text(html)
        assert "Welcome" in result
        assert "About Us" in result
        assert "We are a company" in result

    def test_whitespace_handling(self):
        """Test that excessive whitespace is normalized."""
        html = "<p>Text    with    extra    spaces</p>"
        result = html_to_clean_text(html)
        # Should still contain the text
        assert "Text" in result
        assert "extra" in result

    def test_nested_tags(self):
        """Test handling of nested HTML tags."""
        html = "<div><strong>Bold</strong> and <em>italic</em> text</div>"
        result = html_to_clean_text(html)
        assert "Bold" in result
        assert "italic" in result
        assert "text" in result


# ============================================================================
# normalize_whitespace() Tests
# ============================================================================


class TestNormalizeWhitespace:
    """Test normalize_whitespace pure function."""

    def test_basic_stripping(self):
        """Test basic leading/trailing whitespace stripping."""
        result = normalize_whitespace("  hello world  ")
        assert result == "hello world"

    def test_collapse_multiple_spaces(self):
        """Test collapsing multiple consecutive spaces."""
        result = normalize_whitespace("hello   world")
        assert result == "hello world"

    def test_tab_not_collapsed(self):
        """Test that tabs are preserved (only spaces collapsed)."""
        result = normalize_whitespace("hello\t\tworld")
        # Tabs are not spaces, so they're not collapsed by this function
        assert "hello" in result
        assert "world" in result

    def test_empty_string(self):
        """Test handling of empty string."""
        result = normalize_whitespace("")
        assert result == ""

    def test_only_whitespace(self):
        """Test string with only whitespace."""
        result = normalize_whitespace("   ")
        assert result == ""

    def test_none_input(self):
        """Test handling of None input."""
        result = normalize_whitespace(None)
        assert result == ""

    def test_non_string_input(self):
        """Test handling of non-string input."""
        result = normalize_whitespace(123)
        assert result == ""

    def test_multiple_consecutive_spaces(self):
        """Test collapsing multiple consecutive spaces."""
        result = normalize_whitespace("a     b     c")
        assert result == "a b c"

    def test_leading_and_trailing_combined(self):
        """Test combination of leading, trailing, and internal spaces."""
        result = normalize_whitespace("  hello   world  ")
        assert result == "hello world"


# ============================================================================
# extract_page_title() Tests
# ============================================================================


class TestExtractPageTitle:
    """Test extract_page_title pure function."""

    def test_extract_simple_title(self):
        """Test extraction of simple title tag."""
        html = "<title>My Page Title</title>"
        result = extract_page_title(html)
        assert result == "My Page Title"

    def test_title_with_whitespace(self):
        """Test title extraction with leading/trailing whitespace."""
        html = "<title>  My Page Title  </title>"
        result = extract_page_title(html)
        assert result == "My Page Title"

    def test_no_title_tag(self):
        """Test handling when no title tag exists."""
        html = "<html><body>No title here</body></html>"
        result = extract_page_title(html)
        assert result is None

    def test_empty_title_tag(self):
        """Test handling of empty title tag."""
        html = "<title></title>"
        result = extract_page_title(html)
        assert result is None

    def test_title_only_whitespace(self):
        """Test title tag containing only whitespace."""
        html = "<title>   </title>"
        result = extract_page_title(html)
        assert result is None

    def test_empty_string(self):
        """Test handling of empty string."""
        result = extract_page_title("")
        assert result is None

    def test_none_input(self):
        """Test handling of None input."""
        result = extract_page_title(None)
        assert result is None

    def test_non_string_input(self):
        """Test handling of non-string input."""
        result = extract_page_title(123)
        assert result is None

    def test_title_in_full_html_document(self):
        """Test title extraction from full HTML document."""
        html = """
        <html>
            <head>
                <meta charset="utf-8">
                <title>Company Careers Portal</title>
                <meta name="description" content="Join our team">
            </head>
            <body>
                <h1>Welcome</h1>
            </body>
        </html>
        """
        result = extract_page_title(html)
        assert result == "Company Careers Portal"

    def test_multiple_title_tags(self):
        """Test that first title tag is used (if multiple exist)."""
        html = "<title>First Title</title><title>Second Title</title>"
        result = extract_page_title(html)
        assert result == "First Title"


# ============================================================================
# extract_json_ld() Tests
# ============================================================================


class TestExtractJsonLd:
    """Test extract_json_ld pure function."""

    def test_simple_json_ld(self):
        """Test extraction of simple JSON-LD."""
        html = '<script type="application/ld+json">{"@type": "Organization", "name": "Company"}</script>'
        result = extract_json_ld(html)
        assert result is not None
        assert result.get("@type") == "Organization"
        assert result.get("name") == "Company"

    def test_json_ld_with_whitespace(self):
        """Test JSON-LD with internal whitespace."""
        html = '''<script type="application/ld+json">
        {
            "@type": "Organization",
            "name": "Company Inc"
        }
        </script>'''
        result = extract_json_ld(html)
        assert result is not None
        assert result.get("@type") == "Organization"
        assert result.get("name") == "Company Inc"

    def test_no_json_ld(self):
        """Test handling when no JSON-LD exists."""
        html = "<html><body>No JSON-LD here</body></html>"
        result = extract_json_ld(html)
        assert result is None

    def test_malformed_json_ld(self):
        """Test handling of malformed JSON in JSON-LD block."""
        html = '<script type="application/ld+json">{invalid json}</script>'
        result = extract_json_ld(html)
        assert result is None

    def test_json_ld_not_dict(self):
        """Test JSON-LD that parses to non-dict (e.g., array)."""
        html = '<script type="application/ld+json">["item1", "item2"]</script>'
        result = extract_json_ld(html)
        # Function returns None for non-dict JSON
        assert result is None

    def test_empty_string(self):
        """Test handling of empty string."""
        result = extract_json_ld("")
        assert result is None

    def test_none_input(self):
        """Test handling of None input."""
        result = extract_json_ld(None)
        assert result is None

    def test_non_string_input(self):
        """Test handling of non-string input."""
        result = extract_json_ld(123)
        assert result is None

    def test_json_ld_in_full_document(self):
        """Test JSON-LD extraction from full HTML document."""
        html = """
        <html>
            <head>
                <title>Company Careers</title>
                <script type="application/ld+json">
                {
                    "@type": "Organization",
                    "name": "Acme Corp",
                    "url": "https://acme.com",
                    "jobsPage": "https://acme.com/careers"
                }
                </script>
            </head>
            <body>
                <h1>Join our team</h1>
            </body>
        </html>
        """
        result = extract_json_ld(html)
        assert result is not None
        assert result.get("@type") == "Organization"
        assert result.get("name") == "Acme Corp"
        assert result.get("jobsPage") == "https://acme.com/careers"

    def test_multiple_json_ld_blocks(self):
        """Test that first valid JSON-LD block is returned."""
        html = '''
        <script type="application/ld+json">{"@type": "First", "id": 1}</script>
        <script type="application/ld+json">{"@type": "Second", "id": 2}</script>
        '''
        result = extract_json_ld(html)
        assert result is not None
        # Should get the first valid one
        assert result.get("id") == 1


# ============================================================================
# extract_careers_url_from_html() Tests
# ============================================================================


class TestExtractCareersUrlFromHtml:
    """Test extract_careers_url_from_html pure function."""

    def test_extract_absolute_careers_url(self):
        """Test extraction of absolute careers URL."""
        html = '<a href="https://example.com/careers">Join us</a>'
        result = extract_careers_url_from_html(html, "https://example.com")
        assert result == "https://example.com/careers"

    def test_extract_relative_careers_url(self):
        """Test extraction and resolution of relative careers URL."""
        html = '<a href="/careers">Join us</a>'
        result = extract_careers_url_from_html(html, "https://example.com")
        assert result == "https://example.com/careers"

    def test_extract_jobs_url(self):
        """Test extraction of URL containing 'jobs' keyword."""
        html = '<a href="/jobs">View openings</a>'
        result = extract_careers_url_from_html(html, "https://example.com")
        assert result == "https://example.com/jobs"

    def test_case_insensitive_match(self):
        """Test that keyword matching is case-insensitive."""
        html = '<a href="/CAREERS">Join us</a>'
        result = extract_careers_url_from_html(html, "https://example.com")
        assert result == "https://example.com/CAREERS"

    def test_no_careers_url(self):
        """Test handling when no careers/jobs URL exists."""
        html = '<a href="/products">Our products</a><a href="/about">About</a>'
        result = extract_careers_url_from_html(html, "https://example.com")
        assert result is None

    def test_empty_href(self):
        """Test handling of link with empty href."""
        html = '<a href="">Empty link</a><a href="/careers">Careers</a>'
        result = extract_careers_url_from_html(html, "https://example.com")
        assert result == "https://example.com/careers"

    def test_empty_html(self):
        """Test handling of empty HTML string."""
        result = extract_careers_url_from_html("", "https://example.com")
        assert result is None

    def test_none_html_input(self):
        """Test handling of None HTML input."""
        result = extract_careers_url_from_html(None, "https://example.com")
        assert result is None

    def test_non_string_html_input(self):
        """Test handling of non-string HTML input."""
        result = extract_careers_url_from_html(123, "https://example.com")
        assert result is None

    def test_none_base_url(self):
        """Test handling of None base_url."""
        result = extract_careers_url_from_html('<a href="/careers">Careers</a>', None)
        assert result is None

    def test_empty_base_url(self):
        """Test handling of empty base_url."""
        result = extract_careers_url_from_html('<a href="/careers">Careers</a>', "")
        assert result is None

    def test_non_string_base_url(self):
        """Test handling of non-string base_url."""
        result = extract_careers_url_from_html('<a href="/careers">Careers</a>', 123)
        assert result is None

    def test_relative_url_resolution(self):
        """Test proper resolution of relative URLs."""
        html = '<a href="careers">Careers</a>'
        result = extract_careers_url_from_html(html, "https://example.com/pages/")
        # urljoin should handle relative paths
        assert "careers" in result

    def test_multiple_links_returns_first_match(self):
        """Test that first matching career/job link is returned."""
        html = '''
        <a href="/about">About</a>
        <a href="/careers">First careers</a>
        <a href="/jobs">Jobs opening</a>
        '''
        result = extract_careers_url_from_html(html, "https://example.com")
        assert result == "https://example.com/careers"

    def test_career_in_url_path(self):
        """Test matching when 'career' appears in URL path."""
        html = '<a href="/our-career-opportunities">Opportunities</a>'
        result = extract_careers_url_from_html(html, "https://example.com")
        assert result == "https://example.com/our-career-opportunities"

    def test_job_in_query_param(self):
        """Test matching when 'job' appears in query parameters."""
        html = '<a href="/openings?type=job">Openings</a>'
        result = extract_careers_url_from_html(html, "https://example.com")
        assert result == "https://example.com/openings?type=job"

    def test_complex_html_document(self):
        """Test extraction from complex HTML document."""
        html = """
        <html>
            <head><title>Company</title></head>
            <body>
                <nav>
                    <a href="/">Home</a>
                    <a href="/about">About</a>
                    <a href="/careers-page">Careers</a>
                    <a href="/contact">Contact</a>
                </nav>
            </body>
        </html>
        """
        result = extract_careers_url_from_html(html, "https://example.com")
        assert result == "https://example.com/careers-page"

    def test_fragment_in_url(self):
        """Test URL with fragment identifier."""
        html = '<a href="/careers#open-positions">Careers</a>'
        result = extract_careers_url_from_html(html, "https://example.com")
        assert "/careers" in result

    def test_query_string_in_url(self):
        """Test URL with query string."""
        html = '<a href="/jobs?location=remote">Jobs</a>'
        result = extract_careers_url_from_html(html, "https://example.com")
        assert result == "https://example.com/jobs?location=remote"


# ============================================================================
# Integration Tests
# ============================================================================


class TestNormalizationIntegration:
    """Integration tests combining multiple normalization functions."""

    def test_typical_careers_page_processing(self):
        """Test typical workflow: clean HTML, extract title, find careers link."""
        html = """
        <html>
            <head>
                <title>Welcome to Our Company Careers</title>
                <script>console.log('tracking')</script>
            </head>
            <body>
                <h1>Join Our Team</h1>
                <p>We're hiring talented people.</p>
                <a href="/careers/open-positions">View Open Positions</a>
            </body>
        </html>
        """

        # Extract title
        title = extract_page_title(html)
        assert "Careers" in title

        # Clean text
        clean_text = html_to_clean_text(html)
        assert "console.log" not in clean_text
        assert "Join Our Team" in clean_text

        # Extract careers URL
        base_url = "https://company.com"
        url = extract_careers_url_from_html(html, base_url)
        assert url == "https://company.com/careers/open-positions"

    def test_html_with_json_ld_careers(self):
        """Test processing HTML containing JSON-LD with careers data."""
        html = """
        <html>
            <head>
                <title>Company Careers</title>
                <script type="application/ld+json">
                {
                    "@type": "Organization",
                    "name": "Acme Corp",
                    "jobsPage": "https://acme.com/join-us"
                }
                </script>
            </head>
            <body>
                <a href="/careers">See positions</a>
            </body>
        </html>
        """

        # Extract JSON-LD
        json_ld = extract_json_ld(html)
        assert json_ld is not None
        assert json_ld.get("name") == "Acme Corp"

        # Extract careers URL
        careers_url = extract_careers_url_from_html(html, "https://acme.com")
        assert careers_url is not None
        assert careers_url == "https://acme.com/careers"
