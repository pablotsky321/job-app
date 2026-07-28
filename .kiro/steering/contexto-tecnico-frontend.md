---
inclusion: manual
---

# Contexto técnico — Frontend

> Recorte autosuficiente de `contexto_maestro_job_search.md` para la spec de frontend.
> No requiere leer `contexto-tecnico-backend.md` ni `contexto-tecnico-infra.md`, aunque hay
> contenido deliberadamente duplicado con ellos (ver §21.2 del contexto maestro).

---

## 1. Stack cerrado

| Capa | Tecnología |
|---|---|
| Framework | React + Vite + TypeScript (SPA, build estático) |
| Estilos | Tailwind CSS |
| Routing | React Router |
| Data fetching / caché / polling | TanStack Query |
| Formularios y validación | React Hook Form + Zod |
| Iconos | lucide-react |
| Componentes de interacción compleja | Componentes puntuales copiados vía `shadcn` CLI, siempre re-tematizados — ver §4.3. **Nunca** instalar Aceternity UI, Magic UI, ni ningún kit de componentes decorativos como dependencia |
| Motion | Framer Motion, **solo** para transiciones que comunican un cambio de estado real (ver §4.4). Nunca GSAP, nunca Three.js/WebGL |
| Estado global | **Ninguna librería.** La mayoría del estado es server-state vía TanStack Query. Único estado de app real: el token de sesión, en un Context mínimo (ver §3) |
| Tests | **Vitest, solo para lógica pura** (funciones y hooks sin dependencias de red ni de DOM), como arnés de verificación mientras Kiro construye — no para puntaje de rúbrica. Ver §1.1 |
| Tipos compartidos con backend | Generados con `openapi-typescript` desde el `openapi.json` que expone FastAPI (ver §10 del contexto maestro) — no hardcodear tipos de respuesta a mano |

**No usar:** Redux, Zustand, Jotai, Recoil, SWR, Next.js, CSS-in-JS, ninguna librería de componentes UI completa instalada como dependencia (MUI, Chakra, Ant, Aceternity, Magic UI).

### 1.1 Alcance de tests, con el mismo criterio que el backend

El backend (§14 del contexto maestro) cubre con tests **solo funciones puras** — nada de mocks de AWS,
nada de suites exhaustivas — porque en 1–2 semanas una suite completa cuesta un día que no existe. El
frontend sigue el mismo criterio, con una razón adicional propia: los tests no son para el jurado (el
hackathon no los puntúa), son un **arnés de verificación para el propio Kiro** mientras construye, de
modo que pueda confirmar que la lógica que acaba de escribir hace lo que debe sin depender de correr la
app a mano cada vez.

**Cubrir con Vitest** (lógica pura, sin red ni DOM):
- Mapeo `veredicto` → color de badge
- Condición de salida del polling de `GET /scans/{jobId}` (`DONE` / `PARCIAL` / `FAILED`)
- Lógica de "congelar el orden" de la lista durante el rescoring híbrido (§6)
- Generación del `Blob` de descarga del CV-ATS (nombre de archivo, extensión, contenido)
- Detección de "escaneo sin cambios" vs. "escaneo fallido" a partir del estado del `ScanJob`

**No cubrir:** React Testing Library, renderizado de componentes, y ningún framework end-to-end
(Playwright, Cypress). Es el siguiente nivel de costo — sí aplica ahí el argumento de tiempo/rúbrica, y
queda fuera del MVP.

---

## 2. Alcance (qué construye esta spec)

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

Los ítems 2–6 son sub-pasos del Onboarding (§7.1); 7–10 corresponden a pantallas independientes (§7.2–§7.6).
Fuera de alcance completo: ver `fuera-de-alcance.md` y §9 de este documento.

---

## 3. Autenticación

- **Cognito Hosted UI**, flujo Authorization Code + PKCE. No construir pantalla de login propia.
- **El token (`access_token` + `id_token`) se guarda en `sessionStorage`.** Decisión ya cerrada — no
  memoria pura, no `localStorage`. Sobrevive a un refresh de página, se limpia sola al cerrar la pestaña,
  y coincide con que `RefreshTokenValidity` en Cognito se bajó al mínimo permitido por AWS (1 hora): la
  sesión real muere mucho antes por el propio `sessionStorage`, así que ese valor casi nunca se ejercita.
