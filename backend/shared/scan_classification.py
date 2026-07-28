"""
Scan result classification — pure function.

Classifies the outcome of a Cascada_Descubrimiento for a single Empresa
into exactly one of: OK, FAILED, EMPTY_SOSPECHOSO, EMPTY_LEGITIMO.

This is a PURE function: no I/O, no AWS, no side effects.

Requirements: 6.1-6.6
"""

from typing import List, Optional, Tuple

from backend.shared.models import Empresa


def classify_scan_result(
    empresa: Empresa,
    extraction_result: Tuple[Optional[list], Optional[str], Optional[str]],
) -> str:
    """Classify the result of a scan cascade for a single empresa.

    Decision table (Requirement 6, exhaustive, mutually exclusive):

    | Classification     | Condition                                            |
    |--------------------|------------------------------------------------------|
    | FAILED             | error is not None                                    |
    | OK                 | error is None AND len(vacancies) > 0                 |
    | EMPTY_SOSPECHOSO   | error is None AND vacancies == 0 AND lastVacancy > 0 |
    | EMPTY_LEGITIMO     | error is None AND vacancies == 0 AND lastVacancy == 0|

    Args:
        empresa: The Empresa being scanned. Uses lastVacancyCount field.
        extraction_result: Tuple of (vacancies_list, origen, error) from
            cascada_descubrimiento. vacancies_list may be None or empty list.

    Returns:
        Exactly one of: 'OK', 'FAILED', 'EMPTY_SOSPECHOSO', 'EMPTY_LEGITIMO'.
    """
    vacantes_list, origen, error = extraction_result
    num_vacantes = len(vacantes_list) if vacantes_list else 0

    # CASE 1: Error present → FAILED (Requirement 6.3)
    if error is not None:
        return "FAILED"

    # CASE 2: Valid response with N > 0 vacancies → OK (Requirement 6.2)
    if num_vacantes > 0:
        return "OK"

    # CASE 3: Valid response, 0 vacancies, lastVacancyCount > 0 → EMPTY_SOSPECHOSO (Req 6.4)
    if empresa.lastVacancyCount > 0:
        return "EMPTY_SOSPECHOSO"

    # CASE 4: Valid response, 0 vacancies, lastVacancyCount == 0 → EMPTY_LEGITIMO (Req 6.5)
    return "EMPTY_LEGITIMO"
