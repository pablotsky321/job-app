---
inclusion: always
---

# Trampas que se han roto silenciosamente antes. Revisar en cada módulo.

- **EMPTY_SOSPECHOSO**: 0 vacantes con lastVacancyCount > 0 NO significa que la empresa
  cerró todo. Significa casi siempre que el JavaScript no renderizó y llegó un cascarón
  con HTTP 200. Se trata como fallo: no se toca ninguna vacante existente.
- **Cierre con margen**: una vacante solo pasa a `cerrada` con missCount >= 2, y solo tras
  un escaneo clasificado OK. Las vacantes con origen = manual NUNCA se auto-cierran.
- **Clave de deduplicación** = SHA-256 de la URL normalizada. Jamás empresa+cargo+ubicación:
  el título y la ubicación los produce un LLM y no son deterministas.
- **Jobs zombis**: si now - startedAt > 10 min, el ScanJob pasa a PARCIAL con la lista de
  empresas no completadas, en vez de quedarse en RUNNING para siempre.
- **modalidad**: si la fuente no lo dice, el valor es `sin_dato`. Prohibido inferirlo o adivinarlo.
- **Concurrencia reservada** obligatoria en los workers (scan-worker: 5, scoring-worker: 3).
  Sin esto se revienta la cuota de tokens por minuto de Bedrock en cuentas nuevas.
- **Quitar ≠ borrar**: desuscribirse de una empresa pone `activa = false` en Suscripciones.
  La empresa nunca se elimina de la tabla Empresas.
- **IDs de modelo de Bedrock**: varios modelos actuales solo se invocan vía inference
  profiles entre regiones (prefijo `us.`), no con el ID base. Falla con un error poco
  descriptivo si se usa el ID equivocado.
- **CloudFront + SPA**: los códigos 403 y 404 deben mapearse a `/index.html` con status 200,
  o cualquier ruta profunda falla al recargar la página.

# Tests

Solo funciones puras. NO generar una suite completa con mocks de AWS (moto, etc.).
Cubrir específicamente:
- normalización de URL y hash de deduplicación
- limpieza de HTML antes de pasarlo al LLM
- detección de plataforma (greenhouse/lever/jsonld/html) desde una URL
- prefiltro de cargos (solapamiento de tokens)
- lógica de missCount y clasificación de resultado de escaneo (OK/FAILED/EMPTY_SOSPECHOSO/EMPTY_LEGITIMO)