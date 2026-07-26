---
inclusion: auto
name: fuera-de-alcance
description: >
  Funcionalidades explícitamente descartadas del MVP, con la razón del corte.
  Consultar antes de implementar algo que no esté pedido en el requirement o task
  actual, para evitar scope creep silencioso.
---

# Fuera de alcance del MVP — no implementar sin que el usuario lo pida explícitamente

- **CV-visual `.docx` con marca de empresa** — contradice el objetivo de CV-ATS en texto
  plano; varios días de trabajo para algo cosmético que además puede confundir a ATS
  estrictos. Roadmap, no MVP.
- **Panel de administración con UI** — módulo completo (rol, backend, frontend) con cero
  valor demostrable ante el jurado. Se hace por consola/CLI de AWS.
- **APIs públicas de empleo (Adzuna, Arbeitnow, Jooble)** — cada una es registro + key +
  esquema + mapeo distinto. Si sobra tiempo, solo RemoteOK (sin auth).
- **BYOK (usuario trae su propia API key)** — choca con el criterio de uso de AWS del
  hackathon y complica el modelo de costos sin beneficio a esta escala.
- **Registro público / multi-tenant** — descartado permanentemente por diseño. Usuarios
  pre-creados con AdminCreateUser, sin auto-registro.
- **Login o scraping con credenciales a LinkedIn/Computrabajo** — riesgo legal de ToS y
  fragilidad técnica. Resuelto por vacante manual (pegar texto + link).
- **Parsers dedicados por ATS más allá de Greenhouse/Lever** (Workday, etc.) — solo si el
  camino genérico HTML→LLM resulta insuficiente en la práctica.
- **Recuperación de contraseña / flujo self-service de cuenta** — no aplica sin registro público.
- **Filtro por idioma requerido** — poco confiable de extraer, poco visible en demo.
- **Pantalla de históricos** de vacantes cerradas — el TTL sí se implementa, la pantalla no.
- **Vista agregada de preguntas por empresa** — GSI aditivo, se puede añadir después sin migración.
- **Descarga automática de vacante por URL** — ver "descargar vacante suelta" en
  decisiones-invertidas.md: se resuelve con texto pegado.