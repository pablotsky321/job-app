# Implementation Plan: Frontend SPA

## Overview

Convierte `design.md` (fuente de verdad técnica, ya cerrado) en una secuencia de tareas de implementación
para `job-search-assistant` frontend: React + Vite + TypeScript, Tailwind, TanStack Query, shadcn/ui
re-tematizado, Framer Motion puntual. `requirements.md` es la fuente de los criterios de aceptación
verificables por tarea. Ninguna decisión de diseño (dependencias externas, Property 6, `classifyScanResult`,
`retry: false` vs `refetchInterval`, estados de `UsuarioVacante`) se reabre aquí — las tareas implementan
lo ya decidido.

**Estado real del repo verificado antes de escribir este plan**: `frontend/` no tiene todavía ni
`package.json` con contenido, ni `src/`, ni configuración de Vite/Tailwind/Vitest — se arranca desde cero.
`frontend/openapi/openapi.json` (vigente hoy) expone únicamente `/health`, `/me/profile/parse`,
`GET /PUT /me/profile`, `POST /me/profile/roles/suggest`, `PUT /me/profile/roles`, `GET /POST /companies`,
`GET /me/companies`, `PUT /me/companies/{companyId}`. **Ningún path de `/scans`, `/me/vacancies*`, ni
`POST /me/companies/{companyId}`** existe todavía en ese `openapi.json` — esto confirma en código, no solo
en el texto de requirements.md, que las tareas de Onboarding paso 3/4, Listado, Detalle, Postulaciones, y
parte de Fuentes dependen de contrato que el backend aún no expone tipado. Cada tarea afectada lo marca
explícitamente abajo con `<!-- TODO: Dependencia externa -->`.

**Orden de capas** (cada grupo depende del anterior, según `design.md` §Folder Structure y regla de
dependencia `lib/` → nada; `api/`+`auth/` → `lib/`; `components/` → `api/`+`lib/`; `screens/` → todo):

`Setup` → `Auth_Module` → `API_Client` → `TanStack Query (config global)` → `lib/` (funciones puras +
Vitest/fast-check) → `components/ui` (shadcn re-tematizado + componentes compartidos) → `screens/` en
orden de flujo: Onboarding → Listado → Detalle → Postulaciones → Fuentes.

**Regla de capas — aplicada de forma consistente en este plan**: `src/lib/types.ts` (tipos de estado
derivado de UI: `ScanJobStatus`, `VacancyListItem`, `BadgeColor`, `ScanOutcome`, `StoredTokens`, per
`design.md` §Data Models) se crea en la tarea **5.1**, dentro de la sección `lib/`, y depende únicamente
del setup del proyecto (1.1) — nunca de `api/`. `src/api/types.ts` (tipos generados desde `openapi.json`)
se crea por separado en la tarea 3.1, también dependiendo solo de 1.1. Ninguna tarea de `lib/` importa de
`api/`, `auth/`, ni `components/`; las tareas de `api/`/`components/`/`screens/` que necesiten los tipos
de `lib/types.ts` (p. ej. 7.7, 8.1, 8.2) lo declaran como dependencia explícita hacia `lib/`, nunca al
revés.

**Sobre los "Criterios de completitud" redactados como "simular X"**: Requirement 13.6 prohíbe tests de
componentes React, Playwright, y Cypress — eso se respeta en todo este plan (ninguna tarea instala RTL ni
un framework e2e). Los criterios de completitud de las tareas de `screens/`/`mutations/` que dicen
"simular una respuesta mock de 200", "simular fallo de `navigator.clipboard.writeText`", etc., se
verifican **manualmente durante la propia tarea**, con las devtools del navegador y, cuando haga falta,
un mock puntual de `fetch` en la consola o un backend de desarrollo que devuelve la respuesta deseada —
nunca instalando infraestructura de test de componentes para automatizarlos. La tarea 12.1 (checkpoint
final) es la pasada consolidada de todos los Acceptance Criteria al final, no la primera verificación de
ninguno de ellos.

**Nota de calibración honesta**: sumando el tiempo estimado de las 47 tareas de abajo se llega a ~153
horas (~19 días de 8h, o ~10 días si se trabaja en pareja o con alto throughput de pairing con Kiro). El
contexto de "10 días efectivos" es información de calibración de intención, no una restricción que se
fuerza artificialmente recortando estimados por debajo de lo realista — 8 pantallas + auth completo +
capa de API tipada + sistema de diseño con 6+ componentes shadcn re-tematizados + 5 funciones puras con
PBT es, de forma honesta, más volumen que 10 días de una sola persona. Si el plazo es una restricción
dura, la palanca de corte más segura es priorizar `★ momentos firma` (Onboarding paso 1, Detalle de
vacante) y Listado/Fuentes básicos, y tratar Postulaciones/entries como el primer candidato a recortar si
el tiempo se agota — nunca cortar Auth_Module o API_Client, son transversales a todo lo demás.

**Fuera de esta spec** (heredado, no representado por ninguna tarea): provisioning de infraestructura
(S3, CloudFront, Cognito), tests de componentes React, Playwright, Cypress, React Testing Library,
generación de `.docx`, y cualquier re-decisión de las "Dependencias externas pendientes" de
requirements.md.

## Tasks

- [x] 1. Setup del proyecto
  - 1.1 Scaffold Vite + React + TypeScript, dependencias y scripts
    - Crear el proyecto con `npm create vite@latest frontend -- --template react-ts` reutilizando el
      `frontend/` existente (ya tiene `openapi/`, `package.json` y `vite.config.ts` vacíos)
    - Instalar dependencias de runtime: `react-router-dom`, `@tanstack/react-query`, `react-hook-form`,
      `zod`, `@hookform/resolvers`, `lucide-react`, `framer-motion`, `@fontsource/inter` — todas con
      versión exacta fijada (sin rango abierto `^`/`~`), consistente con la regla de dependencias
      pinneadas
    - Instalar devDependencies: `tailwindcss`, `postcss`, `autoprefixer`, `openapi-typescript`, `vitest`,
      `fast-check`, `@vitejs/plugin-react`
    - Configurar `tsconfig.json` (paths si aplica), y agregar a `package.json` los scripts `dev`,
      `build`, `preview`, `test` (`vitest run`), `generate:types`, `predev`, `prebuild` (estos dos últimos
      ejecutan `generate:types` per diseño §API_Client, aunque el script en sí se implementa en la tarea
      3.1)
    - **Criterios de completitud**: `npm install` corre sin error; `npm run build` produce un bundle
      vacío sin fallar; estructura de carpetas coincide con `design.md` §Folder Structure
      (`src/api`, `src/auth`, `src/lib`, `src/components`, `src/screens`, `src/styles`)
    - **Dependencias previas**: ninguna
    - **Tiempo estimado**: 3h
    - _Requirements: (transversal, setup de infraestructura de desarrollo, no mapea a un AC específico)_

  - 1.2 Configurar Tailwind con los tokens exactos y Vitest + fast-check
    - Crear `tailwind.config.js` copiando literal la configuración de `contexto-tecnico-frontend.md`
      §4.2 (colores `primary`/`gray`/`success`/`error`/`warning`/`cancel`, `fontFamily.sans: Inter`) —
      sin reinterpretar ningún valor hexadecimal
    - Crear `postcss.config.js`, y `src/index.css` con las directivas `@tailwind base/components/utilities`
    - Crear `vitest.config.ts` apuntando a `src/vitest.setup.ts` (vacío por ahora, se usa si se necesita
      luego) y configurando el entorno `node` (no `jsdom`, ya que `lib/` no toca el DOM — Requirement 13.6)
    - Agregar `fast-check` como import verificable con un test trivial de humo
      (`fc.assert(fc.property(fc.integer(), () => true))`) para confirmar que la integración Vitest +
      fast-check funciona antes de escribir las funciones reales
    - **Criterios de completitud**: `npm run test` ejecuta el test de humo y pasa; los tokens de color en
      `tailwind.config.js` son un copy-paste verificable contra `contexto-tecnico-frontend.md` §4.2 (mismo
      valor hex por token)
    - **Dependencias previas**: 1.1
    - **Tiempo estimado**: 2h
    - _Requirements: 3.1, 3.2, 13.6_

  - 1.3 App shell: bootstrap, rutas stub, e importación de fuente
    - Crear `src/main.tsx`: importa `@fontsource/inter` (pesos 400/500/600/700), monta
      `QueryClientProvider` (con un `QueryClient` por ahora default) y `<App />`
    - Crear `src/App.tsx` con `react-router-dom`: rutas `/callback`, `/onboarding/:step`, `/vacancies`,
      `/vacancies/:companyId/:vacancyId`, `/applications`, `/applications/:companyId/:vacancyId`,
      `/sources`, y `/*` — cada una renderizando un componente placeholder (`<div>TODO: X</div>`) que se
      reemplaza en las tareas de `screens/` más adelante
    - **Criterios de completitud**: `npm run dev` levanta la app, navegar a cada ruta stub no lanza error
      de consola, la tipografía Inter se aplica visualmente (verificable inspeccionando `font-family`
      computado en devtools)
    - **Dependencias previas**: 1.2
    - **Tiempo estimado**: 2h
    - _Requirements: 3.2 (Inter como única familia tipográfica)_

