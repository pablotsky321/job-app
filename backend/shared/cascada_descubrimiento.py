"""
Cascada de Descubrimiento — orchestrator for vacancy extraction.

Pure function that routes an Empresa through the cascade of extraction methods
based on its plataforma, stopping at the first method that returns N > 0 vacancies.

Cascade order:
- greenhouse/lever: board_api → json_ld → html_llm
- html/jsonld:      json_ld → html_llm
- manual:           skip all → ([], None, None)

Stop criteria:
- board_api / json_ld: stop ONLY if vacancies > 0 AND no error
- html_llm: ALWAYS accept as final (last resort, no further fallback)

Requirements: 2.1-2.13
"""

from typing import List, Optional, Tuple

from backend.shared.board_api_client import board_api_client
from backend.shared.extraction import ExtractionResult, VacancyExtracted
from backend.shared.html_llm_extractor import html_llm_extractor
from backend.shared.json_ld_extractor import json_ld_extractor
from backend.shared.logging_config import get_contextual_logger
from backend.shared.models import Empresa

logger = get_contextual_logger(__name__)

# Type alias for the cascade return tuple
CascadaResult = Tuple[List[VacancyExtracted], Optional[str], Optional[str]]

# Method sequences by plataforma
_SEQUENCES = {
    "greenhouse": ["board_api", "json_ld", "html_llm"],
    "lever": ["board_api", "json_ld", "html_llm"],
    "html": ["json_ld", "html_llm"],
    "jsonld": ["json_ld", "html_llm"],
}


def _get_extractor(metodo: str):
    """Resolve extractor function by method name.

    Uses late binding so that unit tests can patch the module-level names
    (board_api_client, json_ld_extractor, html_llm_extractor) and have
    the cascade pick up the patched versions.
    """
    if metodo == "board_api":
        return board_api_client
    elif metodo == "json_ld":
        return json_ld_extractor
    elif metodo == "html_llm":
        return html_llm_extractor
    raise ValueError(f"Unknown method: {metodo}")


def cascada_descubrimiento(empresa: Empresa) -> CascadaResult:
    """Execute the discovery cascade for a given Empresa.

    Routes through extraction methods based on plataforma, stopping at the
    first method that yields N > 0 vacancies without error.

    html_llm is always the LAST method and its result is accepted as final
    regardless of vacancy count or error status.

    Args:
        empresa: The Empresa to scan.

    Returns:
        Tuple of (vacancies, origen, error):
        - vacancies: List[VacancyExtracted] found (may be empty)
        - origen: str identifying the method that produced the result, or None
        - error: str with error description, or None if successful
    """
    plataforma = empresa.plataforma.value

    # Requirement 2.11, 2.13: manual → skip all methods entirely
    if plataforma == "manual":
        logger.info(
            "cascada_skip_manual",
            context={"companyId": empresa.companyId},
        )
        return ([], None, None)

    # Determine method sequence based on plataforma
    metodos = _SEQUENCES.get(plataforma)
    if metodos is None:
        logger.warning(
            "cascada_unknown_plataforma",
            context={
                "companyId": empresa.companyId,
                "plataforma": plataforma,
            },
        )
        return ([], None, f"unknown_plataforma: {plataforma}")

    for metodo in metodos:
        extractor_fn = _get_extractor(metodo)

        try:
            result: ExtractionResult = extractor_fn(empresa)
        except Exception as e:
            # Unhandled exception from extractor → log and continue to next method
            logger.warning(
                "cascada_method_exception",
                context={
                    "companyId": empresa.companyId,
                    "metodo": metodo,
                    "error_type": type(e).__name__,
                    "error": str(e)[:200],
                },
            )
            # If this was html_llm (final), we have no more methods to try
            if metodo == "html_llm":
                return ([], "html_llm", f"exception: {type(e).__name__}: {str(e)[:200]}")
            continue

        # html_llm is FINAL — accept result regardless of vacancies or error (Req 2.7)
        if metodo == "html_llm":
            if result.error:
                logger.info(
                    "cascada_html_llm_final_with_error",
                    context={
                        "companyId": empresa.companyId,
                        "error": result.error[:200],
                    },
                )
                return ([], result.origen, result.error)
            logger.info(
                "cascada_html_llm_final",
                context={
                    "companyId": empresa.companyId,
                    "vacancies_count": len(result.vacancies),
                },
            )
            return (result.vacancies, result.origen, None)

        # For board_api / json_ld: stop ONLY if no error AND vacancies > 0 (Req 2.2, 2.5)
        if result.error is None and len(result.vacancies) > 0:
            logger.info(
                "cascada_stop_success",
                context={
                    "companyId": empresa.companyId,
                    "metodo": metodo,
                    "vacancies_count": len(result.vacancies),
                },
            )
            return (result.vacancies, result.origen, None)

        # 0 vacancies or error → continue to next method (Req 2.3, 2.6)
        logger.info(
            "cascada_method_fallthrough",
            context={
                "companyId": empresa.companyId,
                "metodo": metodo,
                "vacancies_count": len(result.vacancies),
                "has_error": result.error is not None,
            },
        )

    # Should not be reached since html_llm is always last and handled above,
    # but as a safety fallback:
    return ([], None, "all_methods_failed")
