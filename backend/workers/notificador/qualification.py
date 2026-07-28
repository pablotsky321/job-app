"""
Pure qualified-vacancy determination logic for Notificador Lambda.

No I/O, no boto3 — operates only on plain data structures.

Requirements: 7.3, 7.5
"""


def determine_qualified_vacancies(
    usuario_vacantes: list[dict],
    empresas_completadas: set[str],
    started_at: str,
) -> list[dict]:
    """
    Determine which vacancies qualify for notification.

    A vacancy qualifies when:
    - UsuarioVacante.estado == "nueva" (NEVER filtered_out or any other estado)
    - Vacante.firstSeenAt >= startedAt (ISO 8601 string comparison)
    - UsuarioVacante.companyId ∈ empresas_completadas

    Args:
        usuario_vacantes: List of dicts, each with keys: estado, companyId, vacancyId,
                          firstSeenAt (from the Vacante), score, titulo, etc.
        empresas_completadas: Set of companyIds that were successfully scanned
        started_at: ISO string of ScanJob.startedAt

    Returns:
        List of qualifying vacancy dicts
    """
    qualified = []
    for uv in usuario_vacantes:
        # Only estado == "nueva" qualifies
        if uv.get("estado") != "nueva":
            continue

        # companyId must be in empresasCompletadas
        if uv.get("companyId") not in empresas_completadas:
            continue

        # firstSeenAt must be >= startedAt (ISO 8601 string comparison works for timestamps)
        first_seen_at = uv.get("firstSeenAt", "")
        if not first_seen_at or first_seen_at < started_at:
            continue

        qualified.append(uv)

    return qualified


def should_send_email(qualified_vacancies: list[dict]) -> bool:
    """Returns False when the list is empty (zero-vacancies guard)."""
    return len(qualified_vacancies) > 0
