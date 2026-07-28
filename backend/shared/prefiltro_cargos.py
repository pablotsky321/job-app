"""
Prefiltro de cargos: token overlap between vacancy title and user's active job roles.

Pure functions, no I/O. Used by Scoring_Worker to skip irrelevant vacancies
before invoking Bedrock_Client.

Requirements: 16.2-16.7
"""

import os
import re
import unicodedata
from typing import List


# Spanish stopwords — comprehensive list for filtering non-significant tokens
# (Requirement 16.2: discard tokens in a defined stopword list)
STOPWORDS: set = {
    "y", "o", "el", "la", "de", "del", "en", "a", "por", "para",
    "los", "las", "un", "una", "es", "con", "que", "se", "al", "lo",
    "su", "le", "no", "como", "mas", "pero", "sus", "ya", "entre",
    "sin", "sobre", "todo", "esta", "ser", "tambien", "fue", "ha",
    "son", "esta", "cuando", "muy", "nos", "ni",
}


def _remove_diacritics(text: str) -> str:
    """Remove diacritics using NFD normalization and stripping combining characters."""
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")


def get_significant_tokens(text: str) -> set:
    """
    Derive significant tokens from text for cargo comparison.

    Process:
    1. Lowercase
    2. Remove diacritics (NFD normalization, strip combining chars)
    3. Split on whitespace/punctuation (any non-alphanumeric boundary)
    4. Remove stopwords
    5. Filter tokens shorter than 2 characters

    Returns set of remaining tokens.

    Requirements: 16.2
    """
    if not text or not isinstance(text, str):
        return set()

    # 1. Lowercase
    lowered = text.lower()

    # 2. Remove diacritics
    without_diacritics = _remove_diacritics(lowered)

    # 3. Split on any non-alphanumeric boundary
    tokens = re.split(r"[^a-z0-9]+", without_diacritics)

    # 4. Remove stopwords and filter short tokens (< 2 chars)
    significant = {
        token for token in tokens
        if token and len(token) >= 2 and token not in STOPWORDS
    }

    return significant


def _get_threshold() -> int:
    """
    Read threshold from environment variable PREFILTRO_THRESHOLD.
    If unset, empty, or not a positive integer, defaults to 1.

    Requirement 16.3-16.4
    """
    raw = os.environ.get("PREFILTRO_THRESHOLD", "")
    if not raw:
        return 1
    try:
        value = int(raw)
        if value < 1:
            return 1
        return value
    except (ValueError, TypeError):
        return 1


def pasa_prefiltro_cargos(
    titulo_vacante: str,
    cargosActivos: List[str],
    threshold: int = 1,
) -> bool:
    """
    Determine if a vacancy title has enough token overlap with any active cargo.

    - If cargosActivos is empty → return True (bypass prefiltro). Requirement 16.5
    - For each cargo: compute overlap of significant tokens with titulo tokens
    - If overlap >= threshold for ANY cargo → return True. Requirement 16.4
    - Otherwise → return False

    The threshold parameter defaults to 1 (at least one significant token in common).
    In production, Scoring_Worker reads threshold from env via _get_threshold().

    Requirements: 16.4-16.7
    """
    # Requirement 16.5: empty cargosActivos → bypass
    if not cargosActivos:
        return True

    titulo_tokens = get_significant_tokens(titulo_vacante)

    # If titulo has no significant tokens, no overlap possible
    if not titulo_tokens:
        return False

    for cargo in cargosActivos:
        cargo_tokens = get_significant_tokens(cargo)
        if not cargo_tokens:
            continue
        overlap = titulo_tokens & cargo_tokens
        if len(overlap) >= threshold:
            return True

    return False
