---
inclusion: always
---

# Trampas que se han roto silenciosamente antes. Revisar en cada módulo.

- **EMPTY_SOSPECHOSO**: 0 vacantes con lastVacancyCount > 0 NO significa "la empresa cerró todo".
  Significa casi siempre que el JavaScript no renderizó y llegó un cascarón con HTTP 200.
  Se trata como fallo: no se toca ninguna vacante.
- **Cierre con margen**: una vacante solo pasa a `cerrada` con missCount >= 2, y solo tras un escaneo OK.
  Las vacantes con origen = manual NUNCA se auto-cierran.
- **Visibility timeout de SQS** debe ser 6× el timeout de la Lambda consumidora.
- **Clave de deduplicación** = SHA-256 de la URL normalizada. Jamás empresa+cargo+ubicación:
  el título y la ubicación los produce un LLM y no son deterministas.
- **Jobs zombis**: si now - startedAt > 10 min, el ScanJob pasa a PARCIAL con la lista de empresas no completadas.
- **modalidad**: si la fuente no lo dice, el valor es `sin_dato`. Prohibido inferirlo o adivinarlo.
- **Concurrencia reservada** obligatoria en los workers (scan-worker: 5, scoring-worker: 3).
  Sin esto se revienta la cuota de tokens por minuto de Bedrock.
- **Quitar ≠ borrar**: desuscribirse de una empresa pone activa=false. La empresa nunca se elimina.

# Tests

Solo funciones puras. NO generar una suite con mocks de AWS (moto, etc.).
Cubrir: normalización de URL y hash de dedup, limpieza de HTML, detección de plataforma desde URL,
prefiltro de cargos, lógica de missCount y clasificación de resultado de escaneo.