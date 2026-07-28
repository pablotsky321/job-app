"""
Pure filter/sort/staleness logic for vacancy listing.

Provides:
- build_vacancy_listing: Pure function (no I/O, no boto3) that filters, sorts,
  flags staleness, and assembles vacancy listing records from plain dicts.

Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.10
"""

from typing import Optional


def build_vacancy_listing(
    usuario_vacantes: list[dict],
    vacantes_by_id: dict,
    profile_version: Optional[int],
    estado_filter: str,
) -> list[dict]:
    """
    Pure function that filters, sorts, and flags staleness for vacancy listing.

    Args:
        usuario_vacantes: List of UsuarioVacante records as plain dicts.
            Each dict must have at minimum: companyId, vacancyId, estado,
            score (nullable), scoreProfileVersion (nullable), appliedAt (nullable).
        vacantes_by_id: Dict keyed by "{companyId}#{vacancyId}" with Vacante+Empresa
            summary data (titulo, descripcion, modalidad, ubicacion, url, lastSeenAt,
            empresa_nombre, empresa_plataforma, etc.).
        profile_version: The user's current Perfiles.profileVersion (nullable).
        estado_filter: "activas" or "aplicadas".

    Returns:
        List of dicts representing the filtered, sorted vacancy listing.
        Each record includes UsuarioVacante fields (minus cvAtsTexto),
        vacancy info from vacantes_by_id, and a staleFlag boolean.

    Requirements:
        - 1.1: activas → estado ∈ {nueva, vista}
        - 1.2: aplicadas → estado == aplicada
        - 1.6: activas sorted by score desc (nulls last), tie-break lastSeenAt desc
        - 1.7: aplicadas sorted by appliedAt desc
        - 1.8: staleFlag when scoreProfileVersion != profile_version,
                or scoreProfileVersion is None and estado == nueva
        - 1.10: cvAtsTexto NEVER in output
    """
    # Step 1: Filter by estado
    if estado_filter == "activas":
        filtered = [
            uv for uv in usuario_vacantes if uv.get("estado") in ("nueva", "vista")
        ]
    elif estado_filter == "aplicadas":
        filtered = [
            uv for uv in usuario_vacantes if uv.get("estado") == "aplicada"
        ]
    else:
        filtered = []

    # Step 2: Sort
    if estado_filter == "activas":
        # Sort by score descending (nulls last), tie-break by Vacante.lastSeenAt descending
        filtered.sort(
            key=lambda uv: _activas_sort_key(uv, vacantes_by_id),
        )
    elif estado_filter == "aplicadas":
        # Sort by appliedAt descending
        filtered.sort(
            key=lambda uv: uv.get("appliedAt") or "",
            reverse=True,
        )

    # Step 3: Build output with staleness flag, exclude cvAtsTexto
    result = []
    for uv in filtered:
        sk = f"{uv.get('companyId')}#{uv.get('vacancyId')}"
        vacante_info = vacantes_by_id.get(sk, {})

        # Compute staleFlag
        score_profile_version = uv.get("scoreProfileVersion")
        estado = uv.get("estado")

        if score_profile_version is None and estado == "nueva":
            stale_flag = True
        elif score_profile_version is not None and score_profile_version != profile_version:
            stale_flag = True
        else:
            stale_flag = False

        # Build record excluding cvAtsTexto
        record = {}
        for key, value in uv.items():
            if key == "cvAtsTexto":
                continue
            record[key] = value

        # Add vacancy info
        record["vacante"] = vacante_info
        record["staleFlag"] = stale_flag

        result.append(record)

    return result


def _activas_sort_key(uv: dict, vacantes_by_id: dict) -> tuple:
    """
    Sort key for activas: score descending (nulls last),
    tie-broken by Vacante.lastSeenAt descending.
    """
    score = uv.get("score")
    sk = f"{uv.get('companyId')}#{uv.get('vacancyId')}"
    vacante = vacantes_by_id.get(sk, {})
    last_seen_at = vacante.get("lastSeenAt") or ""

    # Primary: score desc, nulls last
    # (0, -score) for non-null scores → lower tuple = higher score
    # (1, 0) for null scores → always after non-null
    if score is None:
        score_key = (1, 0)
    else:
        score_key = (0, -score)

    # Secondary: lastSeenAt descending
    # We invert lexicographic order by complementing each character
    # Simpler: use a negative approach. Since ISO strings sort ascending,
    # we want descending, so we negate by making "later" dates sort first.
    # Trick: prefix with 0 and invert won't work for strings.
    # Instead, we use a tuple where lower = better, so we flip the string.
    # Actually the cleanest approach: since tuples compare element by element,
    # and we want lastSeenAt DESCENDING, we can return the negative of the string's
    # sort position. For ISO 8601 strings, reversing the comparison means
    # we want the complement. Let's just negate character ordinals.
    inverted_last_seen = tuple(-ord(c) for c in last_seen_at) if last_seen_at else ()

    return (score_key, inverted_last_seen)
