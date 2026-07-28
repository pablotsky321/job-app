"""
MissCount increment and vacancy closure logic.

Pure function — no I/O, no AWS. Applies missCount rules to determine
which vacancies to increment, reset, close, or reopen after an OK-classified scan.

Requirements: 7.1-7.7
"""

from datetime import datetime
from typing import List

from backend.shared.extraction import VacancyExtracted, compute_vacancyId
from backend.shared.models import Empresa, Vacante


def apply_missCount_logic(
    empresa: Empresa,
    vacantes_nuevas_en_escan: List[VacancyExtracted],
    vacantes_existentes: List[Vacante],
    origen: str = "automated",
) -> List[Vacante]:
    """Apply missCount logic after an OK-classified scan.

    PRECONDITION: Only call this function when scan classification == OK.

    For each EXISTING vacancy:
      - Req 7.1: If vacancyId NOT in scan result AND estado='abierta': missCount += 1
      - Req 7.2: If vacancyId IS in scan result: missCount = 0
      - Req 7.3: If estado was 'cerrada' AND vacancyId in scan: estado = 'abierta'
      - Req 7.4: If missCount >= 2 AND origen != 'manual': estado = 'cerrada'
      - Req 7.5: Manual origin NEVER auto-closes regardless of missCount
      - Req 7.7: When found in scan, update lastSeenAt (verificadaAt) without
                 modifying vacancyId or firstSeenAt (crawledAt)

    For each NEW vacancy in scan (not in existing):
      - Req 7.6: Create Vacante with vacancyId = SHA-256(url), missCount = 0,
                 estado = 'abierta', firstSeenAt = now

    Args:
        empresa: The company being scanned.
        vacantes_nuevas_en_escan: Vacancies found in the current scan result.
        vacantes_existentes: Previously stored vacancies for this company.
        origen: Extraction method origin ('board_api', 'json_ld', 'html_llm')
                used when creating NEW vacancy records.

    Returns:
        List of updated and new Vacante records ready for DynamoDB upsert.
    """
    now = datetime.utcnow()

    # Build set of vacancy IDs found in the current scan
    scan_vacancy_ids: set[str] = {
        compute_vacancyId(v.url) for v in vacantes_nuevas_en_escan
    }

    # Build lookup from vacancyId → VacancyExtracted for new vacancy data
    scan_vacancy_map: dict[str, VacancyExtracted] = {
        compute_vacancyId(v.url): v for v in vacantes_nuevas_en_escan
    }

    # Track existing vacancy IDs to detect truly new ones
    existing_ids: set[str] = {v.vacanteSha256 for v in vacantes_existentes}

    result: List[Vacante] = []

    # 1. Process EXISTING vacancies
    for vacante in vacantes_existentes:
        if vacante.vacanteSha256 in scan_vacancy_ids:
            # Requirement 7.2: Reset missCount to 0
            vacante.missCount = 0

            # Requirement 7.3: Reopen if closed
            if vacante.cerrada:
                vacante.cerrada = False

            # Requirement 7.7: Update lastSeenAt (verificadaAt), don't touch crawledAt
            vacante.verificadaAt = now
        else:
            # Requirement 7.1: Increment missCount ONLY for abierta vacancies
            if not vacante.cerrada:
                vacante.missCount += 1

            # Requirement 7.4: Close if missCount >= 2 AND not manual
            # Requirement 7.5: Manual origin NEVER auto-closes
            if vacante.missCount >= 2 and vacante.origen != "manual":
                vacante.cerrada = True

        result.append(vacante)

    # 2. Process NEW vacancies (in scan but not in existing)
    for vacancy_id, extracted in scan_vacancy_map.items():
        if vacancy_id not in existing_ids:
            # Requirement 7.6: Create new vacancy
            new_vacante = Vacante(
                vacanteSha256=vacancy_id,
                companyId=empresa.companyId,
                titulo=extracted.titulo,
                descripcion=extracted.descripcion,
                modalidad=extracted.modalidad,
                ubicacion=extracted.ubicacion,
                url=extracted.url,
                plataforma=empresa.plataforma,
                origen=origen,
                crawledAt=now,
                verificadaAt=now,
                missCount=0,
                cerrada=False,
            )
            result.append(new_vacante)

    return result