- **Regla dura, sin excepción:** nunca usar `dangerouslySetInnerHTML` con texto de vacantes escaneadas,
  contenido generado por LLM, o cualquier dato que no haya escrito el propio usuario en un campo
  controlado. React ya escapa por defecto — no romper esa protección. Esto es lo único que hace que
  guardar el token en `sessionStorage` sea una decisión razonable en vez de un riesgo real.
- `userId` (el `sub` del JWT) nunca se lee ni se envía manualmente desde el frontend como parámetro; el
  backend lo extrae siempre del JWT en cada request. El frontend solo adjunta el header
  `Authorization: Bearer <token>`.
- Interceptor centralizado (un solo lugar, ej. wrapper de `fetch` o instancia de cliente) que adjunte el
  header y redirija a Hosted UI si la API responde 401.
- No asumir que la sesión persiste entre pestañas: si el usuario abre una pestaña nueva, pedirá login de
  nuevo. No es un bug.

---

## 4. Sistema visual

### 4.1 Tipografía

Una sola familia: **Inter**, vía `@fontsource/inter` (paquete npm, no CDN de Google Fonts — evita un
origen externo y funciona offline en dev). Se usa para toda la UI: títulos, cuerpo, labels.

Excepción: el CV-ATS en texto plano (§7.6) se renderiza con la pila `font-mono` **por defecto de
Tailwind** (`ui-monospace`), sin importar una fuente monoespaciada adicional. Comunica visualmente
"esto es texto plano" sin gastar un font load extra.

Pesos a instalar: 400 (regular), 500 (medium — labels y subtítulos), 600 (semibold — títulos de tarjeta),
700 (bold — score, títulos de sección).

