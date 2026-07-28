"""
Pure email body/subject construction for Notificador Lambda.

No I/O, no boto3 — operates only on plain data structures.

Requirements: 7.4, design Section 7 (Email Body Structure)
"""

from datetime import datetime, timezone


def build_notification_email(
    user_display_data: dict,
    qualified_vacancies: list[dict],
) -> tuple[str, str]:
    """
    Build notification email subject and body.

    Args:
        user_display_data: Dict with user info (e.g., nombre or email for greeting)
        qualified_vacancies: List of vacancy dicts with: titulo, empresa_nombre,
                            plataforma, ubicacion, modalidad, url, score, descripcion,
                            cvAtsTexto (optional)

    Returns:
        Tuple of (subject, body)

    Subject format: "{count} nuevas vacante(s) de interés - {fecha_UTC}"
    Body: Plain text (no HTML), at most 5 vacancies per call.
    Description truncated to 250 chars, cvAtsTexto to 500 chars.
    """
    # Limit to 5 vacancies per email
    vacancies_to_include = qualified_vacancies[:5]
    count = len(vacancies_to_include)

    # Build subject
    fecha_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"{count} nuevas vacante(s) de interés - {fecha_utc}"

    # Build body
    usuario_nombre = user_display_data.get("nombre", "usuario")
    lines: list[str] = []

    lines.append(f"Hola {usuario_nombre},")
    lines.append("")
    lines.append(
        f"Se encontraron {count} nueva(s) vacante(s) que coinciden con tu perfil:"
    )
    lines.append("")

    separator_thick = "=" * 60
    separator_thin = "-" * 60

    lines.append(separator_thick)

    for i, vacancy in enumerate(vacancies_to_include, start=1):
        titulo = vacancy.get("titulo", "Sin título")
        empresa_nombre = vacancy.get("empresa_nombre", "Empresa desconocida")
        plataforma = vacancy.get("plataforma", "")
        ubicacion = vacancy.get("ubicacion", "")
        modalidad = vacancy.get("modalidad", "sin_dato")
        url = vacancy.get("url", "")
        score = vacancy.get("score")
        descripcion = vacancy.get("descripcion", "")
        cv_ats_texto = vacancy.get("cvAtsTexto")
        company_id = vacancy.get("companyId", "")
        vacancy_id = vacancy.get("vacancyId", "")

        lines.append("")
        lines.append(f"VACANTE {i}: {titulo}")
        lines.append(f"Empresa: {empresa_nombre}")
        lines.append(f"Plataforma: {plataforma}")
        lines.append(f"Ubicación: {ubicacion}")
        lines.append(f"Modalidad: {modalidad}")
        lines.append(f"URL: {url}")

        if score is not None:
            lines.append(f"Score: {score}")
        else:
            lines.append("Score: pendiente")

        lines.append("")
        lines.append("Resumen:")
        lines.append(_truncate(descripcion, 250))

        # Include cvAtsTexto only if present and non-empty
        if cv_ats_texto:
            lines.append("")
            lines.append(f'CV Personalizado para "{titulo}":')
            lines.append("")
            lines.append(_truncate(cv_ats_texto, 500))

        lines.append("")
        if i < count:
            lines.append(separator_thin)

    lines.append("")
    lines.append(separator_thick)
    lines.append("")
    lines.append("Acciones:")
    lines.append("- Ver perfil: https://app.job-app.com/profile")
    lines.append("- Editar suscripciones: https://app.job-app.com/subscriptions")
    lines.append("")
    lines.append("Saludos,")
    lines.append("Job App Team")

    body = "\n".join(lines)
    return subject, body


def _truncate(text: str, max_length: int) -> str:
    """Truncate text to max_length, adding ellipsis if truncated."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."
