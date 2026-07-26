---
inclusion: manual
---

# Contexto técnico — Frontend

> Recorte autosuficiente de contexto_maestro_job_search.md para la spec de frontend.
> No requiere leer contexto-tecnico-backend.md ni contexto-tecnico-infra.md.

## Alcance (qué pantallas construye el frontend)

1. Login vía Cognito Hosted UI (Authorization Code + PKCE) — no se construye UI de login propia
2. Onboarding guiado de 4 pasos
3. Perfil: pegar CV → mostrar parseo con IA → editable
4. Selección de cargos objetivo sugeridos + propios
5. Selección de empresas del catálogo semilla
6. Progreso de escaneo asíncrono (polling)
7. Listado de vacantes con score
8. Detalle de vacante con desglose de score y flujo de "Presentarse"
9. Postulaciones hechas / banco de preguntas y notas
10. Descarga/copia de CV-ATS (construida en el navegador, no llama al backend)
11. Vista de fuentes con avisos de fallas

Fuera de alcance: ver `fuera-de-alcance.md`.

## Autenticación

Cognito Hosted UI con Authorization Code + PKCE. `userId` lo determina el backend a partir del JWT;
el frontend nunca lo envía como parámetro. Decisión pendiente de tomar en la spec: dónde vive el
token (memoria vs. localStorage) — memoria es más seguro contra XSS, localStorage sobrevive un
refresh sin re-login; con Hosted UI + PKCE el refresh silencioso es viable de cualquier forma.

## Contratos de API que consume (fuente de verdad: OpenAPI generado por el backend)

Todo detrás del Cognito Authorizer. Los tipos TypeScript se generan con `openapi-typescript` desde
el `openapi.json` que produce FastAPI — no hardcodear tipos de respuesta a mano.

| Método | Ruta | Uso en frontend |
|---|---|---|
| `POST` | `/me/profile/parse` | paso 1 de onboarding |
| `GET` / `PUT` | `/me/profile` | edición de perfil |
| `POST` | `/me/roles/suggest` | paso 2 de onboarding |
| `PUT` | `/me/roles` | confirmar cargos activos |
| `GET` | `/companies` | catálogo para paso 3 de onboarding |
| `POST` | `/companies` | agregar empresa nueva desde la vista de Fuentes |
| `GET` | `/me/companies` | vista de Fuentes (con `lastScanStatus`) |
| `PUT` | `/me/companies/{companyId}` | activar/desactivar en Fuentes |
| `POST` | `/scans` | disparar escaneo manual |
| `GET` | `/scans/{jobId}` | barra de progreso (polling) |
| `GET` | `/me/vacancies?estado=activas\|aplicadas` | listado principal / postulaciones hechas |
| `GET` | `/me/vacancies/{companyId}/{vacancyId}` | detalle de vacante |
| `POST` | `/me/vacancies/manual` | formulario de vacante manual |
| `POST` | `/me/vacancies/{companyId}/{vacancyId}/apply` | botón "Presentarse" / "Guardar" |
| `POST` | `/me/vacancies/{companyId}/{vacancyId}/cv` | botón "Generar hoja de vida" |
| `GET` / `POST` | `/me/vacancies/{companyId}/{vacancyId}/entries` | banco de preguntas y notas |
| `POST` | `/.../entries/{entryId}/answer` | ayuda de IA para redactar respuesta |

## Formato del score que hay que renderizar

```json
{
  "score": 78,
  "veredicto": "buen_encaje",
  "coincidencias": ["Python", "AWS Lambda", "DynamoDB"],
  "faltantes": ["Kubernetes", "3 años de experiencia (tienes 1)"],
  "resumen": "Encaja con tu stack de backend serverless; el requisito de K8s es el vacío principal."
}
```
`veredicto` ∈ `{ excelente, buen_encaje, parcial, bajo }` — cada uno con su propio color de badge.

**Rescoring híbrido:** cuando el usuario guarda perfil o cargos, el listado puede traer scores
marcados como desactualizados. El backend responde de inmediato con el score viejo; el frontend
debe mostrar un badge "actualizando…" y refrescar a los pocos segundos (polling corto o refetch).
Si el listado está ordenado por score, congelar el orden visual hasta que termine el lote — si no,
las tarjetas saltan de posición bajo los pies del usuario.

## Pantallas

### Onboarding (4 pasos)

1. Pegar CV → parseo → confirmar/editar perfil
2. Confirmar cargos sugeridos + agregar propios
3. Elegir empresas del catálogo semilla
4. Primer escaneo con barra de progreso

Es la experiencia entera del jurado en su primer minuto — no debe aterrizar en un dashboard vacío.

### Listado principal

Tarjeta, en este orden: fecha de publicación (pequeña, izquierda) + ✓ si ya se aplicó, **badge de
score con color** (lo más visible de la pantalla), cargo (título principal), empresa (subtítulo),
lugar/modalidad (subtítulo).

### Detalle de vacante

Descripción completa + desglose del score (coincidencias/faltantes/resumen) + link a la publicación
oficial + botón "Presentarse".

Al presionar "Presentarse", **en la misma vista, sin navegar**: aparece el link listo para copiar y
tres acciones — "Generar hoja de vida" / "Guardar preguntas" / "Guardar" (marca como aplicada sin
generar nada).

### Postulaciones hechas → detalle

Mismo componente visual que el listado principal, sin el check. Al entrar al detalle: descripción +
link oficial, entradas guardadas (cronológicas), CV-ATS generado (botón copiar + botón descargar),
botón "Continuar proceso" (agrega una entrada nueva para rondas posteriores).

### Fuentes

Catálogo compartido + suscripciones propias, con `lastScannedAt`. Con `consecutiveFailures >= 3`
(dato que llega en `/me/companies`), mostrar: *"No hemos podido revisar Empresa X desde el [fecha]"*,
con botones de reintentar y desactivar. Sin esto el listado no es confiable para el usuario.

**UX crítica de escaneo sin cambios:** si el escaneo programado ya corrió recientemente y el usuario
dispara uno manual, puede no haber nada nuevo que mostrar. Esto **no es un fallo** — la UI debe decir
*"Tus 12 empresas están al día — última revisión hace 2 horas"* con la lista y sus timestamps, nunca
un spinner que termina sin explicación.

### Descarga del CV — en el navegador, no en el backend

El CV-ATS llega como texto plano desde `/me/vacancies/{...}/cv` (5–10 KB). La descarga se construye
en el cliente con un `Blob` y un enlace — no hay endpoint de descarga ni presigned URL. En pantalla:
texto renderizado con botón **copiar** (uso más frecuente en la práctica) y botón **descargar
`.md`/`.txt`**. Opcional si sobra tiempo: generar `.docx` con una librería JS del lado del cliente.

## Tests

No aplica la restricción de "solo funciones puras" del backend de la misma forma, pero mantener el
mismo espíritu de alcance: priorizar cobertura de los flujos críticos de la demo (onboarding,
escaneo, "Presentarse") sobre una suite exhaustiva de componentes.