### 4.2 Paleta — Tailwind config

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        // ─── PRIMARIO — azul pastel ─────────────────────────────────────
        primary: {
          50:  '#F0F6FC', // fondo general de secciones destacadas, hover sutil
          100: '#DCEAF7', // fondos de badges/tarjetas, bordes suaves
          300: '#9DC4E8', // el "pastel puro" — acentos decorativos, chevrons, iconos secundarios
          500: '#5B96D1', // íconos activos, bordes de foco, elementos grandes — NUNCA texto pequeño encima
          700: '#2E6CA3', // botones primarios, navbar, texto de link — pasa contraste AA con blanco ★
          900: '#173C5C'  // texto sobre fondos primary-50/100
        },
        // ─── NEUTROS ──────────────────────────────────────────────────
        gray: {
          50:  '#F7F8FA',
          200: '#E2E8F0',
          400: '#94A3B8',
          600: '#475569',
          900: '#1E293B'
        },
        // ─── ESTADOS SEMÁNTICOS (sin "info" — usa primary) ─────────────
        success: {
          bg:     '#F0FDF4',
          text:   '#16A34A',
          border: '#86EFAC'
        },
        error: {
          bg:     '#FEF2F2',
          text:   '#DC2626',
          border: '#FECACA'
        },
        warning: {
          bg:     '#FFFBEB',
          text:   '#D97706',
          border: '#FDE68A'
        },
        cancel: { // alias de error — cancelar es semánticamente destructivo
          DEFAULT: '#EF4444',
          text:    '#DC2626',
          bg:      '#FEF2F2'
        },
      }
    },
  },
  plugins: [],
}
```

**Regla de uso, no solo de paleta:** `primary-500` es el pastel "de verdad" — nunca ponerle texto pequeño
encima en blanco, falla contraste. Botones sólidos y navbar usan `primary-700`. `primary-100`/`primary-300`
son para fondos y acentos decorativos, no para texto ni para fondo de botón con texto blanco.

### 4.3 Componentes UI aprobados

**shadcn/ui, vía su CLI (`npx shadcn add <componente>`), nunca como paquete npm instalado.** El CLI copia
el código fuente del componente al repo propio — se edita como si lo hubiéramos escrito nosotros, no es
una dependencia de una librería cerrada. Esto no contradice la regla de "sin librería de componentes UI
completa": instalar el paquete entero de un kit sí la contradiría, copiar componentes puntuales es
composición.

**Regla no negociable:** cualquier componente copiado de shadcn se re-tematiza de inmediato con los
tokens de §4.2 (`primary`, `gray`, `success`/`error`/`warning`) en vez de dejar las variables `zinc`/
`slate` que trae por defecto. shadcn sin re-tematizar es, hoy, tan reconocible como "app genérica hecha
con IA" como lo era Bootstrap hace diez años — justo el problema que se busca evitar.

Componentes aprobados y dónde se usan:

| Componente shadcn | Dónde |
|---|---|
| `Select` | Elegir cargos objetivo, filtros del listado |
| `Command` / `Combobox` | Buscar y elegir empresa del catálogo (onboarding paso 3, vista Fuentes) |
| `Tabs` | Alternar `activas` / `aplicadas` en el listado |
| `Toast` | Feedback de guardado, aplicada, reintento de fuente |
| `Progress` | Barra de progreso del escaneo — **solo si no se implementa la alternativa grounded de §7.1 (lista de empresas con check)**, que es preferible |
| `Dialog` / `Sheet` | Confirmaciones puntuales (ej. desactivar una fuente). **No** para "Presentarse" — esa acción es inline, sin navegar, ver §7.3 |

**Nunca instalar** Aceternity UI ni Magic UI como dependencia. Si un efecto puntual de ahí resolviera un
problema funcional real (ej. un skeleton loader), se evalúa componente por componente con la pregunta de
§4.4 — no se importa el catálogo completo.

### 4.4 Dirección visual: evitar el look genérico de IA

Regla general, antes de entrar al detalle por módulo (§7): antes de cualquier elección de layout,
tipografía o color, la pregunta es **¿esto comunica algo real del contenido, o es el default que
generaría cualquier modelo para cualquier página similar?** Si es lo segundo, se revisa.

- **Gasta el esfuerzo distintivo en 1–2 momentos firma, no en las 6 pantallas por igual.** Una app donde
  cada pantalla "se esfuerza" se siente tan genérica como una donde ninguna lo hace, solo que con más
  efectos. Los dos momentos firma de este proyecto están marcados explícitamente en §7.1 y §7.3 — son los
  únicos donde vale la pena invertir tiempo de diseño real.
- **Motion solo si comunica estado, nunca decorativo.** Animar la aparición de cada tarjeta al cargar la
  página no comunica nada. Animar el badge "actualizando…" del rescoring, o la revelación del link al
  presionar "Presentarse", sí — son eventos reales que ya están definidos en la spec (§6, §7.3).
  Framer Motion, con moderación; nunca GSAP ni Three.js/WebGL — además del riesgo de que se vea genérico,
  es dependencia y superficie de fallo innecesaria en una demo en vivo.
- **Nada de `shadow-md` gris por defecto en cada tarjeta.** Usar borde de 1px con `primary-100`/`gray-200`
  en vez de elevación falsa — es más coherente con la paleta y menos "plantilla de Tailwind sin pensar".
- **Estructura como información, no como decoración.** Si algo parece una secuencia numerada (01/02/03),
  verificar primero que el contenido de verdad sea secuencial (ver §7.5, donde sí aplica) antes de
  usarlo — no ponerlo porque se ve prolijo.

---

## 5. Contratos de API que consume

Todo detrás del Cognito Authorizer. Fuente de verdad: el `openapi.json` que produce FastAPI; los tipos
TypeScript se generan con `openapi-typescript` — no escribir interfaces a mano. Si un tipo no existe
todavía porque el backend no lo ha expuesto, es señal de que falta coordinación entre specs, no de
improvisar un tipo local.

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
| `GET` | `/scans/{jobId}` | progreso del escaneo (polling) |
| `GET` | `/me/vacancies?estado=activas\|aplicadas` | listado principal / postulaciones hechas |
| `GET` | `/me/vacancies/{companyId}/{vacancyId}` | detalle de vacante |
| `POST` | `/me/vacancies/manual` | formulario de vacante manual |
| `POST` | `/me/vacancies/{companyId}/{vacancyId}/apply` | botón "Presentarse" / "Guardar" |
| `POST` | `/me/vacancies/{companyId}/{vacancyId}/cv` | botón "Generar hoja de vida" |
| `GET` / `POST` | `/me/vacancies/{companyId}/{vacancyId}/entries` | banco de preguntas y notas |
| `POST` | `/.../entries/{entryId}/answer` | ayuda de IA para redactar respuesta |

**Reglas de consumo:**

- `POST /scans` → `{ jobId }`, seguido de polling a `GET /scans/{jobId}` con TanStack Query
  (`refetchInterval`), **hasta que `status` sea `DONE`, `PARCIAL` o `FAILED`** — nunca un polling
  infinito sin condición de salida.
- Un resultado de escaneo vacío (0 vacantes nuevas) es un **estado de éxito**, no de error ni de "sin
  resultados". La UI debe distinguir "escaneado, sin novedades" de un fallo real — nunca el mismo
  componente para ambos casos.

---

## 6. Formato del score a renderizar

```json
{
  "score": 78,
  "veredicto": "buen_encaje",
  "coincidencias": ["Python", "AWS Lambda", "DynamoDB"],
  "faltantes": ["Kubernetes", "3 años de experiencia (tienes 1)"],
  "resumen": "Encaja con tu stack de backend serverless; el requisito de K8s es el vacío principal."
}
```
`veredicto` ∈ `{ excelente, buen_encaje, parcial, bajo }`. Mapeo de color sugerido:
`excelente`→success, `buen_encaje`→primary, `parcial`→warning, `bajo`→gray/error según severidad.
Definir en un solo lugar (helper o mapa de constantes), no repetir el `if/else` en cada componente.

**Rescoring híbrido (§9.4 del contexto maestro):** al cargar `/me/vacancies`, el backend puede devolver
scores marcados como desactualizados. El frontend debe:
- mostrar esos scores con un badge "actualizando…" (motion aquí es funcional, ver §4.4),
- **congelar el orden de la lista** hasta que termine el lote (no reordenar bajo los pies del usuario),
- refrescar con un refetch corto (pocos segundos) vía TanStack Query, no con un WebSocket ni polling agresivo.

---

## 7. Las seis pantallas

### 7.1 Onboarding (4 pasos) — ★ momento firma (transformación CV → perfil)

1. Pegar CV → parseo por IA → confirmar/editar perfil (React Hook Form + Zod validando el `PerfilEstructurado`)
2. Confirmar cargos sugeridos + agregar propios
3. Elegir empresas del catálogo semilla
4. Primer escaneo con barra de progreso (consume el polling de §5)

Es la primera experiencia del jurado. Si el flujo de onboarding no está pulido, la evaluación arranca mal —
priorizar esta pantalla sobre cualquier otra si el tiempo aprieta.

**Dirección visual — paso 1 (★ firma):** el valor real de esta pantalla es la transformación texto crudo →
`PerfilEstructurado`, que es literalmente la tesis del producto (el scoring depende de este perfil). Vista
dividida: a la izquierda el texto que el usuario pegó, a la derecha el perfil estructurado apareciendo
campo por campo a medida que se procesa. El motion secuencial aquí sí está justificado — comunica la
extracción ocurriendo, no es decoración.

**Dirección visual — paso 4:** en vez de un spinner o barra de porcentaje abstracta, usar la lista real de
empresas del `ScanJob` con un check apareciendo una por una conforme se completan (`empresasCompletadas`
ya es un set de nombres concretos en el backend). Más preciso y más distintivo que una barra genérica,
porque expone el estado real, no un número inventado.

### 7.2 Listado principal

Tarjeta, en este orden exacto:
- Fecha de publicación (pequeña, izquierda) + ✓ si ya se aplicó
- **Badge de score con color** — el elemento más visible de la tarjeta
- Cargo (título principal)
- Empresa (subtítulo)
- Lugar / modalidad (subtítulo)

**Dirección visual:** lista de una columna, densa, priorizando escaneabilidad — el jurado va a mirar
muchas vacantes rápido en el video. Nada de grid de 3 columnas con sombra gris genérica; borde de 1px con
`primary-100`/`gray-200` en vez de elevación falsa (§4.4).

### 7.3 Detalle de vacante — ★ momento firma (desglose del score)

Descripción completa + desglose del score (coincidencias / faltantes / resumen) + link a la publicación
oficial + botón "Presentarse".

Al presionar "Presentarse", **en la misma vista, sin navegar**: aparece el link listo para copiar y tres
acciones — "Generar hoja de vida" / "Guardar preguntas" / "Guardar" (marca como aplicada sin generar nada).
Esta revelación es un buen candidato para una transición corta de Framer Motion (comunica que algo nuevo
apareció, no es decorativa).

**Dirección visual (★ firma):** el JSON del score (§6) ya tiene una estructura dual — `coincidencias[]`
vs `faltantes[]`. Layout de dos columnas lado a lado (lo que tienes / lo que falta), con el score como
número grande arriba. No es un capricho estético, es la forma real de los datos. Nada de donut chart de
porcentaje genérico ni barra de progreso plana.

### 7.4 Postulaciones hechas → detalle

Mismo componente visual que el listado principal (sin el check, redundante ahí). Al entrar al detalle, en
este orden:
1. Descripción de la vacante + link oficial
2. Entradas guardadas (preguntas y notas), cronológicas
3. CV-ATS generado — botón **copiar** y botón **descargar**
4. Botón "Continuar proceso" → agrega una entrada nueva (rondas posteriores)

**Dirección visual — entradas guardadas:** `Entradas` es append-only y ordenado cronológicamente por
ULID — es una secuencia real de rondas de entrevista. Aquí sí aplica un timeline vertical con marcador por
ronda, a diferencia de un "01/02/03" decorativo sin secuencia real detrás (§4.4).

### 7.5 Fuentes

Catálogo compartido + suscripciones propias, con `lastScannedAt` y avisos de fuentes fallando
(`consecutiveFailures >= 3` → mensaje "No hemos podido revisar Empresa X desde el [fecha]" con botones
reintentar/desactivar). Transparencia total: el usuario debe ver qué se está escaneando.

**Dirección visual:** el dato central de esta pantalla es *salud de la fuente*, no un on/off. Status-first:
indicador de estado (verde/rojo/gris) como elemento principal de cada fila, con `lastScannedAt` y el
mensaje de fallo visible sin hacer clic — no un panel de ajustes con toggles genéricos.

**UX crítica de escaneo sin cambios:** si el escaneo programado ya corrió recientemente y el usuario
dispara uno manual, puede no haber nada nuevo que mostrar. Esto **no es un fallo** — la UI debe decir
*"Tus 12 empresas están al día — última revisión hace 2 horas"* con la lista y sus timestamps, nunca un
spinner que termina sin explicación.

### 7.6 Descarga del CV — en el navegador, no en el backend

El CV-ATS llega como texto plano desde `/me/vacancies/{...}/cv` (5–10 KB). La descarga se construye **en
el cliente** con un `Blob` y un enlace `<a download>` — cero llamadas adicionales al backend, no hay
endpoint de descarga ni presigned URL. En pantalla: texto renderizado en `font-mono`, botón **copiar**
(uso más frecuente en la práctica) y botón **descargar `.txt`/`.md`**.

**Dirección visual:** este es el único módulo donde la respuesta correcta es *no* ser distintivo. El
CV-ATS necesita verse como texto plano porque literalmente es lo que se copia tal cual a un formulario de
ATS. Cualquier intento de "hacerlo bonito" (colores, iconos, cards) contradice el propósito funcional de
la pantalla — la elegancia aquí es ejecutar bien la decisión minimalista, no añadir algo encima.

*Opcional, solo si sobra tiempo:* generar `.docx` desde el navegador con una librería JS. No es requisito
del MVP — no bloquear ninguna otra pantalla por esto.

---

## 8. Trampas técnicas específicas de frontend

| Trampa | Detalle |
|---|---|
| **CloudFront + SPA** | 403/404 deben mapearse a `/index.html` con código 200 (config de infra), pero el router del frontend debe asumir que cualquier ruta profunda puede recargarse directamente — no depender de estado en memoria que se pierda con el reload |
| **Polling sin condición de salida** | El polling de `GET /scans/{jobId}` debe detenerse en `DONE`/`PARCIAL`/`FAILED`. Un `refetchInterval` que nunca para es una fuga de requests silenciosa |
| **Reordenar la lista durante rescoring** | Ver §6 — congelar el orden mientras el lote de rescoring está en curso |
| **Escaneo vacío ≠ error** | Ver §7.5 — un componente de "sin novedades" distinto del componente de error |
| **`dangerouslySetInnerHTML`** | Ver §3 — nunca con contenido escaneado o generado por IA |
| **Token en `sessionStorage`** | Se pierde si el usuario abre una nueva pestaña — no asumir que la sesión persiste entre pestañas |
| **shadcn sin re-tematizar** | Ver §4.3 — cualquier componente copiado debe usar los tokens de `primary`/`gray`/semánticos, nunca `zinc`/`slate` por defecto |
| **Motion decorativo en cada elemento** | Ver §4.4 — anima solo lo que comunica un cambio de estado real; motion en todo se ve más genérico, no menos |

---

## 9. Fuera de alcance para esta spec

Panel de administración con UI, BYOK, registro público, recuperación de contraseña self-service, filtro
por idioma, pantalla de históricos, vista agregada de preguntas por empresa, cualquier librería de estado
global, tests de componentes o end-to-end, cualquier librería de componentes UI o de motion decorativo
completa (Aceternity, Magic UI, GSAP, Three.js). Ver `fuera-de-alcance.md` para el detalle completo y el
argumento de cada corte.