- [x] 2. Auth_Module (Requirement 1)
  - 2.1 Token_Store: `src/auth/tokenStore.ts`
    - Implementar `tokenStore` exactamente como en `design.md` §1 (Auth_Module): `getAccessToken`,
      `getIdToken`, `setTokens`, `clear` — wrapper delgado sobre `sessionStorage`, nunca `localStorage`
      ni cookies
    - **Criterios de completitud**: revisión manual confirma que ningún método usa `localStorage` ni
      `document.cookie`; `clear()` remueve las 4 claves (`access_token`, `id_token`,
      `pkce_code_verifier`, `post_login_redirect`)
    - **Dependencias previas**: 1.1
    - **Tiempo estimado**: 1.5h
    - _Requirements: 1.4, 1.5, 1.6_

  - 2.2 PKCE: `src/auth/pkce.ts` + test Vitest
    - Implementar `generateCodeVerifier()` (aleatorio criptográfico vía `crypto.getRandomValues`,
      base64url, longitud dentro de 43-128 caracteres per RFC 7636) y `generateCodeChallenge(verifier)`
      (SHA-256 vía `crypto.subtle.digest` + base64url)
    - Escribir el test unitario de ejemplo descrito en `design.md` §Testing Strategy: longitud del
      `code_verifier` dentro de 43-128, y dos invocaciones sucesivas producen verifiers distintos (no es
      PBT — es un ejemplo puntual sobre aleatoriedad, tal como el design lo especifica explícitamente)
    - **Criterios de completitud**: `npm run test -- pkce` pasa; `generateCodeChallenge` para un
      `verifier` fijo es determinista (mismo input → mismo output) en dos ejecuciones del test
    - **Dependencias previas**: 2.1
    - **Tiempo estimado**: 3h
    - _Requirements: 1.3_

  - 2.3 AuthContext: `src/auth/AuthContext.tsx`
    - Implementar `AuthProvider` con `login()` (guarda ruta actual + `code_verifier` en
      `sessionStorage`, redirige a Cognito Hosted UI con `code_challenge` y `response_type=code`),
      `handleCallback(code)` (intercambia código por tokens vía `fetch` al endpoint de token de Cognito,
      sin client secret; en éxito llama a `tokenStore.setTokens` y navega a la ruta guardada o `/`; en
      error NO persiste tokens parciales), y `logout()` (limpia Token_Store y redirige a Hosted UI)
    - Exponer `isAuthenticated` derivado de `tokenStore.getAccessToken() !== null`
    - Registrar el handler de 401 con `registerUnauthorizedHandler(() => logout())` al montar el
      Provider (evita el import circular con `api/client.ts`, tal como especifica `design.md`)
    - **Criterios de completitud**: revisión manual confirma que ningún camino de error de
      `handleCallback` deja un token parcial en `sessionStorage`; `login()` nunca renderiza un formulario
      propio de usuario/contraseña
    - **Dependencias previas**: 2.2
    - **Tiempo estimado**: 5h
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.9, 1.12, 1.13_

  - 2.4 AuthGuard + CallbackView + wiring en App.tsx
    - `src/auth/AuthGuard.tsx`: envuelve toda ruta salvo `/callback`; si `isAuthenticated` es falso,
      invoca `login()` inmediatamente y no renderiza children
    - `src/screens/auth/CallbackView.tsx`: lee `code` o `error` de la URL; si hay `code`, invoca
      `handleCallback(code)` y muestra un estado de carga; si hay `error` (usuario canceló login),
      muestra el mensaje "el login no se completó" con botón para reintentar `login()`
    - Envolver las rutas protegidas de `App.tsx` (todas salvo `/callback`) con `<AuthGuard>`
    - **Criterios de completitud**: navegar a cualquier ruta protegida sin sesión redirige a Cognito
      Hosted UI (verificable simulando `tokenStore` vacío); `/callback?error=access_denied` muestra el
      mensaje de cancelación con botón de reintento en vez de intentar el intercambio de código
    - **Dependencias previas**: 2.3
    - **Tiempo estimado**: 4h
    - _Requirements: 1.1, 1.2, 1.7, 1.11, 1.13_

- [x] 3. API_Client (Requirement 2)
  - 3.1 Generación de tipos desde openapi.json
    - Implementar el script `generate:types` en `package.json`:
      `openapi-typescript openapi/openapi.json -o src/api/generated/schema.d.ts`, y confirmar que
      `predev`/`prebuild` lo invocan (ya declarados en 1.1)
    - Crear `src/api/types.ts` re-exportando tipos de dominio con nombres claros
      (`PerfilEstructurado`, etc.) derivados de `components["schemas"]` del `schema.d.ts` generado, usando
      `Pick`/`Omit`/`Partial` cuando se necesite una variante — nunca redefiniendo un campo a mano
    - **Nota de capas**: esta tarea NO crea `src/lib/types.ts` (eso vive en la tarea 5.1, dentro de la
      sección `lib/`, y no depende de esta tarea) — `src/api/types.ts` solo contiene tipos derivados del
      esquema generado; los tipos de estado derivado de UI (`VacancyListItem`, etc.) son responsabilidad
      exclusiva de `lib/`, per la regla de capas del Overview
    - **Criterios de completitud**: `npm run generate:types` produce `schema.d.ts` sin error contra el
      `openapi.json` actual; `npm run build` tipa correctamente sin `any` implícito en `types.ts`
    - **Dependencias previas**: 1.1
    - **Tiempo estimado**: 2h
    - _Requirements: 2.1, 2.2, 2.5_

  - 3.2 `client.ts`: fetch wrapper único
    - Implementar `apiClient.get/post/put` y `ApiError` exactamente como en `design.md` §API_Client:
      adjunta `Authorization: Bearer <token>` leído de `tokenStore`, maneja `Content-Type: text/plain`
      (usado por `POST .../cv`) devolviendo texto crudo en vez de intentar `.json()`, y parsea `.detail`
      del body de error cuando existe
    - Confirmar que **ningún otro módulo** de la SPA construye URLs de la API o llama a `fetch`
      directamente — esto se revisa también al final de cada tarea de `screens/` más adelante, pero se
      establece aquí como regla de arquitectura
    - **Criterios de completitud**: llamada de ejemplo a `apiClient.get<HealthResponse>("/health")`
      contra el backend real (o un mock de `fetch`) devuelve `{status: "ok"}` tipado; una respuesta 404
      simulada lanza `ApiError` con `status === 404`
    - **Dependencias previas**: 3.1
    - **Tiempo estimado**: 4h
    - _Requirements: 2.3, 2.4_

  - 3.3 Interceptor de 401 ↔ Auth_Module
    - Implementar `registerUnauthorizedHandler` en `client.ts` (variable de módulo `onUnauthorized`) y
      confirmar que `AuthProvider` (tarea 2.3) ya lo registra al montar
    - En `request<T>`, al recibir HTTP 401: invocar `onUnauthorized?.()` y lanzar `ApiError(401, ...)`
      antes de intentar parsear el body
    - **Criterios de completitud**: simular una respuesta 401 de `fetch` (mock) y confirmar que
      `logout()` de `AuthContext` se invoca exactamente una vez, y que ningún hook individual de
      `queries/`/`mutations/` necesita manejar el 401 por su cuenta
    - **Dependencias previas**: 3.2, 2.3
    - **Tiempo estimado**: 1.5h
    - _Requirements: 1.9, 2.7_

