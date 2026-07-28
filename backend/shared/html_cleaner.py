"""
HTML cleaning for LLM processing.

Cleans raw HTML before submission to Bedrock models, removing non-content
elements and enforcing a size threshold to stay within token budgets.

Pure function — no AWS dependencies, no network calls.

Requirements: 5.1
Tech rule: BeautifulSoup with html.parser ONLY. PROHIBIDO lxml (binary, fails in Lambda).
"""

import re

from bs4 import BeautifulSoup, Comment


def html_to_clean_text(html: str, max_clean_size_kb: int = 100) -> str:
    """
    Clean HTML for extraction with Bedrock.

    REMOVED (Requirement 5.1):
    - <script> tags and content
    - <style> tags and content
    - <noscript> tags and content
    - <svg> tags and content
    - <iframe> tags and content
    - <meta> tags
    - HTML comments (<!-- -->)

    KEPT:
    - Text content from all remaining tags
    - Basic paragraph structure, lists, headings (as flat text)

    If the cleaned text exceeds max_clean_size_kb, it is TRUNCATED (never skipped,
    never marked as failed). Truncation respects UTF-8 byte boundaries.

    Args:
        html: Raw HTML string to clean.
        max_clean_size_kb: Maximum size in KB of the output text. Default 100 KB
                           (~25k tokens at 4:1 ratio).

    Returns:
        Cleaned plain text string, truncated if necessary.
    """
    if not html or not isinstance(html, str):
        return ""

    # Parse with html.parser (lxml PROHIBITED — binary in Lambda)
    soup = BeautifulSoup(html, "html.parser")

    # 1. Remove dangerous/useless elements
    for tag_name in ["script", "style", "noscript", "svg", "iframe", "meta"]:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # 2. Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # 3. Extract text
    text = soup.get_text(separator=" ", strip=True)

    # 4. Whitespace cleanup: multiple whitespace chars → single space
    text = re.sub(r"\s+", " ", text)
    text = text.strip()

    # 5. Size threshold — TRUNCATE (never skip, never fail)
    max_bytes = max_clean_size_kb * 1024
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        text = encoded[:max_bytes].decode("utf-8", errors="ignore")

    return text