- [x] 4. TanStack Query — configuración global (Requirement 2 criterio 6)
  - 4.1 QueryClient config + convención de queryKeys
    - Actualizar `src/main.tsx` para usar un `QueryClient` configurado explícitamente (no el default
      implícito de 1.3): `staleTime: 0` por defecto (cada pantalla sobreescribe según necesidad, per
      `design.md` §3), `retry` por defecto razonable para queries normales (no aplica a
      `Scan_Polling_Hook`, que fija su propio `retry: false` en la tarea 7.7)
    - Crear `src/api/queryKeys.ts` documentando la convención `["<recurso>", ...params]` con funciones
      helper tipadas (`vacanciesKey(estado)`, `vacancyKey(companyId, vacancyId)`, `scanKey(jobId)`,
      `entriesKey(companyId, vacancyId)`, `companiesKey()`, `subscriptionsKey()`, `profileKey()`) para que
      cada hook de `queries/`/`mutations/` las reutilice en vez de escribir arrays de query key a mano
    - Confirmar que ninguna dependencia de estado global (Redux/Zustand/Jotai/Recoil) se instaló en la
      tarea 1.1 — es una verificación, no código nuevo
    - **Criterios de completitud**: `package.json` no contiene ninguna de esas librerías;
      `queryKeys.ts` exporta al menos las 6 funciones listadas con tipos de parámetro explícitos
    - **Dependencias previas**: 3.3
    - **Tiempo estimado**: 2h
    - _Requirements: 2.6_

- [x] 5. Funciones puras en `lib/` con tests Vitest + fast-check (Requirement 13)
  - [x] 5.1 Tipos locales de estado derivado de UI: `src/lib/types.ts`
    - Crear `src/lib/types.ts` con los tipos que `design.md` §Data Models asigna explícitamente a `lib/`
      (no a `api/`): `ScanJobStatus`, `VacancyListItem`, `BadgeColor`, `ScanOutcome`, `StoredTokens` —
      exactamente como en `design.md`
    - Documentar `VacancyListItem` con el comentario `// TODO(dependencia-externa-pendiente-2/4): eliminar
      cuando openapi.json exponga el esquema real de /me/vacancies` — confirmado por grep que ese
      endpoint no tiene esquema todavía en el `openapi.json` vigente
    - **Regla de capas**: este archivo no importa nada de `src/api/`, `src/auth/`, ni `src/components/` —
      depende únicamente de TypeScript puro, consistente con la regla del Overview de que `lib/` no
      depende de nada del resto de la SPA
    - **Criterios de completitud**: `tsc --noEmit` tipa el archivo sin error; grep sobre
      `src/lib/types.ts` confirma cero declaraciones `import` hacia `src/api/`, `src/auth/`, o
      `src/components/`
    - **Dependencias previas**: 1.1
    - **Tiempo estimado**: 1.5h
    - _Requirements: (soporte transversal de tipos para 13.1-13.5, sin AC propio)_

  - [x] 5.2 `scoreColorMapper.ts` + test (Property 1)
    - Implementar `scoreColorMapper(veredicto): BadgeColor` (tipo `BadgeColor` de la tarea 5.1) como
      tabla determinista total: `excelente→success`, `buen_encaje→primary`, `parcial→warning`,
      `bajo→gray`
    - Escribir `src/lib/__tests__/scoreColorMapper.test.ts`: un test de property-based testing
      (`fc.constantFrom("excelente","buen_encaje","parcial","bajo")`, `numRuns: 100`) con el comentario
      de tag `// Feature: frontend-spa, Property 1: ...` inmediatamente antes del `it(...)`, más 1 caso de
      ejemplo feliz documentando la tabla completa como comentario legible
    - **Criterios de completitud**: `npm run test -- scoreColorMapper` pasa; el archivo no importa nada
      de `api/`, `auth/`, ni `components/`
    - **Dependencias previas**: 5.1
    - **Tiempo estimado**: 1.5h
    - _Requirements: 8.4, 13.1_

  - [x] 5.3 `scanPollingExit.ts` + test (Property 2)
    - Implementar `isScanTerminal(status: string): boolean` — verdadero para `DONE`/`PARCIAL`/`FAILED`,
      falso para `RUNNING` o cualquier otro string no reconocido; la firma toma `string` (no
      `ScanJobStatus`) deliberadamente, porque Property 2 exige fuzzing con valores arbitrarios no
      reconocidos, no solo el enum válido — por eso esta tarea no depende de 5.1
    - Escribir el test PBT correspondiente (`fc.oneof(fc.constantFrom("DONE","PARCIAL","FAILED"),
      fc.constantFrom("RUNNING"), fc.string())` con aserciones separadas por rama, tag `Property 2`)
    - **Criterios de completitud**: `npm run test -- scanPollingExit` pasa, incluyendo el caso de un
      string arbitrario no reconocido (fuzz vía `fc.string()`) siempre clasificado como "continuar"
    - **Dependencias previas**: 1.2
    - **Tiempo estimado**: 1.5h
    - _Requirements: 7.4, 13.2_

  - [x] 5.4 `rescoringFreeze.ts` — `hasStaleItems` + test (Property 3)
    - Implementar `hasStaleItems(items: VacancyListItem[]): boolean` (usa el tipo `VacancyListItem` de
      la tarea 5.1)
    - Escribir el test PBT (`fc.array(fc.record({ companyId: fc.string(), vacancyId: fc.string(),
      staleFlag: fc.boolean() }))`, tag `Property 3`), incluyendo el caso de ejemplo explícito de lista
      vacía → `false` (documentado también como unit test de ejemplo per `design.md`)
    - **Criterios de completitud**: `npm run test -- rescoringFreeze` pasa el bloque de `hasStaleItems`,
      incluyendo el caso `[]` → `false`
    - **Dependencias previas**: 5.1
    - **Tiempo estimado**: 2h
    - _Requirements: 8.6, 13.3_

  - [x] 5.5 `rescoringFreeze.ts` — `reconcileFrozenOrder` + test (Property 4)
    - Implementar `reconcileFrozenOrder(frozenOrder, latest): VacancyListItem[]` exactamente como en
      `design.md` §5: preserva el orden relativo de elementos presentes en ambas listas (con datos
      frescos de `latest`), e inserta al final los elementos nuevos de `latest` en su orden relativo
      original
    - Escribir el test PBT (listas generadas con `fc.array` + permutación/inserción controlada de claves
      nuevas vs. persistentes, tag `Property 4`)
    - **Criterios de completitud**: `npm run test -- rescoringFreeze` pasa el bloque de
      `reconcileFrozenOrder`, cubriendo: membresía sin cambios, elementos removidos, elementos nuevos
      agregados al final, y datos actualizados (score/staleFlag) tomados de `latest` no de `frozenOrder`
    - **Dependencias previas**: 5.4
    - **Tiempo estimado**: 3h
    - _Requirements: 8.6, 13.3_

  - [x] 5.6 `cvAtsBlobBuilder.ts` + test (Properties 5 y 6)
    - Implementar `buildCvAtsFileName(companyId, vacancyId): string` y `buildCvAtsBlob(cvAtsTexto): Blob`
      exactamente como en `design.md` §6 (no usa ningún tipo de la tarea 5.1 — trabaja solo con `string`)
    - Escribir dos tests PBT en `cvAtsBlobBuilder.test.ts`: (a) round-trip — `fc.string()` /
      `fc.unicodeString()` para `companyId`/`vacancyId`/`cvAtsTexto`, verificando que el nombre contiene
      ambos identificadores codificados, termina en `.txt`, y el contenido del `Blob` (leído vía
      `.text()`) es idéntico al `cvAtsTexto` de entrada (tag `Property 5`); (b) no-colisión — dos pares
      `(companyId, vacancyId)` generados con la restricción de que difieren en al menos un campo producen
      nombres de archivo distintos (tag `Property 6`)
    - Incluir el caso de ejemplo con texto multi-párrafo y saltos de línea real per `design.md`
      §Unit tests de ejemplo
    - **Criterios de completitud**: `npm run test -- cvAtsBlobBuilder` pasa ambas properties; leer el
      `Blob` con `await blob.text()` en el test confirma igualdad exacta de string, incluyendo Unicode
    - **Dependencias previas**: 1.2
    - **Tiempo estimado**: 3h
    - _Requirements: 11.5, 13.4_

  - [x] 5.7 `scanResultClassifier.ts` + test (Property 7)
    - Implementar `classifyScanResult(status, newVacancyCount): ScanOutcome` (tipo `ScanOutcome` de la
      tarea 5.1) exactamente como en `design.md` §7, incluyendo la nota de diseño sobre `PARCIAL` (la
      función es una simplificación de dos ramas; `SourcesView` en la tarea 11.3 consulta
      `status === "PARCIAL"` explícitamente antes de usar esta función para decidir el componente visual)
    - Escribir el test PBT (`fc.integer({min:0,max:999})` para conteos, `fc.constantFrom("DONE","FAILED")`
      para status, tag `Property 7`), verificando las dos fronteras exigidas por Requirement 13.5:
      `DONE` + count 0 → `sin_novedades` para cualquier conteo de empresas revisadas, y `FAILED` →
      `fallido` para cualquier `count`
    - **Criterios de completitud**: `npm run test -- scanResultClassifier` pasa
    - **Dependencias previas**: 5.1
    - **Tiempo estimado**: 2h
    - _Requirements: 12.5, 12.6, 13.5_

  - [x] 5.8 `cn.ts` — utilidad de merge de clases Tailwind
    - Implementar `cn(...inputs: ClassValue[]): string` usando `clsx` (condicionales) + `tailwind-merge`
      (resolución de conflictos Tailwind), patrón estándar de shadcn/ui
    - **Criterios de completitud**: el archivo existe y se importa correctamente desde componentes UI
    - **Dependencias previas**: 1.2
    - **Tiempo estimado**: 0.5h
    - _Requirements: (transversal, necesaria para componentes UI, sin AC propio)_

- [x] 6. Componentes UI compartidos (Requirement 3)
  - 6.1 shadcn: `Select`, `Tabs`, `Progress` — copiar y re-tematizar
    - `npx shadcn add select tabs progress`; en el mismo commit, sustituir toda variable `zinc`/`slate`
      por los tokens `primary`/`gray`/semánticos de §4.2 antes de usarlos en cualquier ruta real
    - **Criterios de completitud**: inspección visual/grep de los archivos copiados en
      `src/components/ui/` confirma cero referencias a `zinc-*`/`slate-*` en clases Tailwind
    - **Dependencias previas**: 1.2
    - **Tiempo estimado**: 3h
    - _Requirements: 3.4_

  - 6.2 shadcn: `Command`/`Combobox` — copiar y re-tematizar
    - `npx shadcn add command`; re-tematizar en el mismo commit (usado en Onboarding paso 3 y Fuentes)
    - **Criterios de completitud**: mismo criterio de grep de 6.1 aplicado a `command.tsx`
    - **Dependencias previas**: 1.2
    - **Tiempo estimado**: 2h
    - _Requirements: 3.4, 6.1, 12.9_

  - 6.3 shadcn: `Toast`, `Dialog`/`Sheet` — copiar y re-tematizar
    - `npx shadcn add toast dialog sheet`; re-tematizar en el mismo commit
    - **Criterios de completitud**: mismo criterio de grep aplicado a los 3 archivos copiados
    - **Dependencias previas**: 1.2
    - **Tiempo estimado**: 3h
    - _Requirements: 3.4_

  - 6.4 `ScoreBadge` + `StaleBadge`
    - `src/components/ScoreBadge.tsx`: usa `scoreColorMapper` (tarea 5.2) para renderizar un badge de
      color según `veredicto`
    - `src/components/StaleBadge.tsx`: badge "actualizando…" — usado sobre un score existente o solo
      (cuando `score` es `null`), per Requirement 8.5
    - **Criterios de completitud**: revisión visual manual confirma que `ScoreBadge` nunca pone texto
      pequeño blanco sobre `primary-500` (Requirement 3.3)
    - **Dependencias previas**: 5.2, 1.2
    - **Tiempo estimado**: 2h
    - _Requirements: 8.4, 8.5, 3.3_

  - 6.5 `VacancyCard` compartida
    - `src/components/VacancyCard.tsx`: tarjeta de una columna con el orden exacto de Requirement 8.2
      (fecha + check si aplica, `ScoreBadge`, cargo, empresa, lugar/modalidad); borde 1px
      `primary-100`/`gray-200`, sin `shadow-*` sin re-tematizar; prop opcional para ocultar el check de
      "ya aplicada" (reutilizada sin ese check en Postulaciones, tarea 10.1)
    - Usa `PlainText` (tarea 6.6) para renderizar cualquier campo de texto proveniente del backend
    - **Criterios de completitud**: revisión visual confirma layout de una columna (no grid de 3
      columnas); grep confirma ausencia de `shadow-md`/`shadow-lg` sin comentario de re-tematización
    - **Dependencias previas**: 6.4, 6.6
    - **Tiempo estimado**: 3h
    - _Requirements: 8.2, 8.3, 10.1_

  - 6.6 `EmptyState`, `ErrorState`, `PlainText`
    - `src/components/EmptyState.tsx` y `ErrorState.tsx`: visualmente distintos entre sí (Requirement
      8.11), cada uno con mensaje configurable y `ErrorState` con botón de reintento opcional
    - `src/components/PlainText.tsx`: wrapper que renderiza `children` como texto plano de React —
      **nunca** usa `dangerouslySetInnerHTML`; existe para que cada pantalla que muestre descripción de
      vacante, `resumen` de score, o contenido de `Entrada` lo use consistentemente en vez de repetir la
      garantía en cada componente
    - **Criterios de completitud**: grep sobre `src/` confirma cero ocurrencias de
      `dangerouslySetInnerHTML` en todo el proyecto (se re-verifica en el checkpoint final, tarea 12.1)
    - **Dependencias previas**: 1.2
    - **Tiempo estimado**: 2h
    - _Requirements: 4.9, 8.10, 9.4, 10.13_

- [x] 7. Onboarding (Requirements 4, 5, 6, 7)
  - 7.1 `OnboardingWizard` — contenedor y stepper
    - `src/screens/onboarding/OnboardingWizard.tsx`: maneja el paso actual vía el param de ruta
      `/onboarding/:step` (1-4), renderiza el stepper visual y delega a `Step1..Step4` (implementados en
      7.2-7.8); reemplaza el placeholder de `/onboarding/:step` en `App.tsx`
    - **Criterios de completitud**: navegar manualmente a `/onboarding/1`..`/onboarding/4` renderiza el
      stepper con el paso correcto resaltado
    - **Dependencias previas**: 1.3, 2.4
    - **Tiempo estimado**: 3h
    - _Requirements: (contenedor transversal a Req 4-7)_

  - 7.2 Step1 — vista dividida + revelación secuencial con Framer Motion
    - `src/screens/onboarding/Step1ProfileParse.tsx`: campo de texto para pegar CV; al confirmar, invoca
      `POST /me/profile/parse` (mutation), muestra estado de carga con vista dividida (texto crudo a la
      izquierda vía `PlainText`, derecha vacía); al recibir 200, revela cada sección del
      `PerfilEstructurado` secuencialmente con Framer Motion (omite secciones vacías, respeta el orden de
      la respuesta)
    - Maneja HTTP 413 (mensaje de tamaño excedido + vuelta a panel único) y HTTP 400/502 (mensaje
      distinto + botón reintentar) como estados separados de la mutation
    - **Criterios de completitud**: con una respuesta mock de 200, las secciones aparecen en el orden de
      la respuesta con una transición visible; con un mock 413, la UI vuelve al panel de un solo campo sin
      perder el texto ya pegado
    - **Dependencias previas**: 7.1, 3.3, 6.6
    - **Tiempo estimado**: 5h
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.9_

  - 7.3 Step1 — formulario editable RHF + Zod + guardado
    - Extender `Step1ProfileParse.tsx` (o extraer `ProfileEditForm.tsx`): tras la revelación, habilita
      edición de cada campo del `PerfilEstructurado` con React Hook Form, validado con un esquema Zod
      equivalente; deshabilita el botón de confirmación mientras haya errores de validación sin resolver
    - Al confirmar, invoca `PUT /me/profile` (mutation) y avanza a `/onboarding/2` únicamente tras 200;
      en error, conserva el perfil editado sin descartarlo, muestra mensaje y botón de reintento sin
      avanzar
    - **Criterios de completitud**: introducir un valor inválido en el esquema Zod deshabilita el botón
      de confirmación; simular un error de `PUT /me/profile` conserva los valores editados en el
      formulario (verificable no reseteando el form state)
    - **Dependencias previas**: 7.2
    - **Tiempo estimado**: 5h
    - _Requirements: 4.5, 4.8, 4.10_

  - 7.4 Step2 — sugerencia de cargos + polling de `resumenGenerating`
    <!-- TODO: Dependencia externa — punto 3 de "Dependencias externas pendientes": ningún spec de
         backend define qué dispara `resumenParaMatching`; esta tarea asume que `GET /me/profile` expone
         `resumenGenerating` tal como documenta requirements.md, y que el proceso corre en <30s. Si el
         worker no existe en el momento de integrar, este paso queda bloqueado en producción hasta que
         se implemente en el backend. -->
    - `src/screens/onboarding/Step2Roles.tsx`: al entrar, invoca `POST /me/profile/roles/suggest`; si
      responde HTTP 424, inicia polling de `GET /me/profile` cada 3s verificando `resumenGenerating`,
      con tope de 30s (tras el cual detiene el polling y muestra error con reintento manual); al
      `resumenGenerating=false` reintenta el suggest inmediatamente
    - **Criterios de completitud**: simular una respuesta 424 seguida de `resumenGenerating: true` en
      dos polls y `false` en el tercero dispara un reintento automático de `roles/suggest`; simular
      `resumenGenerating` siempre `true` durante 30s detiene el polling y muestra el botón de reintento
    - **Dependencias previas**: 7.3
    - **Tiempo estimado**: 4h
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.12_

  - 7.5 Step2 — selección de cargos y confirmación
    - Extender `Step2Roles.tsx`: renderiza `suggestions` como opciones seleccionables, permite agregar
      cargos propios (trim, máx 50 caracteres, bloquea agregar si el combinado llega a 10), y al
      confirmar invoca `PUT /me/profile/roles` con `cargosActivos` (lista vacía permitida sin bloquear
      avance); avanza a `/onboarding/3` solo tras HTTP 200; en HTTP 400 muestra errores de validación por
      campo sin avanzar
    - **Criterios de completitud**: intentar agregar un cargo vacío (tras trim) o >50 caracteres no lo
      agrega y muestra validación; con 10 cargos seleccionados, el control de "agregar" queda
      deshabilitado hasta deseleccionar uno
    - **Dependencias previas**: 7.4
    - **Tiempo estimado**: 4h
    - _Requirements: 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.13_

  - 7.6 Step3 — catálogo de empresas y selección/deselección
    <!-- TODO: Dependencia externa — punto 1 de "Dependencias externas pendientes": POST
         /me/companies/{companyId} (alta idempotente de Suscripcion) no existe en `openapi.json` vigente
         (confirmado por grep) ni en `backend-core` ya implementado, que solo expone
         PUT /me/companies/{companyId} sobre una Suscripcion YA existente. Esta tarea implementa el
         flujo asumiendo el contrato idempotente ya decidido en requirements.md; queda bloqueada en
         producción hasta que el backend lo exponga. -->
    - `src/screens/onboarding/Step3Companies.tsx`: al entrar, invoca `GET /companies` (ya disponible
      hoy) y lo muestra con el `Command`/`Combobox` de la tarea 6.2; selección invoca
      `POST /me/companies/{companyId}` (mutation, dependencia externa arriba), deselección invoca
      `PUT /me/companies/{companyId}` con `activa=false` (endpoint ya disponible)
    - Errores puntuales por empresa no afectan las demás; bloquea avance a `/onboarding/4` hasta que
      `GET /companies` haya cargado exitosamente al menos una vez y al menos una empresa esté confirmada
      con HTTP 200/201
    - **Criterios de completitud**: simular error de `GET /companies` bloquea el avance y muestra botón
      de reintento; simular error de selección en una empresa específica no descarta las demás ya
      confirmadas
    - **Dependencias previas**: 7.5, 6.2
    - **Tiempo estimado**: 5h
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - 7.7 `useScanPolling` — Scan_Polling_Hook genérico y reutilizable
    <!-- TODO: Dependencia externa — GET /scans/{jobId} no existe todavía en `openapi.json` vigente
         (confirmado por grep) ni, según el tasks.md de backend-scan-y-scoring, está necesariamente
         desplegado. Se implementa contra el contrato documentado en requirements.md/design.md
         (status RUNNING/DONE/PARCIAL/FAILED + conteos agregados) usando el tipo local `ScanJobStatus`
         de src/lib/types.ts (tarea 5.1), marcado con el mismo TODO, hasta que el esquema real aparezca
         en openapi.json. -->
    - `src/api/queries/useScanPolling.ts`: implementar exactamente como `design.md` §4 — `refetchInterval`
      que consulta cada 2s, usa `isScanTerminal` (tarea 5.3) para decidir cuándo detenerse, aplica el
      límite de 600s marcando `timedOut`, y usa `retry: false` (con el comentario de diseño explicando
      por qué, ya documentado en `design.md`)
    - Escribir un test de ejemplo (no PBT, ya que depende de temporizadores/mocks de TanStack Query) que
      verifique que `isScanTerminal` efectivamente detiene el `refetchInterval` — puede vivir junto al
      test de 5.3 como caso de integración ligero, sin mockear red extensivamente
    - **Criterios de completitud**: con `status: "RUNNING"` el hook sigue refetcheando cada 2s; con
      `status: "DONE"` el siguiente `refetchInterval` devuelve `false`; forzando `Date.now()` más de 600s
      adelante, `timedOut` pasa a `true` y el polling se detiene
    - **Dependencias previas**: 5.3, 5.1, 4.1
    - **Tiempo estimado**: 3h
    - _Requirements: 7.3, 7.4, 7.5, 7.7_

  - 7.8 Step4 — escaneo con contador agregado
    <!-- TODO: Dependencia externa — depende de POST /scans y GET /scans/{jobId} (ver 7.7). -->
    - `src/screens/onboarding/Step4Scan.tsx`: al entrar, invoca `POST /scans`, guarda `jobId`, inicia
      `useScanPolling(jobId)` (tarea 7.7); muestra contador "{completadas} de {empresasTotal} empresas
      revisadas" mientras `status === RUNNING` (sin nombrar empresas individuales, per dependencia
      externa punto 2); en error de `POST /scans` no inicia el polling y ofrece reintentar
    - Al llegar a `DONE`/`PARCIAL`: resumen de finalización + botón para completar el wizard y navegar a
      `/vacancies`; en `FAILED`: mensaje visualmente distinto, mismo botón de continuar; en `timedOut`:
      estado de "tardando más de lo esperado" con opción de continuar sin esperar
    - **Criterios de completitud**: los 4 estados terminales (`DONE`, `PARCIAL`, `FAILED`, `timedOut`)
      renderizan componentes visualmente distintos y todos permiten completar el wizard
    - **Dependencias previas**: 7.7, 7.6
    - **Tiempo estimado**: 5h
    - _Requirements: 7.1, 7.2, 7.6, 7.8, 7.9, 7.10_

- [x] 8. Listado de vacantes (Requirement 8)
  - 8.1 `useVacancies` — query hook
    <!-- TODO: Dependencia externa — GET /me/vacancies no existe en `openapi.json` vigente (confirmado
         por grep). Se implementa contra el tipo local `VacancyListItem` de src/lib/types.ts (tarea 5.1)
         hasta que el backend lo exponga tipado. -->
    - `src/api/queries/useVacancies.ts`: `useQuery` parametrizado por `estado` (`activas`/`aplicadas`)
      usando `queryKeys.vacanciesKey(estado)` (tarea 4.1), tipado con `VacancyListItem[]` (tarea 5.1); sin
      `refetchInterval` fijo aquí — ese comportamiento condicional se implementa en la tarea 8.3 dentro
      de `VacancyListView`
    - **Criterios de completitud**: cambiar el parámetro `estado` produce una `queryKey` distinta
      (verificable inspeccionando el cache de TanStack Query en devtools o en un test de integración
      ligero)
    - **Dependencias previas**: 4.1, 5.1
    - **Tiempo estimado**: 3h
    - _Requirements: 8.1_

  - 8.2 `VacancyListView` — tabs, tarjetas, stale badge, congelamiento de orden
    - `src/screens/vacancies/VacancyListView.tsx`: usa el `Tabs` re-tematizado (tarea 6.1) para
      `activas`/`aplicadas`, cada pestaña invoca `useVacancies` (8.1) con su `estado`; renderiza cada
      elemento con `VacancyCard` (6.5); muestra `StaleBadge` (6.4) sobre el score cuando
      `staleFlag=true` (o solo, si `score` es `null`); muestra `EmptyState` cuando la lista está vacía
    - Mantiene `frozenOrderRef` por pestaña (dos `useRef` independientes) usando `hasStaleItems` y
      `reconcileFrozenOrder` (tareas 5.4/5.5) exactamente según el flujo de `design.md` §Rescoring Freeze
      Flow: al detectar stale sin congelamiento previo, inicializa con la respuesta actual; en
      respuestas subsecuentes con stale, reconcilia; al desaparecer el stale, descongela
    - **Criterios de completitud**: con una respuesta mock que tiene `staleFlag=true` en 2 de 5
      elementos, el orden no cambia aunque una respuesta posterior mockeada devuelva otro orden, hasta
      que ninguna respuesta tenga `staleFlag=true`; cambiar de pestaña no comparte el congelamiento entre
      `activas` y `aplicadas`
    - **Dependencias previas**: 8.1, 6.5, 6.4, 5.4, 5.5
    - **Tiempo estimado**: 6h
    - _Requirements: 8.1, 8.2, 8.3, 8.5, 8.6, 8.9, 8.10, 8.11, 8.14_

  - 8.3 `refetchInterval` acotado + botón de actualizar manual
    - Extender `VacancyListView.tsx`: mientras haya al menos un `staleFlag=true`, activa
      `refetchInterval: 5000` con tope de 24 intentos; al alcanzar el tope sin que el stale desaparezca,
      detiene el refetch automático, descongela la lógica de intentos (no el orden — el orden se
      descongela solo cuando ya no hay stale, per Requirement 8.9), y muestra un botón "actualizar" que
      dispara un único refetch inmediato sin reiniciar el ciclo automático
    - **Criterios de completitud**: simular 24 respuestas seguidas con `staleFlag=true` detiene el
      `refetchInterval` (verificable contando invocaciones del mock de `queryFn`) y muestra el botón
      manual; presionar el botón dispara exactamente un refetch adicional
    - **Dependencias previas**: 8.2
    - **Tiempo estimado**: 3h
    - _Requirements: 8.7, 8.8, 8.12, 8.13_

- [x] 9. Detalle de vacante (Requirement 9)
  - 9.1 `useVacancyDetail` — query hook con manejo de 404
    <!-- TODO: Dependencia externa — GET /me/vacancies/{companyId}/{vacancyId} no existe en
         `openapi.json` vigente (confirmado por grep). A diferencia de `useVacancies` (8.1), que
         reutiliza `VacancyListItem` de `src/lib/types.ts`, este hook declara su propio tipo ad-hoc
         localmente dentro del archivo del hook — per la regla de fallback de `design.md` §API_Client
         ("se declara el tipo de request/response localmente en el hook correspondiente") — dado que el
         detalle de una vacante no es una proyección de `VacancyListItem`; se marca con el mismo
         comentario TODO que 8.1. -->
    - `src/api/queries/useVacancyDetail.ts`: `useQuery` por `(companyId, vacancyId)`; expone
      `isNotFound` derivado de `error instanceof ApiError && error.status === 404`, distinguible del
      resto de errores (Requirement 9.13 vs 9.14)
    - **Criterios de completitud**: un mock que responde 404 produce `isNotFound === true`; un mock que
      responde 500 produce `isNotFound === false` con `isError === true`
    - **Dependencias previas**: 4.1
    - **Tiempo estimado**: 3h
    - _Requirements: 9.1, 9.13, 9.14_

  - 9.2 `VacancyDetailView` — desglose de score en dos columnas
    - `src/screens/vacancies/VacancyDetailView.tsx`: muestra descripción completa (vía `PlainText`),
      link a la publicación oficial, y el desglose del score: número grande arriba, dos columnas lado a
      lado (`coincidencias` / `faltantes`) — nunca donut chart ni barra de porcentaje; si `score` es
      `null`, muestra "el score todavía se está calculando" en vez de columnas vacías; renderiza
      `ErrorState`/estado "vacante no encontrada" según `isNotFound` (9.1)
    - **Criterios de completitud**: con `score: null` en el mock, se renderiza el mensaje de cálculo
      pendiente, no columnas vacías; con `score: 78`, el número aparece arriba y las dos columnas debajo
    - **Dependencias previas**: 9.1, 6.6
    - **Tiempo estimado**: 4h
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.13, 9.14, 9.15_

  - 9.3 Flujo "Presentarse" — revelación Framer Motion + 3 acciones
    - Extender `VacancyDetailView.tsx`: botón "Presentarse" revela (Framer Motion) el link con botón de
      copiar y las 3 acciones ("Generar hoja de vida", "Guardar preguntas", "Guardar"), sin invocar la
      API en el momento de la revelación
    - Implementar `useApplyVacancy` y `useGenerateCvAts` (mutations en `src/api/mutations/`): "Generar
      hoja de vida" invoca `.../apply` seguido de `.../cv` (si `.../apply` falla, no continúa; si
      `.../apply` OK y `.../cv` falla, Toast específico permitiendo reintentar solo `.../cv`); "Guardar
      preguntas" invoca `.../apply` y abre el formulario de entradas (implementado en 10.3, aquí solo se
      deja el hook de apertura); "Guardar" invoca únicamente `.../apply`
    - Si `Vacante.estado === "cerrada"`: deshabilita "Generar hoja de vida" con mensaje explicando el
      HTTP 409 (Requirement 9.15); si ya existe `cvAtsTexto` al montar, lo muestra de inmediato sin
      requerir repetir el flujo
    - **Criterios de completitud**: simular fallo de `.../apply` muestra Toast y no invoca `.../cv`;
      simular éxito de `.../apply` + fallo de `.../cv` muestra Toast distinto y el reintento posterior
      solo repite `.../cv`
    - **Dependencias previas**: 9.2, 6.3
    - **Tiempo estimado**: 6h
    - _Requirements: 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12_

- [x] 10. Postulaciones (Requirement 10, Requirement 11)
  - 10.1 `ApplicationsListView`
    - `src/screens/applications/ApplicationsListView.tsx`: invoca `useVacancies("aplicadas")` (tarea
      8.1) y reutiliza `VacancyCard` (6.5) con la prop que oculta el check de "ya aplicada"
    - **Criterios de completitud**: la tarjeta renderizada en esta vista es visualmente idéntica a la de
      `VacancyListView` salvo por la ausencia del check
    - **Dependencias previas**: 8.1, 6.5
    - **Tiempo estimado**: 2h
    - _Requirements: 10.1_

  - 10.2 `useEntries` + timeline vertical con numeración de ronda
    <!-- TODO: Dependencia externa — GET /me/vacancies/{companyId}/{vacancyId}/entries no existe en
         `openapi.json` vigente (mismo hueco que GET /me/vacancies, confirmado por grep). -->
    - `src/api/queries/useEntries.ts`: `useQuery` por `(companyId, vacancyId)`, orden cronológico ya
      garantizado por el backend
    - `src/screens/applications/ApplicationDetailView.tsx`: muestra, en orden, descripción de la vacante
      + link oficial, timeline vertical de entradas (marcador propio por entrada; solo las de tipo
      `nota_entrevista` muestran número de ronda = posición secuencial entre entradas de ese tipo,
      empezando en 1), y el `CV_ATS_Panel` (tarea 10.5); estado "postulación no encontrada" en HTTP 404
    - **Criterios de completitud**: con un mock de 5 entradas donde 3 son `nota_entrevista` intercaladas
      con 2 `preguntas`, las 3 `nota_entrevista` muestran "Ronda 1", "Ronda 2", "Ronda 3" en orden, y las
      `preguntas` no muestran número
    - **Dependencias previas**: 9.3, 4.1
    - **Tiempo estimado**: 4h
    - _Requirements: 10.2, 10.3, 10.4_

  - 10.3 Formulario de entrada — crear + "Continuar proceso"
    <!-- TODO: Dependencia externa — POST /me/vacancies/{companyId}/{vacancyId}/entries no existe en
         `openapi.json` vigente. -->
    - `src/api/mutations/useCreateEntry.ts`: `POST .../entries` con `tipo` y `contenido` (1-5000
      caracteres); en éxito (201) invalida `useEntries`, cierra el formulario y vacía el campo; en HTTP
      400 muestra errores sin cerrar ni descartar contenido; en HTTP 404 cierra el formulario con mensaje
      "la postulación ya no existe" sin reintento automático
    - Formulario reutilizable para "agregar entrada" y para "Continuar proceso" (pre-rellena el
      contenido con el número de ronda = cantidad de `nota_entrevista` existentes + 1)
    - Entradas son append-only: ningún control de edición/eliminación se expone
    - **Criterios de completitud**: enviar contenido vacío o >5000 caracteres deshabilita el submit;
      simular HTTP 400 conserva el contenido ingresado en el formulario abierto
    - **Dependencias previas**: 10.2
    - **Tiempo estimado**: 4h
    - _Requirements: 10.5, 10.6, 10.7, 10.8, 10.9, 10.10_

  - 10.4 Ayuda de IA para responder
    <!-- TODO: Dependencia externa — POST .../entries/{entryId}/answer no existe en `openapi.json`
         vigente. -->
    - `src/api/mutations/useAnswerEntry.ts`: sobre una entrada de tipo `preguntas`, invoca
      `.../entries/{entryId}/answer`; muestra estado de carga asociado a esa entrada específica (no a
      toda la vista); en éxito agrega la respuesta como nueva entrada en el timeline; en error detiene el
      loading de esa entrada, muestra mensaje, y no crea ninguna entrada nueva
    - **Criterios de completitud**: simular error de la mutation deja el timeline sin entradas nuevas y
      el estado de carga se apaga
    - **Dependencias previas**: 10.3
    - **Tiempo estimado**: 3h
    - _Requirements: 10.11, 10.12_

  - 10.5 `CV_ATS_Panel` — copiar y descargar (Requirement 11)
    - `src/components/CVAtsPanel.tsx`: renderiza `cvAtsTexto` en `font-mono` sin colores/iconos/tarjetas
      adicionales; botón "copiar" usa `navigator.clipboard.writeText` directo (sin llamar a la API), con
      confirmación visual en éxito y mensaje de error si la Clipboard API falla; botón "descargar" usa
      `buildCvAtsFileName` + `buildCvAtsBlob` (tarea 5.6) + `URL.createObjectURL` + `<a download>`
      efímero; si `cvAtsTexto` está vacío, muestra "aún no se ha generado" en vez de botones deshabilitados
    - **Criterios de completitud**: simular fallo de `navigator.clipboard.writeText` (mock que rechaza)
      muestra el mensaje de error sin la confirmación de éxito; descargar dos vacantes distintas produce
      dos nombres de archivo distintos (usa directamente la garantía de la Property 6, tarea 5.6)
    - **Dependencias previas**: 5.6, 9.3
    - **Tiempo estimado**: 3h
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [x] 11. Fuentes (Requirement 12)
  - 11.1 `useSubscriptions` + listado con indicador de salud
    - `src/api/queries/useSubscriptions.ts`: `GET /me/companies` (ya disponible en `openapi.json`
      vigente — sin dependencia externa)
    - `src/screens/sources/SourcesView.tsx`: cada fila muestra indicador de estado como elemento
      principal (gris si `lastScannedAt` es `null`, rojo si `consecutiveFailures >= 3`, verde en el
      resto) y `lastScannedAt` visible sin clic adicional; para `consecutiveFailures >= 3` muestra el
      mensaje "No hemos podido revisar {empresa} desde el {lastScannedAt}" con botones reintentar/desactivar
    - **Criterios de completitud**: con un mock de 3 suscripciones (una con `consecutiveFailures: 5`,
      una con `lastScannedAt: null`, una normal), los 3 indicadores de color son distintos y correctos
    - **Dependencias previas**: 4.1, 6.4
    - **Tiempo estimado**: 4h
    - _Requirements: 12.1, 12.2_

  - 11.2 Reintentar / desactivar / agregar empresa nueva
    <!-- TODO: Dependencia externa — punto 1 de "Dependencias externas pendientes": POST
         /me/companies/{companyId} (mismo hueco que en la tarea 7.6). -->
    - `useToggleSubscription` (`PUT /me/companies/{companyId}`, ya disponible) para "desactivar"
    - `useAddCompany`: flujo de agregar empresa por URL nueva — `POST /companies` (ya disponible); en
      201 sigue con `POST /me/companies/{companyId}` (dependencia externa); en HTTP 409, usa el
      `companyId` del body de error para invocar `POST /me/companies/{companyId}` igualmente, en vez de
      solo mostrar error
    - Reutiliza el `Command`/`Combobox` de la tarea 6.2 para buscar en el catálogo; seleccionar una
      empresa no suscrita invoca `POST /me/companies/{companyId}` igual que en Onboarding paso 3
    - Errores puntuales por empresa no descartan el texto de búsqueda ni las suscripciones ya confirmadas
    - **Criterios de completitud**: simular HTTP 409 de `POST /companies` completa la suscripción usando
      el `companyId` devuelto en el error, sin requerir una acción manual adicional del usuario
    - **Dependencias previas**: 11.1, 6.2
    - **Tiempo estimado**: 5h
    - _Requirements: 12.4, 12.7, 12.8, 12.9, 12.10, 12.13_

  - 11.3 Escaneo manual + clasificación de resultado + conteo de vacantes nuevas
    <!-- TODO: Dependencia externa — depende de POST /scans, GET /scans/{jobId} (ver tarea 7.7) y GET
         /me/vacancies (ver tarea 8.1).
         TODO adicional (riesgo de comportamiento, no de endpoint ausente — más peligroso porque no
         produce un 404 visible, produce un conteo incorrecto en silencio): el conteo de "vacantes
         nuevas" de esta tarea depende de que `firstSeenAt` sea INMUTABLE tras la creación de una
         `Vacante`. El contexto maestro (§21.4, "Dependencias externas pendientes" punto 6 de
         requirements.md) documenta que esa garantía todavía no está verificada por código: es la Tarea
         8 de `backend-scan-y-scoring` (`apply_missCount_logic`), que a la fecha de este plan sigue sin
         marcar `[x]`. Si esa tarea de backend no preserva `firstSeenAt` en las ramas de reaparición o
         reapertura de una vacante, el conteo de "{N} vacantes nuevas" de esta pantalla puede quedar mal
         sin lanzar ningún error — no hay síntoma visible que lo delate. Antes de confiar en este conteo
         en producción, confirmar que el test de función pura de `apply_missCount_logic` (exigido por el
         alcance de tests de `backend-scan-y-scoring`) cubre explícitamente que `firstSeenAt` no cambia
         en ninguna de esas dos ramas. -->
    - Extender `SourcesView.tsx`: botón "reintentar" sobre una fuente fallando dispara `POST /scans`
      (reescanea todas las suscripciones activas del usuario, no solo esa empresa — documentado
      explícitamente en la UI si el tiempo lo permite) y reutiliza `useScanPolling` (tarea 7.7);
      captura `scanStartedAt` al invocar `POST /scans`
    - Al `status DONE`: invoca `GET /me/vacancies?estado=activas`, cuenta registros con
      `firstSeenAt >= scanStartedAt`; usa `classifyScanResult` (tarea 5.7) para decidir el componente
      visual — pero consulta `status === "PARCIAL"`/`"FAILED"` explícitamente antes de esa función para
      preservar la distinción de 3 vías que Requirement 12.12 exige (per la nota de diseño en
      `design.md` §7)
    - Muestra "Tus {N} empresas están al día" (conteo nuevas = 0) o el resumen de vacantes nuevas
      (conteo > 0) con un componente visualmente distinto al de `FAILED`/`PARCIAL`
    - **Criterios de completitud**: simular `status: DONE` con 0 vacantes nuevas (`firstSeenAt` anterior
      a `scanStartedAt` en todas) muestra el mensaje "al día"; simular `status: PARCIAL` muestra el
      componente de fallo aunque `classifyScanResult` por sí sola no distinga `PARCIAL` de `DONE` con
      conteo 0
    - **Dependencias previas**: 11.2, 7.7, 8.1, 5.7
    - **Tiempo estimado**: 5h
    - _Requirements: 12.3, 12.5, 12.6, 12.11, 12.12_

- [x] 12. Checkpoint final
  - 12.1 QA manual contra Acceptance Criteria + verificación de reglas transversales
    - Recorrer manualmente cada Acceptance Criteria de `requirements.md` (Requirements 1-12) contra la
      app corriendo, dado que Requirement 13.6 excluye explícitamente tests de componentes/e2e de esta
      spec — esta es la pasada **consolidada final**, no la primera verificación de estos criterios (cada
      tarea de `screens/`/`mutations/` ya se verificó manualmente por su cuenta al completarse, per la
      nota del Overview sobre "Criterios de completitud")
    - Grep final sobre `src/` confirmando: cero `dangerouslySetInnerHTML`, cero referencias a
      `zinc-`/`slate-` en `components/ui/`, cero import de Redux/Zustand/Jotai/Recoil/GSAP/Three.js en
      `package.json`, y que `src/lib/` no importa nada de `api/`/`auth/`/`components/`
    - Ejecutar `npm run test` completo (las 7 Properties + los tests de ejemplo) y `npm run build`
      confirmando cero errores de tipo
    - **Criterios de completitud**: los 3 puntos anteriores documentados como pasa/no-pasa; cualquier
      falla se convierte en una tarea de corrección puntual antes de considerar la spec completa
    - **Dependencias previas**: 7.8, 8.3, 10.4, 10.5, 11.3
    - **Tiempo estimado**: 4h
    - _Requirements: 13.6 (y verificación cruzada de todos los AC de Req 1-12)_

## Notes

- Las tareas marcadas con `<!-- TODO: Dependencia externa -->` implementan el flujo asumiendo el
  contrato ya documentado en `requirements.md` §"Dependencias externas pendientes"; quedan bloqueadas en
  producción (no en su codificación) hasta que el backend correspondiente exponga el endpoint real. La
  ausencia de esos paths en `frontend/openapi/openapi.json` se verificó por grep antes de escribir este
  plan, no se asumió del texto de requirements.md únicamente. La tarea 11.3 documenta además un tercer
  tipo de riesgo (no un endpoint ausente, sino una garantía de comportamiento del backend —
  inmutabilidad de `firstSeenAt`— todavía no verificada por test) que es más peligroso precisamente
  porque falla en silencio en vez de con un error visible.
- Ninguna tarea de esta lista escribe un test que monte un componente React ni dependa de React Testing
  Library, Playwright, o Cypress (Requirement 13.6). Los "Criterios de completitud" de las tareas de
  `screens/`/`mutations/` que dicen "simular X" se verifican manualmente (devtools + mock puntual de
  `fetch`) al completar cada tarea individual — la tarea 12.1 es únicamente la pasada consolidada final
  de todos los Acceptance Criteria, no la primera vez que se verifican.
- Cada tarea de `lib/` (sección 5) empareja la función pura con su test de Vitest + fast-check en la
  misma tarea, nunca en una tarea separada posterior, per instrucción explícita de granularidad de esta
  fase. `src/lib/types.ts` (tarea 5.1) se creó como tarea propia de `lib/`, sin dependencia de `api/`,
  para cumplir la regla de capas del Overview (`lib/` → nada) — antes vivía dentro de la tarea de `api/`
  que genera tipos desde `openapi.json`, lo cual invertía esa regla y producía un ciclo de dependencia
  con las tareas 5.4/5.5 (que usan `VacancyListItem`); se corrigió separándola.
- El total de 47 tareas (~153h estimadas) es mayor al presupuesto nominal de "10 días efectivos"
  mencionado como contexto de calibración; ver la nota de calibración honesta en el Overview para la
  recomendación de qué recortar primero si el plazo es una restricción dura.
- El grafo de `waves` de abajo se calculó programáticamente a partir del campo "Dependencias previas" de
  cada tarea: `level(tarea) = 0` si no tiene dependencias, o `level(tarea) = 1 + max(level(dep) para dep
  en Dependencias previas)` en caso contrario; cada wave agrupa las tareas de un mismo `level`. Por
  construcción, ninguna tarea comparte wave con una de sus propias dependencias (garantiza ejecución
  paralela segura dentro de cada wave).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "3.1", "5.1"] },
    { "id": 2, "tasks": ["1.3", "2.2", "3.2", "5.2", "5.3", "5.4", "5.6", "5.7", "6.1", "6.2", "6.3", "6.6"] },
    { "id": 3, "tasks": ["2.3", "5.5", "6.4"] },
    { "id": 4, "tasks": ["2.4", "3.3", "6.5"] },
    { "id": 5, "tasks": ["4.1", "7.1"] },
    { "id": 6, "tasks": ["7.2", "7.7", "8.1", "9.1", "11.1"] },
    { "id": 7, "tasks": ["7.3", "8.2", "9.2", "10.1", "11.2"] },
    { "id": 8, "tasks": ["7.4", "8.3", "9.3", "11.3"] },
    { "id": 9, "tasks": ["7.5", "10.2", "10.5"] },
    { "id": 10, "tasks": ["7.6", "10.3"] },
    { "id": 11, "tasks": ["7.8", "10.4"] },
    { "id": 12, "tasks": ["12.1"] }
  ]
}
```
