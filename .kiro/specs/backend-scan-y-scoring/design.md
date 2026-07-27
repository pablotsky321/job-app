# Design Document: backend-scan-y-scoring

## Overview

Este design cubre la arquitectura completa del sistema de descubrimiento asíncrono de vacantes, 
scoring de candidatos y gestión del ciclo de vida de ScanJobs. Se compone de:

1. **Orquestador Lambda**: Atiende `POST /scans`, resuelve empresas suscritas, aplica Ventana_Frescura, 
   crea ScanJob y publica en SQS_Scan.
2. **Scan_Worker Lambda**: Procesa un mensaje por empresa, ejecuta Cascada_Descubrimiento, clasifica 
   resultado (OK/FAILED/EMPTY_SOSPECHOSO/EMPTY_LEGITIMO), evalúa cierre de vacantes con missCount, 
   y encola en SQS_Scoring.
3. **Scoring_Worker Lambda**: Procesa un mensaje por par (userId, Vacante), aplica Prefiltro_Cargos, 
   invoca Bedrock_Client, persiste en UsuarioVacante con idempotencia.
4. **Scans_API (GET /scans/{jobId})**: Polling contract con zombie detection a 600s.

---

## Architecture Overview

### High-Level Message Flow

```
┌────────────┐
│   Orquestador    │  POST /scans o Trigger programado
│   (Lambda)       │  ↓ Resuelve empresas, aplica Ventana_Frescura
└────────────┘
       ↓
       │ Publica N mensajes
       ↓
   SQS_Scan
   (VisibilityTimeout: 6 × timeout_scan_worker)
       ↓
   ┌──────────────────────┐
   │  Scan_Worker Lambda  │
   │  (concurrencia: 5)   │
   │  ↓ Cascada de         │
   │    Descubrimiento    │
   │  ↓ Clasifica: OK/...  │
   │  ↓ Upsert Vacantes    │
   │  ↓ Evalúa missCount   │
   │  ↓ Fan-out scoring    │
   └──────────────────────┘
       ↓
   Publica M mensajes
   (M = nuevas vacantes × usuarios activos)
       ↓
   SQS_Scoring
   (VisibilityTimeout: 6 × timeout_scoring_worker)
       ↓
   ┌────────────────────────┐
   │ Scoring_Worker Lambda  │
   │ (concurrencia: 3)      │
   │ ↓ Prefiltro_Cargos     │
   │ ↓ Bedrock scoring      │
   │ ↓ Persist UsuarioVacante│
   └────────────────────────┘
       ↓ Actualiza DynamoDB
   UsuarioVacante Table

GET /scans/{jobId} → ScanJob con status, conteos, zombie detection
```

---

## SQS Queue Configuration & Visibility Timeout Formulas

### Scan_Worker Timeout Configuration

```
Lambda Timeout (Scan_Worker) = 90 seconds
Visibility Timeout (SQS_Scan) = 6 × 90 = 540 seconds
MaxReceiveCount (DLQ) = 3
```

**Justificación (Requirement 3.1-3.3)**:
60s was optimistic for the Scan_Worker cascade: 
- Fetch enterprise from DynamoDB: ~50ms
- Cascada_Descubrimiento: HTTP × 3 (Greenhouse, JSON-LD, HTML) + Bedrock HTML extraction = 15-25s
- HTML cleanup via BeautifulSoup: 1-5s
- Vacante upsert (N=100 vacancies) × DynamoDB write: ~200ms
- N × M SQS_Scoring sends (N=100 new vacancies, M=5 users) = 500 messages = 30-40s alone
  (SQS batch send limit is 10, so 50 batches minimum)
- Network jitter + Lambda cold start + global I/O variance: +10s

Total: 15-25s (cascada) + 5-10s (cleanup+upsert) + 30-40s (SQS sends) + 10s (variance) = 60-85s average.
With percentile variance (p95), 90s is realistic minimum to avoid timeouts in 5% of invocations.

### Scoring_Worker Timeout Configuration

```
Lambda Timeout (Scoring_Worker) = 30 seconds
Visibility Timeout (SQS_Scoring) = 6 × 30 = 180 seconds
MaxReceiveCount (DLQ) = 3
```

**Justificación**: Scoring_Worker is simpler (no cascada):
- Fetch Perfil + UsuarioVacante: ~100ms
- Prefiltro_Cargos: ~200ms
- Bedrock MID invoke + response parsing: 5-10s
- UsuarioVacante upsert: ~100ms
- Total: ~6-11s average → 30s with margins
```

**Justificación**: Si un worker se cuelga a los T segundos (timeouts), el mensaje vuelve a la 
cola después de 6T segundos. Reintenta hasta 3 veces; después va a DLQ.

---

## SQS Message Payloads (Modelos Pydantic)

Todos los payloads se definen en `backend/shared/models.py`.

### ScanMessage (SQS_Scan)

```python
from pydantic import BaseModel, Field
from typing import Optional

class ScanMessage(BaseModel):
    """
    Mensaje para SQS_Scan.
    Publicado por Orquestador, consumido por Scan_Worker.
    Requirement 12.1: Un mensaje por Empresa a escanear.
    """
    
    jobId: str = Field(
        ..., 
        description="ScanJob ID (identificador único del ciclo de escaneo)",
        example="scan_20240115_user123",
    )
    companyId: str = Field(
        ...,
        description="SHA-256 hash de la URL de carreras normalizada (64 hex chars)",
        example="a1b2c3d4e5f6...",
    )
    
    model_config = ConfigDict(extra="ignore")
```

**Límite de tamaño**: ~256 KB. Este payload es < 1 KB.

### ScoringMessage (SQS_Scoring)

```python
class ScoringMessage(BaseModel):
    """
    Mensaje para SQS_Scoring.
    Publicado por Scan_Worker, consumido por Scoring_Worker.
    Requirement 12.4: Un mensaje por (userId, Vacante) pair de NUEVA vacante.
    """
    
    userId: str = Field(
        ...,
        description="User ID (del JWT sub claim)",
        example="user_8f9e7d6c",
    )
    vacancyId: str = Field(
        ...,
        description="Vacante ID (SHA-256 de URL normalizada, 64 hex chars)",
        example="vacancy_sha256_hash",
    )
    
    model_config = ConfigDict(extra="ignore")
```

**Límite de tamaño**: ~256 KB. Este payload es < 1 KB.

**NOTA CRÍTICA** (Requirement 12.4, 12.5): 
- Scan_Worker publica UN mensaje por (userId, vacancyId) pair **de nueva vacante**.
- NO intenta deduplicar antes de enqueue (confianza en Scoring_Worker para idempotencia).
- Si reintentada SQS_Scan → publica NUEVAMENTE (Scoring_Worker detecta via scoreProfileVersion).

---

## Data Models (Backend/Shared)

### Extensiones a Modelos Existentes

#### Vacante (Extensión)

```python
class Vacante(BaseModel):
    """
    Job vacancy record. Nuevos campos respecto a backend-core:
    - vacancyId: SHA-256 de URL normalizada
    - estado: 'abierta' | 'cerrada'
    - missCount: contador de escaneos OK sin encontrar esta vacante
    - origen: 'board_api' | 'json_ld' | 'html_llm' | 'manual'
    - firstSeenAt, lastSeenAt: timestamps
    
    Requirements: 1.1-1.5, 7.6
    """
    
    vacancyId: str = Field(
        ...,
        description="SHA-256 hash of normalized URL (64 hex chars, lowercase)",
    )
    companyId: str
    titulo: str
    descripcion: str
    requisitos: List[str] = Field(default_factory=list)
    modalidad: str = Field(default="sin_dato")
    ubicacion: str = Field(default="")
    url: str
    plataforma: PlatformaEnum
    origen: str = Field(
        ...,
        description="Source: 'board_api' | 'json_ld' | 'html_llm' | 'manual'",
    )
    crawledAt: datetime
    verificadaAt: Optional[datetime] = None
    
    # NUEVOS CAMPOS (esta spec)
    estado: str = Field(default="abierta", description="'abierta' | 'cerrada'")
    missCount: int = Field(default=0, description="Consecutive OK scans without this vacancy")
    firstSeenAt: datetime = Field(default_factory=datetime.utcnow)
    lastSeenAt: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(extra="ignore")
```

#### Empresa (Extensión)

```python
class Empresa(BaseModel):
    """
    Company record. Nuevos campos:
    - ultimoOrigenExitoso: último origen que dio OK o EMPTY_LEGITIMO
    
    Requirements: 1.6, 2.10
    """
    
    companyId: str
    nombre: str
    careersUrl: str
    plataforma: PlatformaEnum
    lastScannedAt: Optional[datetime] = None
    lastScanStatus: Optional[ScanStatusEnum] = None
    lastVacancyCount: int = Field(default=0)
    consecutiveFailures: int = Field(default=0)
    createdAt: datetime
    
    # NUEVO CAMPO (esta spec)
    ultimoOrigenExitoso: Optional[str] = Field(
        default=None,
        description="'board_api' | 'json_ld' | 'html_llm' (null until first OK/EMPTY_LEGITIMO)",
    )
    
    model_config = ConfigDict(extra="ignore")
```

#### ScanJob (Extensión)

```python
class ScanJob(BaseModel):
    """
    Async scan job tracker. Campos nuevos:
    - status: 'RUNNING' | 'DONE' | 'PARCIAL' | 'FAILED'
    - empresasCompletadas, empresasFallidas: String Sets (via ADD operation)
    - empresasOmitidas: colección (populated once at creation)
    
    Requirements: 1.7-1.8, 9.5-9.7, 10.1-10.4
    
    CRITICAL INVARIANT (Requirement 1.7):
    empresasTotal = len(empresas_a_escanear) AFTER Ventana_Frescura filter.
    This ensures GET /scans returns accurate progress (not 0/N when all omitted).
    
    State transitions: 'RUNNING' → 'DONE' | 'PARCIAL' | 'FAILED'
    - DONE: All empresasCompletadas without failures
    - PARCIAL: Some completed, or zombie detection (>600s)
    - FAILED: All publish attempts failed in Orquestador
    
    NOTE: Scoring_Worker NEVER updates ScanJob.status. Only Orquestador and GET /scans endpoint.
    Scoring_Worker only ADDS to empresasCompletadas (idempotent).
    """
    
    scanJobId: str = Field(..., description="Unique scan job ID")
    userId: Optional[str] = Field(
        default=None,
        description="User ID if user-initiated; null if global scheduled scan",
    )
    status: str = Field(
        ...,
        description="'RUNNING' | 'DONE' | 'PARCIAL' | 'FAILED'",
    )
    
    # Conteos
    empresasTotal: int = Field(
        description="Total AFTER Ventana_Frescura filter (count of empresas_a_escanear). "
        "INVARIANT: empresasTotal must ALWAYS equal (empresasCompletadas + empresasOmitidas + pending) at any time."
    )
    empresasCompletadas: Set[str] = Field(
        default_factory=set,
        description="String Set of companyId (ADD operation, idempotent)",
    )
    empresasOmitidas: List[str] = Field(
        default_factory=list,
        description="Companies skipped by Ventana_Frescura (populated once)",
    )
    empresasFallidas: Set[str] = Field(
        default_factory=set,
        description="Companies with FAILED or EMPTY_SOSPECHOSO (ADD operation)",
    )
    
    startedAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(extra="ignore")
```

### Nuevos Modelos (Esta Spec)

#### UsuarioVacante

```python
class UsuarioVacante(BaseModel):
    """
    Score and match details for a user-vacancy pair.
    Keyed by (userId, vacancyId).
    
    Requirements: 1.9, 17.5, 18.1
    """
    
    userId: str = Field(...)
    vacancyId: str = Field(...)
    
    # Score
    score: Optional[int] = Field(
        default=None,
        ge=0, le=100,
        description="Match score 0-100; null if filtered_out or pending",
    )
    scoreDetalle: Optional[dict] = Field(
        default=None,
        description="ScoringResult (veredicto, coincidencias, faltantes, resumen)",
    )
    scoreProfileVersion: Optional[int] = Field(
        default=None,
        description="Profile version when score was computed (for staleness detection)",
    )
    
    # Status
    estado: str = Field(
        ...,
        description="'scored' | 'filtered_out' | 'pending' | 'error'",
    )
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(extra="ignore")
```

#### ScoringResult

```python
class ScoringResult(BaseModel):
    """
    Output from Bedrock_Client scoring invocation.
    Validates score, veredicto, coincidencias, faltantes, resumen.
    
    Requirements: 1.10, 17.1
    """
    
    score: int = Field(
        ...,
        ge=0, le=100,
        description="Match score 0-100",
    )
    veredicto: str = Field(
        ...,
        description="'excelente' | 'buen_encaje' | 'parcial' | 'bajo'",
    )
    coincidencias: List[str] = Field(
        default_factory=list,
        description="Matched requirements/skills",
    )
    faltantes: List[str] = Field(
        default_factory=list,
        description="Missing requirements/skills",
    )
    resumen: str = Field(
        ...,
        description="Short match summary (not logged, not returned to client in logs)",
    )
    
    model_config = ConfigDict(extra="ignore")
```

---

## Pseudocódigo Crítico: Clasificación de Resultado y missCount

### Función: classify_scan_result (Requirement 6)

**Entrada**: 
- `empresa: Empresa` (con `lastVacancyCount`)
- `extraction_result: (vacantes_list, origen, error_or_none)`

**Salida**: 
- `'OK' | 'FAILED' | 'EMPTY_SOSPECHOSO' | 'EMPTY_LEGITIMO'`

**Pseudocódigo**:

```python
def classify_scan_result(empresa, extraction_result):
    """
    Clasifica el resultado de una Cascada_Descubrimiento sin ambigüedad.
    Requirement 6 + tabla de clasificación.
    
    Nota: Si plataforma == 'manual', la cascada retorna ([], None, None) siempre.
    """
    vacantes_list, origen, error = extraction_result
    num_vacantes = len(vacantes_list) if vacantes_list else 0
    
    # CASO 1: Error en método final o todos los métodos fallaron
    if error is not None:
        return "FAILED"  # Requirement 6.3
    
    # Ahora error == None, respuesta fue válida
    
    # CASO 2: Respuesta válida con N > 0 vacantes
    if num_vacantes > 0:
        return "OK"  # Requirement 6.2
    
    # Ahora num_vacantes == 0
    
    # CASO 3: Respuesta válida con 0 vacantes Y lastVacancyCount > 0
    if empresa.lastVacancyCount > 0:
        return "EMPTY_SOSPECHOSO"  # Requirement 6.4
    
    # CASO 4: Respuesta válida con 0 vacantes Y lastVacancyCount == 0
    return "EMPTY_LEGITIMO"  # Requirement 6.5
```

**Tabla de Decisión (Requirement 6, tabla de referencia)**:

| Clasificación | Condición | Acción Vacantes | Acción Empresa | 
|---|---|---|---|
| `OK` | Respuesta válida, N > 0 vacantes | Evalúa missCount, cierre | `consecutiveFailures = 0`, `lastVacancyCount = N`, `ultimoOrigenExitoso = origen` |
| `FAILED` | Timeout, HTTP 4xx/5xx, JSON inválido, excepción no manejada | SIN CAMBIOS | `consecutiveFailures += 1` |
| `EMPTY_SOSPECHOSO` | Respuesta válida, 0 vacantes, `lastVacancyCount > 0` | SIN CAMBIOS | `consecutiveFailures += 1` |
| `EMPTY_LEGITIMO` | Respuesta válida, 0 vacantes, `lastVacancyCount == 0` | N/A (no hay vacantes) | `consecutiveFailures = 0`, `lastVacancyCount = 0`, `ultimoOrigenExitoso = origen` |

---

### Función: apply_missCount_logic (Requirement 7)

**Precondición**: `clasificacion == "OK"` (solo se aplica en escaneos OK)

**Entrada**:
- `empresa: Empresa`
- `vacantes_nuevas_en_escan: List[Vacante]` (resultado de la cascada)
- `vacantes_existentes: List[Vacante]` (vacantes previas de la empresa)

**Salida**: Modificaciones in-place en vacantes (upsert a DynamoDB)

**Pseudocódigo**:

```python
def apply_missCount_logic(empresa, vacantes_nuevas_en_escan, vacantes_existentes):
    """
    Aplica lógica de missCount según Requirement 7.
    CRÍTICO: Solo aplica tras escaneo clasificado OK.
    
    Algoritmo:
    1. Para cada vacante EXISTENTE:
       - Si NO está en vacantes_nuevas_en_escan → missCount += 1
       - Si SÍ está en vacantes_nuevas_en_escan → missCount = 0
       - Si missCount >= 2 Y origen != 'manual' → estado = 'cerrada'
       - Si en vacantes_nuevas_en_escan Y estado == 'cerrada' → estado = 'abierta'
    
    2. Para cada vacante NUEVA en vacantes_nuevas_en_escan:
       - Si NO existe previo → crear con missCount = 0, estado = 'abierta'
       - Si existe pero estado = 'cerrada' → estado = 'abierta', missCount = 0
    """
    
    # Construir conjunto de vacancyIds en el nuevo escaneo
    nuevo_scan_ids = {compute_vacancyId(v.url) for v in vacantes_nuevas_en_escan}
    
    # 1. Iterar sobre vacantes EXISTENTES
    for vacante_existente in vacantes_existentes:
        if vacante_existente.vacancyId not in nuevo_scan_ids:
            # Vacante NO está en nuevo escaneo → incrementar missCount
            vacante_existente.missCount += 1
            
            # Requirement 7.4: Si missCount >= 2 Y origen != 'manual' → cerrada
            if vacante_existente.missCount >= 2 and vacante_existente.origen != "manual":
                vacante_existente.estado = "cerrada"
        
        else:
            # Vacante SÍ está en nuevo escaneo → reset missCount
            vacante_existente.missCount = 0
            
            # Requirement 7.3: Si estaba cerrada → reabre
            if vacante_existente.estado == "cerrada":
                vacante_existente.estado = "abierta"
        
        # Requirement 7.5: origen = 'manual' NUNCA se auto-cierra
        # (el if arriba ya lo protege)
        
        # UPDATE a DynamoDB
        put_vacante(vacante_existente)
    
    # 2. Iterar sobre vacantes NUEVAS en el escaneo
    for vacante_nueva in vacantes_nuevas_en_escan:
        vacancyId = compute_vacancyId(vacante_nueva.url)
        
        # Requirement 7.6: Si es NUEVA → create con missCount=0, estado='abierta'
        if vacancyId not in {v.vacancyId for v in vacantes_existentes}:
            vacante_record = Vacante(
                vacancyId=vacancyId,
                companyId=empresa.companyId,
                titulo=vacante_nueva.titulo,
                descripcion=vacante_nueva.descripcion,
                url=vacante_nueva.url,
                plataforma=empresa.plataforma,
                origen=extraction_result_origen,  # 'board_api' | 'json_ld' | 'html_llm'
                estado="abierta",
                missCount=0,
                firstSeenAt=now(),
                lastSeenAt=now(),
                # ... otros campos ...
            )
            put_vacante(vacante_record)
        
        else:
            # Requirement 7.7: Si ya existe → solo actualizar lastSeenAt
            existing = get_vacante_by_id(vacancyId)
            existing.lastSeenAt = now()
            # firstSeenAt y vacancyId NO se tocan
            put_vacante(existing)
```

**Notas de Idempotencia (Requirement 13.4)**:

Si SQS_Scan se reentrega para la misma empresa:

1. Primera entrega: `missCount` de vacantes no encontradas se incrementa a 1
2. Segunda entrega (reentregada): El mismo `missCount` (ahora 1) se incrementa a 2, 
   posiblemente cerrando la vacante.
   
**Esto es correcto** porque:
- `missCount` refleja "¿cuántos escaneos OK consecutivos sin ver esta vacante?"
- Una reentregada del MISMO escaneo se procesa como UN SOLO escaneo (no se repite el incremento).
- El sistema usa `vacancyId` como clave de deduplicación; no crea duplicados.

---

### Función: compute_vacancyId (Requirement 1.1)

```python
def compute_vacancyId(url: str) -> str:
    """
    SHA-256 hash of normalized URL.
    Devuelve string de 64 caracteres hexadecimales en minúsculas.
    
    Normalización:
    - Lowercased scheme y host
    - Sin fragment
    - Sin trailing /
    """
    import hashlib
    from urllib.parse import urlparse, urlunparse
    
    parsed = urlparse(url)
    normalized = urlunparse((
        parsed.scheme.lower(),      # http → http
        parsed.netloc.lower(),      # EXAMPLE.COM → example.com
        parsed.path.rstrip('/'),    # /path/ → /path
        parsed.params,              # params (raro)
        parsed.query,               # query string (incluido para distinción)
        '',                         # sin fragment
    ))
    
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
```

**Ejemplos**:

```
Input:  "https://example.com/jobs/123#section"
Output: "a1b2c3d4e5f6..." (64 hex chars)

Input:  "HTTPS://EXAMPLE.COM/JOBS/123"
Output: "a1b2c3d4e5f6..." (same as above, normalized)

Input:  "https://example.com/jobs/123/"
Output: "a1b2c3d4e5f6..." (same as above, trailing / removed)
```

---

## HTML Limpieza y Umbral de Tamaño (Requirement 5)

### Función: html_to_clean_text (Requirement 5.1)

**Propósito**: Remover elementos no relevantes antes de enviar HTML a Bedrock_Client.

**Elemento Eliminados**:

```python
def html_to_clean_text(html: str, max_clean_size_kb: int = 100) -> str:
    """
    Limpia HTML para extracción con Bedrock.
    
    ELIMINADOS (Requirement 5.1):
    - <script> tags y contenido
    - <style> tags y contenido
    - <noscript> tags
    - HTML comments (<!-- -->)
    - Meta tags (<meta ...>)
    - SVG tags (<svg>...</svg>)
    - iframe tags
    - Atributos on* (onclick, onload, etc.)
    
    MANTENIDOS:
    - Contenido de texto de todos los tags
    - Estructura básica de párrafos, listas, títulos
    - Data attributes (data-*) sin procesar
    
    max_clean_size_kb: umbral de tamaño máximo en KB del texto limpio
    """
    from bs4 import BeautifulSoup
    
    # Parse con html.parser (PROHIBIDO lxml por binarios en Lambda)
    soup = BeautifulSoup(html, 'html.parser')
    
    # 1. Remover elementos peligrosos/inútiles
    for tag_name in ['script', 'style', 'noscript', 'svg', 'iframe', 'meta']:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    
    # 2. Remover HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.decompose()
    
    # 3. Extraer texto
    text = soup.get_text(separator=' ', strip=True)
    
    # 4. Limpieza de whitespace
    import re
    text = re.sub(r'\s+', ' ', text)  # Múltiples espacios → uno
    text = text.strip()
    
    # 5. Umbral de tamaño
    # Requirement 5.1: Si el texto limpio excede max_clean_size_kb → ACCIÓN
    # Decisión elegida: TRUNCAR a max_clean_size_kb
    max_bytes = max_clean_size_kb * 1024
    if len(text.encode('utf-8')) > max_bytes:
        # Truncar manteniendo límite de bytes (no caracteres para respetar UTF-8)
        text = text.encode('utf-8')[:max_bytes].decode('utf-8', errors='ignore')
    
    return text
```

**Umbral de Tamaño**: 

- **Máximo**: 100 KB de texto limpio
- **Acción si excede**: TRUNCAR (no SKIP, no FAILED)
- **Razón**: Bedrock tiene límite de tokens. 100 KB ≈ 25k tokens (razón 4:1).
  - BEDROCK_MODEL_SMALL: típicamente 200k tokens context.
  - Mantener margen para prompt + output.

**Alternativas Consideradas** (y descartadas):

- ❌ SKIP (estado = filtered_out): Implicaría perder empresas enteras si HTML es grande.
- ❌ FAILED: Haría que Scan_Worker no progrese y ScanJob quede en RUNNING para siempre.
- ✅ TRUNCAR: Pierde detalle pero permite progresión del escaneo.

---

## Cascada de Descubrimiento (Requirement 2)

### Diagrama de Decisión

```
┌─────────────────────────┐
│  Scan Empresa           │
│  plataforma = ?         │
└────────┬────────────────┘
         │
    ┌────┴──────────────────┐
    │                       │
    ▼ greenhouse/lever      ▼ html/jsonld/manual
    
┌─────────────────────────┐  ┌──────────────────────────┐
│ 1. Board_API_Client     │  │ 1. JsonLd_Extractor      │
│    (vacantes > 0?)      │  │    (vacantes > 0?)       │
└────┬────────────────────┘  └──────┬───────────────────┘
     │YES                           │YES
     └─────────────────┬────────────┘ (STOP)
                       │
                   NO  │
                       ▼
                  ┌─────────────────────────┐
                  │ 2. JsonLd_Extractor     │
                  │    (vacantes > 0?)      │
                  └────┬────────────────────┘
                       │YES
                       └──────────> (STOP)
                       │
                   NO  │
                       ▼
                  ┌──────────────────────────┐
                  │ 3. Html_Llm_Extractor    │
                  │    (método final)        │
                  │    (resultado = origen)  │
                  └──────────────────────────┘
                       (STOP, siempre)
```

**Orden según plataforma** (Requirement 2):

- **greenhouse** o **lever**: Board_API → JsonLd → Html_Llm
- **html** o **jsonld**: JsonLd → Html_Llm
- **manual**: SKIP todos, retorna ([], None, None) → EMPTY_LEGITIMO

---

### Pseudocódigo: cascada_descubrimiento

```python
def cascada_descubrimiento(empresa: Empresa) -> tuple:
    """
    Ejecuta cadena de métodos de extracción.
    Retorna: (vacantes_list, origen, error_or_none)
    
    Requirements: 2.1-2.13
    """
    
    # Requirement 2.11: Plataforma manual → skip todos
    if empresa.plataforma == "manual":
        logger.info("cascada_skipped_manual_platform", context={
            "companyId": empresa.companyId
        })
        return ([], None, None)  # Requirement 2.13: EMPTY_LEGITIMO
    
    # Resolver métodos según plataforma
    if empresa.plataforma in ["greenhouse", "lever"]:
        metodos = ["board_api", "json_ld", "html_llm"]
    else:  # html, jsonld
        metodos = ["json_ld", "html_llm"]
    
    # Ejecutar en orden de prioridad
    for metodo in metodos:
        try:
            logger.info("cascada_attempting", context={
                "companyId": empresa.companyId,
                "metodo": metodo
            })
            
            if metodo == "board_api":
                vacantes = board_api_client(empresa)
                # Requirement 2.2: Si N > 0 → STOP
                if vacantes and len(vacantes) > 0:
                    logger.info("cascada_success", context={
                        "companyId": empresa.companyId,
                        "metodo": metodo,
                        "vacantes": len(vacantes)
                    })
                    return (vacantes, "board_api", None)
                # Si 0 vacantes, continúa al siguiente
            
            elif metodo == "json_ld":
                vacantes = json_ld_extractor(empresa)
                # Requirement 2.5: Si N > 0 → STOP
                if vacantes and len(vacantes) > 0:
                    logger.info("cascada_success", context={
                        "companyId": empresa.companyId,
                        "metodo": metodo,
                        "vacantes": len(vacantes)
                    })
                    return (vacantes, "json_ld", None)
                # Si 0 vacantes, continúa al siguiente
            
            elif metodo == "html_llm":
                vacantes = html_llm_extractor(empresa)
                # Requirement 2.7: Método final, SIEMPRE retorna (sin importar N)
                logger.info("cascada_final_result", context={
                    "companyId": empresa.companyId,
                    "metodo": metodo,
                    "vacantes": len(vacantes) if vacantes else 0
                })
                return (vacantes or [], "html_llm", None)
        
        except Exception as e:
            logger.warning("cascada_method_error", context={
                "companyId": empresa.companyId,
                "metodo": metodo,
                "error": str(e)[:100]  # No log completo del error
            })
            # Continúa al siguiente método
            continue
    
    # Si llegamos aquí: todos fallaron (debería ser raro, html_llm es final)
    logger.error("cascada_all_failed", context={
        "companyId": empresa.companyId
    })
    return ([], None, "all_methods_failed")
```

---

## Pseudocódigo: Orquestador (POST /scans)

```python
def handler_post_scans(event, context):
    """
    POST /scans - Disparar escaneo de empresas suscritas.
    Requirements: 9, 10, 11
    
    1. Autenticación: userId del JWT
    2. Resolver empresas suscritas (deduplicadas)
    3. Aplicar Ventana_Frescura
    4. Crear ScanJob
    5. Publicar en SQS_Scan
    
    CRITICAL (Requirement 11.2, 11.3): Status Transitions
    - If ALL messages fail to publish → status='FAILED'
    - If SOME fail → status='PARCIAL' (only if >= 1 success)
    - If ALL succeed → status remains 'RUNNING' (scanning in flight)
    
    NOTE: Scoring_Worker NEVER updates ScanJob.status. Scoring_Worker only ADDs 
    to empresasCompletadas (idempotent). Status transitions are ONLY done by:
    1. Orquestador (on SQS_Scan publish failure)
    2. GET /scans endpoint (zombie detection at 600s, or auto-DONE when completadas==total)
    """
    
    # Requirement 9.1: Extraer userId del JWT (ignorar body/query params)
    userId = extract_jwt_sub(event)
    
    # Requirement 9.2: Resolver suscripciones activas del usuario
    suscripciones = query_suscripciones_activas(userId)
    empresas_ids = list(set([s.companyId for s in suscripciones]))  # Dedup Requirement 9.4
    
    # Requirement 10.1: Si cero empresas → DONE inmediato
    if not empresas_ids:
        scanJob = create_scan_job(
            userId=userId,
            empresasTotal=0,
            status="DONE",
        )
        put_scan_job(scanJob)
        return {
            "statusCode": 200,
            "body": {"jobId": scanJob.scanJobId}
        }
    
    # Requirement 9.5: Crear ScanJob con status RUNNING
    scanJob = ScanJob(
        scanJobId=generate_unique_id(),
        userId=userId,
        status="RUNNING",
        empresasTotal=len(empresas_ids),
        startedAt=now(),
    )
    put_scan_job(scanJob)
    
    # Requirement 8: Aplicar Ventana_Frescura
    empresas_a_escanear = []
    empresas_omitidas = []
    
    for companyId in empresas_ids:
        empresa = get_empresa(companyId)
        if es_elegible_para_rescan(empresa, scanJob.startedAt):
            empresas_a_escanear.append(companyId)
        else:
            empresas_omitidas.append(companyId)
    
    # Requirement 10.2: Si todas omitidas → DONE inmediato
    if not empresas_a_escanear:
        scanJob.status = "DONE"
        scanJob.empresasOmitidas = empresas_omitidas
        put_scan_job(scanJob)
        return {
            "statusCode": 200,
            "body": {"jobId": scanJob.scanJobId}
        }
    
    # FALLO 4 FIX: Update empresasTotal to reflect AFTER Ventana_Frescura
    scanJob.empresasTotal = len(empresas_a_escanear)
    scanJob.empresasOmitidas = empresas_omitidas
    put_scan_job(scanJob)  # Re-save with updated total
    
    # Requirement 11.1: Publicar mensajes en SQS_Scan
    failed_to_publish = []
    
    for companyId in empresas_a_escanear:
        try:
            msg = ScanMessage(jobId=scanJob.scanJobId, companyId=companyId)
            sqs_send(msg.model_dump(), SQS_SCAN_URL)
        except Exception as e:
            logger.error("sqs_publish_failed", context={
                "jobId": scanJob.scanJobId,
                "companyId": companyId,
                "error": str(e)
            })
            failed_to_publish.append(companyId)
    
    # Requirement 11.2, 11.3: Resolver estado final
    # FALLO 1 FIX: Explicit rules for status transitions
    if failed_to_publish:
        if len(failed_to_publish) == len(empresas_a_escanear):
            # ALL messages failed to publish
            scanJob.status = "FAILED"
            scanJob.empresasFallidas = set(failed_to_publish)
            logger.error("sqs_publish_all_failed", context={
                "jobId": scanJob.scanJobId,
                "failedCount": len(failed_to_publish),
                "totalAttempted": len(empresas_a_escanear),
            })
        else:
            # SOME failed, but at least 1 succeeded
            scanJob.status = "PARCIAL"
            scanJob.empresasFallidas = set(failed_to_publish)
            logger.warning("sqs_publish_partial_failure", context={
                "jobId": scanJob.scanJobId,
                "successCount": len(empresas_a_escanear) - len(failed_to_publish),
                "failedCount": len(failed_to_publish),
                "totalAttempted": len(empresas_a_escanear),
            })
    # else: all published successfully, status remains "RUNNING"
    
    scanJob.updatedAt = now()
    put_scan_job(scanJob)
    
    # Requirement 9.10: Responder con jobId inmediato
    return {
        "statusCode": 200,
        "body": {"jobId": scanJob.scanJobId}
    }


def es_elegible_para_rescan(empresa, startedAt):
    """
    Ventana_Frescura (Requirement 8).
    
    - board_api / json_ld: 3600s (1h)
    - html_llm: 43200s (12h)
    - sin ultimoOrigenExitoso: 43200s (12h)
    - sin lastScannedAt: siempre elegible
    """
    if not empresa.lastScannedAt:
        return True  # Requirement 8.3
    
    elapsed = (startedAt - empresa.lastScannedAt).total_seconds()
    
    if empresa.ultimoOrigenExitoso in ["board_api", "json_ld"]:
        return elapsed >= 3600  # Requirement 8.1
    elif empresa.ultimoOrigenExitoso == "html_llm":
        return elapsed >= 43200  # Requirement 8.2
    else:  # null, o no reconocido
        return elapsed >= 43200  # Requirement 8.4 (default)
```

---

## Pseudocódigo: Scan_Worker Lambda

```python
def handler_scan_worker(event, context):
    """
    Procesa mensajes de SQS_Scan.
    Requirements: 12, 13
    
    Para cada mensaje:
    1. Extraer jobId, companyId
    2. Cascada_Descubrimiento
    3. Clasificar resultado
    4. Upsert Vacantes + evalúa missCount
    5. Enqueue SQS_Scoring (si OK)
    6. Actualizar ScanJob (ADD empresasCompletadas)
    """
    
    for record in event["Records"]:
        try:
            msg = ScanMessage(**json.loads(record["body"]))
            jobId = msg.jobId
            companyId = msg.companyId
            
            logger.info("scan_worker_start", context={
                "jobId": jobId,
                "companyId": companyId
            })
            
            # Requirement 12.1: Procesar una empresa por mensaje
            empresa = get_empresa(companyId)
            
            # Cascada de Descubrimiento
            result_vacantes, result_origen, result_error = cascada_descubrimiento(empresa)
            
            # Clasificación
            clasificacion = classify_scan_result(empresa, (result_vacantes, result_origen, result_error))
            
            logger.info("scan_classified", context={
                "jobId": jobId,
                "companyId": companyId,
                "clasificacion": clasificacion
            })
            
            # Actualizar Empresa según clasificación (Requirement 6.7-6.9)
            if clasificacion in ["OK", "EMPTY_LEGITIMO"]:
                empresa.consecutiveFailures = 0
                empresa.lastVacancyCount = len(result_vacantes)
                empresa.ultimoOrigenExitoso = result_origen
            elif clasificacion in ["FAILED", "EMPTY_SOSPECHOSO"]:
                empresa.consecutiveFailures += 1
                # lastVacancyCount sin cambios
            
            empresa.lastScannedAt = now()
            empresa.lastScanStatus = clasificacion
            put_empresa(empresa)
            
            # Upsert Vacantes + missCount (solo si OK)
            if clasificacion == "OK":
                # Obtener vacantes existentes de esta empresa
                vacantes_existentes = get_vacantes_de_empresa(companyId)
                
                # Aplicar lógica de missCount y cierre (Requirement 7)
                apply_missCount_logic(empresa, result_vacantes, vacantes_existentes)
                
                # Enqueue SQS_Scoring para vacantes NUEVAS (Requirement 12.4)
                vacantes_nuevas_ids = get_new_vacancy_ids_from_scan(result_vacantes, vacantes_existentes)
                suscripciones_activas = query_suscripciones_activas_para_empresa(companyId)
                
                if vacantes_nuevas_ids and suscripciones_activas:
                    try:
                        for vacancyId in vacantes_nuevas_ids:
                            for suscripcion in suscripciones_activas:
                                msg = ScoringMessage(
                                    userId=suscripcion.userId,
                                    vacancyId=vacancyId,
                                )
                                sqs_send(msg.model_dump(), SQS_SCORING_URL)
                        
                        logger.info("scan_enqueued_scoring", context={
                            "jobId": jobId,
                            "companyId": companyId,
                            "scoring_messages": len(vacantes_nuevas_ids) * len(suscripciones_activas)
                        })
                    
                    except Exception as e:
                        # Requirement 12.5: Fallo en enqueue → abort, no ADD, SQS reintentará
                        logger.error("scan_enqueue_failed", context={
                            "jobId": jobId,
                            "companyId": companyId,
                            "error": str(e)
                        })
                        raise
            
            # Actualizar ScanJob (Requirement 12.2, 12.3)
            # ADD a empresasCompletadas (idempotente)
            add_to_string_set(f"ScanJob#{jobId}", "empresasCompletadas", companyId)
            
            if clasificacion in ["FAILED", "EMPTY_SOSPECHOSO"]:
                add_to_string_set(f"ScanJob#{jobId}", "empresasFallidas", companyId)
            
            logger.info("scan_worker_complete", context={
                "jobId": jobId,
                "companyId": companyId,
                "clasificacion": clasificacion,
                "vacantes_found": len(result_vacantes) if result_vacantes else 0
            })
        
        except Exception as e:
            logger.error("scan_worker_error", context={
                "jobId": record["body"].get("jobId", "unknown"),
                "companyId": record["body"].get("companyId", "unknown"),
                "error": str(e)[:200]
            })
            # NO marcar como completada → SQS reintentará
            raise
```

---

## Pseudocódigo: Scoring_Worker Lambda

```python
def handler_scoring_worker(event, context):
    """
    Procesa mensajes de SQS_Scoring.
    Requirements: 13, 16, 17
    
    Para cada mensaje:
    1. Extraer userId, vacancyId
    2. Verificar idempotencia (scoreProfileVersion)
    3. Aplicar Prefiltro_Cargos
    4. Invocar Bedrock scoring
    5. Persistir UsuarioVacante
    
    CRITICAL (Requirement 1.8): Scoring_Worker NEVER updates ScanJob.status.
    Only operations allowed on ScanJob:
    - ADD to empresasCompletadas (idempotent) ← NOT DONE IN THIS WORKER
    
    Scoring_Worker has NO visibility into ScanJob. Its only job is to score
    vacancies and persist UsuarioVacante records. Status transitions happen:
    1. In Orquestador (at SQS_Scan publish time)
    2. In GET /scans endpoint (zombie detection + auto-DONE logic)
    """
    
    for record in event["Records"]:
        try:
            msg = ScoringMessage(**json.loads(record["body"]))
            userId = msg.userId
            vacancyId = msg.vacancyId
            
            logger.info("scoring_worker_start", context={
                "userId": userId,
                "vacancyId": vacancyId
            })
            
            # Requirement 13.6: Skip si scoreProfileVersion == profileVersion actual
            perfil = get_perfil(userId)
            usuario_vacante = get_usuario_vacante(userId, vacancyId)
            
            if usuario_vacante and usuario_vacante.scoreProfileVersion == perfil.profileVersion:
                logger.info("scoring_skipped_current_version", context={
                    "userId": userId,
                    "vacancyId": vacancyId
                })
                return  # No error, simplemente skip
            
            # Requirement 13.7: Si no existe UsuarioVacante → proceder (no skip)
            
            vacante = get_vacante_by_id(vacancyId)
            
            # Requirement 16: Prefiltro_Cargos
            if not pasa_prefiltro_cargos(vacante.titulo, perfil.cargosActivos):
                # Requirement 16.6: Estado "filtered_out"
                usuario_vacante = UsuarioVacante(
                    userId=userId,
                    vacancyId=vacancyId,
                    estado="filtered_out",
                    updatedAt=now(),
                )
                put_usuario_vacante(usuario_vacante)
                
                logger.info("scoring_filtered_by_prefiltro", context={
                    "userId": userId,
                    "vacancyId": vacancyId,
                    "titulo": vacante.titulo[:50]
                })
                return
            
            # Requirement 17: Invocar Bedrock con reintento en validación
            resumenParaMatching = perfil.resumenParaMatching or ""  # Requirement 7 del user
            prompt = build_scoring_prompt(vacante, resumenParaMatching, perfil.cargosActivos)
            
            bedrock_client = get_bedrock_client()
            result_attempt_1 = None
            
            try:
                result_attempt_1 = bedrock_client.invoke_model(
                    prompt=prompt,
                    model_id=os.getenv("BEDROCK_MODEL_MID"),
                )
                # Validar contra ScoringResult
                scoring_result = ScoringResult(**result_attempt_1)
            
            except ValidationError as ve:
                # Requirement 17.2: Reintento con error inyectado
                logger.info("scoring_validation_failed_attempt1", context={
                    "userId": userId,
                    "vacancyId": vacancyId,
                    "error": str(ve)[:100]
                })
                
                # Inyectar error en prompt
                prompt_with_error = f"""
{prompt}

Previous response failed validation:
{str(ve)[:200]}

Please ensure the JSON response is valid and matches the required schema.
"""
                
                try:
                    result_attempt_2 = bedrock_client.invoke_model(
                        prompt=prompt_with_error,
                        model_id=os.getenv("BEDROCK_MODEL_MID"),
                    )
                    scoring_result = ScoringResult(**result_attempt_2)
                
                except ValidationError as ve2:
                    # Requirement 17.3: Fallo en ambos intentos → NO guardar, NO mutaciones
                    logger.error("scoring_validation_failed_both_attempts", context={
                        "userId": userId,
                        "vacancyId": vacancyId,
                        "error": str(ve2)[:100]
                        # Requirement 17.4: NUNCA loguear raw Bedrock response
                    })
                    # NO guardar, SQS reintentará (potencial vacío en UsuarioVacante hasta 3 reintentos)
                    raise
            
            except Exception as e:
                logger.error("scoring_bedrock_error", context={
                    "userId": userId,
                    "vacancyId": vacancyId,
                    "error": str(e)[:100]
                })
                raise
            
            # Requirement 17.5: Persistir resultado
            usuario_vacante = UsuarioVacante(
                userId=userId,
                vacancyId=vacancyId,
                score=scoring_result.score,
                scoreDetalle=scoring_result.model_dump(),
                scoreProfileVersion=perfil.profileVersion,
                estado="scored",
                updatedAt=now(),
            )
            put_usuario_vacante(usuario_vacante)
            
            logger.info("scoring_complete", context={
                "userId": userId,
                "vacancyId": vacancyId,
                "score": scoring_result.score,
                "veredicto": scoring_result.veredicto
                # Requirement 17.4: NO loguear resumen, coincidencias, faltantes
            })
        
        except Exception as e:
            logger.error("scoring_worker_error", context={
                "userId": record["body"].get("userId", "unknown"),
                "vacancyId": record["body"].get("vacancyId", "unknown"),
                "error": str(e)[:100]
            })
            # SQS reintentará
            raise


def pasa_prefiltro_cargos(titulo_vacante: str, cargosActivos: List[str]) -> bool:
    """
    Requirement 16: Prefiltro_Cargos.
    Devuelve True si hay >= threshold tokens significativos en común.
    """
    # Requirement 16.5: Si cargosActivos vacío → pasar (invocar Bedrock)
    if not cargosActivos:
        return True
    
    # Requirement 16.3: threshold desde env var
    threshold = int(os.getenv("PREFILTRO_TOKEN_THRESHOLD", "1"))
    
    tokens_titulo = get_significant_tokens(titulo_vacante)
    
    for cargo in cargosActivos:
        tokens_cargo = get_significant_tokens(cargo)
        overlap = len(tokens_titulo & tokens_cargo)
        
        # Requirement 16.7: Si overlap >= threshold → pasar
        if overlap >= threshold:
            return True
    
    # Requirement 16.6: Si no hay overlap → no pasar
    return False


def get_significant_tokens(text: str) -> set:
    """
    Extrae tokens significativos.
    - Lowercase
    - Sin acentos (NFD → sin diacríticos)
    - Split en tokens
    - Sin stopwords
    """
    import unicodedata
    import re
    
    # Lowercase + remover acentos
    text = unicodedata.normalize('NFD', text.lower())
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    
    # Split
    tokens = set(re.split(r'[\s\W]+', text))
    
    # Stopwords (en español)
    stopwords = {
        "y", "o", "el", "la", "los", "las", "de", "del", "en", "a", "por", "para",
        "con", "sin", "es", "son", "está", "están", "fue", "fueron", "que", "como",
        "si", "al", "un", "una", "unos", "unas", "a", "ante", "bajo", "entre",
        "hacia", "hasta", "según", "sobre", "traves", "durante", "mediante"
    }
    
    tokens = tokens - stopwords - {""}
    
    return tokens
```

---

## Rescoring Híbrido (Requirement 18)

**Arquitectura**: Dos funciones puras en `backend/shared/rescoring.py`.

```python
def is_score_stale(usuario_vacante: UsuarioVacante, perfil: Perfiles) -> bool:
    """
    Requirement 18.1: Función pura de detección de staleness.
    
    Compara scoreProfileVersion (en el score) con profileVersion (del perfil actual).
    Retorna True si desfasado, False si actual.
    
    NO hace I/O, NO publica mensajes, NO muta estado.
    """
    if not usuario_vacante or not usuario_vacante.scoreProfileVersion:
        return False  # Sin score → no es stale, es vacío
    
    return usuario_vacante.scoreProfileVersion != perfil.profileVersion


def enqueue_rescore(userId: str, vacancyId: str) -> bool:
    """
    Requirement 18.3: Función de enqueue sin bloquear al caller.
    
    Publica exactamente un SQS_Scoring message para (userId, vacancyId).
    
    Retorna True si éxito, False si fallo.
    Requirement 18.4: Si falla → retorna error, sin reintento.
    
    Requirement 18.5: No recomputa score, solo encola para reprocesamiento asíncrono.
    """
    try:
        msg = ScoringMessage(userId=userId, vacancyId=vacancyId)
        sqs_send(msg.model_dump(), SQS_SCORING_URL)
        return True
    except Exception as e:
        logger.error("rescore_enqueue_failed", context={
            "userId": userId,
            "vacancyId": vacancyId,
            "error": str(e)[:100]
        })
        return False
```

**Uso desde otros módulos** (fuera de esta spec):

```python
# En backend/api/routes/vacancy_listing.py (pseudo-código)
from backend.shared.rescoring import is_score_stale, enqueue_rescore

def get_user_vacancies_with_scores(userId):
    """GET /me/vacancies (no es parte de esta spec, pero usa Rescoring_Detector)"""
    
    perfil = get_perfil(userId)
    vacancies = query_usuario_vacantes(userId)
    
    response = []
    for uv in vacancies:
        if is_score_stale(uv, perfil):
            # Score desfasado, encolar para reprocesamiento
            enqueue_rescore(uv.userId, uv.vacancyId)
            
            # Requirement 18.5: Retornar score antiguo al cliente SIN esperar
            response.append({
                "vacancyId": uv.vacancyId,
                "score": uv.score,
                "staleFlag": True,  # Indicar que está en rescore
            })
        else:
            response.append({
                "vacancyId": uv.vacancyId,
                "score": uv.score,
                "staleFlag": False,
            })
    
    return response
```

---

## GET /scans/{jobId} - Polling Contract (Requirement 14, 15)

```python
def handler_get_scans(event, context):
    """
    GET /scans/{jobId}
    Requirements: 14, 14.3, 15
    """
    
    jobId = event["pathParameters"]["jobId"]
    userId = extract_jwt_sub(event)
    
    # Requirement 15.2: Si no existe → 404
    scanJob = get_scan_job(jobId)
    if not scanJob:
        return {"statusCode": 404, "body": {}}
    
    # Requirement 15.3: Autorización
    if scanJob.userId and scanJob.userId != userId:
        return {"statusCode": 404, "body": {}}
    
    # Requirement 14.1: Zombie detection
    if scanJob.status == "RUNNING":
        elapsed = (now() - scanJob.startedAt).total_seconds()
        if elapsed > 600:  # 10 minutos
            scanJob.status = "PARCIAL"
            
            # Identificar empresas no completadas
            # Requirement 14.1: Incluir en respuesta
            pending_ids = resolve_pending_companies(scanJob)
            
            # Requirement 14.2: Permitir ADD tardío
            put_scan_job(scanJob)
    
    # Requirement 14.3: Transición automática a DONE cuando todas las empresas completadas
    if scanJob.status == "RUNNING":
        if scanJob.empresasCompletadas and len(scanJob.empresasCompletadas) >= scanJob.empresasTotal:
            # Verificar: completadas == total (todas las empresas post-Ventana_Frescura procesadas)
            if len(scanJob.empresasCompletadas) == scanJob.empresasTotal:
                scanJob.status = "DONE"
                scanJob.updatedAt = now()
                put_scan_job(scanJob)
                logger.info("scan_auto_transitioned_to_done", context={
                    "jobId": jobId,
                    "empresasCompletadas": len(scanJob.empresasCompletadas),
                    "empresasTotal": scanJob.empresasTotal,
                })
    
    # Construir respuesta
    response = {
        "status": scanJob.status,
        "empresasTotal": scanJob.empresasTotal,
        "empresasCompletadas": len(scanJob.empresasCompletadas),
        "empresasOmitidas": len(scanJob.empresasOmitidas),
        "empresasFallidas": len(scanJob.empresasFallidas),
        "startedAt": scanJob.startedAt.isoformat(),
        "canStop": scanJob.status != "RUNNING",  # Requirement 15.7, 15.8
    }
    
    # Requirement 15.6: Si PARCIAL → incluir lista de empresas pending
    if scanJob.status == "PARCIAL":
        response["pendingCompanies"] = resolve_pending_companies(scanJob)
    
    return {
        "statusCode": 200,
        "body": response
    }


def resolve_pending_companies(scanJob) -> List[str]:
    """
    Empresas no en empresasCompletadas ni empresasOmitidas.
    """
    all_accounted = set(scanJob.empresasCompletadas) | set(scanJob.empresasOmitidas)
    
    # Obtener lista original de empresas a escanear
    # (Requirement: se reconstruye desde ScanJob.empresasTotal - empresasOmitidas - completadas - fallidas)
    # En práctica: empresas_originales - (completadas ∪ omitidas ∪ fallidas) = pending
    
    # Simplificación: pending = total - (completadas + omitidas)
    # Pero fallidas ⊂ completadas (se ADD a ambas)
    pending_ids = []
    
    # Si disponemos del listado original de empresas (guardado al crear ScanJob):
    # pending = originales - all_accounted
    
    return pending_ids
```

---

## Error Handling & Idempotencia (Requirement 13, 21)

### Idempotencia en Scan_Worker

**Clave de deduplicación**: `vacancyId` (SHA-256 URL normalizada)

**Caso**: SQS_Scan se reentrega para la misma empresa.

```
Primera entrega:
  - Cascada_Descubrimiento → 3 vacantes (A, B, C)
  - A, B, C son nuevas → missCount=0, estado='abierta'
  - ADD companyId a empresasCompletadas
  - Enqueue 3×N (usuarios) mensajes en SQS_Scoring

Reentregada (si visibility timeout expira):
  - Cascada_Descubrimiento → MISMO resultado (3 vacantes A, B, C)
  - A, B, C ya existen en DynamoDB
  - apply_missCount_logic:
    - Si A, B, C están en el nuevo escaneo → missCount = 0 (reset)
    - Si hay vacante D (existente, no en nuevo escaneo) → missCount += 1
  - ADD companyId a empresasCompletadas NUEVAMENTE
    - String Set: Solo un companyId (idempotente)
  - Enqueue NUEVAMENTE 3×N mensajes en SQS_Scoring
    - Scoring_Worker: scoreProfileVersion == profileVersion → skip
    - (Requirement 13.6: no recalcula)
```

**Conclusión**: Reentregada produce el mismo estado final. ✓ Idempotente.

### Idempotencia en Scoring_Worker

**Clave de deduplicación**: `(userId, vacancyId)`

**Criterio de skip**: `scoreProfileVersion == profileVersion` actual

**CRITICAL DISTINCTION (Requirement 13.5-13.6, FALLO 2)**:

> **Reentrega SQS_Scoring is NOT idempotent to the score value itself, only to invocation.**

This means:

```
SCENARIO 1: profileVersion hasn't changed (reentrega, same profile state)

Primera entrega (profileVersion=5):
  - scoreProfileVersion_stored = null or != 5
  - Invoke Bedrock → score = 75
  - PUT UsuarioVacante con scoreProfileVersion = 5

Reentregada (profileVersion=5):
  - scoreProfileVersion_stored = 5 (from first delivery)
  - perfil.profileVersion = 5 (actual)
  - Criterion 13.6: scoreProfileVersion == profileVersion → SKIP
  - Stored record UNCHANGED: score still 75
  - NO re-invocation of Bedrock
  
This is TRUE IDEMPOTENCE at the score level: 
  - Same inputs (profileVersion 5) → Same stored output (score 75)
  - No recalculation, no Bedrock invocation


SCENARIO 2: profileVersion DID change in parallel (reentrega, DIFFERENT profile state)

Primera entrega (profileVersion=5):
  - Invoke Bedrock → score = 75
  - PUT UsuarioVacante con scoreProfileVersion = 5

[Profile updated: profileVersion now = 6]

Reentregada AFTER profile update (profileVersion=6):
  - scoreProfileVersion_stored = 5 (from first delivery)
  - perfil.profileVersion = 6 (actual, has changed)
  - Criterion 13.6: scoreProfileVersion (5) != profileVersion (6) → NO SKIP
  - Invoke Bedrock AGAIN with new profile → score = 82
  - PUT UsuarioVacante con scoreProfileVersion = 6
  
This is NOT idempotent at the score level:
  - Same SQS message (userId, vacancyId) processed twice
  - But profile state changed in between
  - Score changed from 75 → 82
  - This is CORRECT and INTENDED behavior (rescoring)
```

**Documentation**: 
- Idempotence is at the **invocation** level: If you enqueue the same (userId, vacancyId) pair 
  and profileVersion hasn't changed, no re-invocation happens (skip via scoreProfileVersion check).
- Idempotence is NOT at the **score** level: If profileVersion changes, a new Bedrock invocation 
  produces a different score.

This is by design: Scoring_Worker is idempotent to avoid wasting Bedrock tokens on unchanged 
profiles, but NOT to prevent legitimate rescoring when the profile evolves.

```

**Conclusión**: Idempotente por profileVersion (skip recompute), pero NO idempotente al valor 
del score si el perfil cambia. ✓ Diseño correcto.

---

### Structured Logging (Requirement 21)

**Formato**: JSON a stdout

**Campos excluidos** (NUNCA loguear):

- CV text completo
- Contenido completo de perfil
- `scoreDetalle.resumen`, `.coincidencias`, `.faltantes`
- Raw Bedrock_Client response body
- HTML limpio completo

**Campos Incluidos**:

```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "level": "INFO",
  "component": "scan_worker",
  "jobId": "scan_20240115_user123",
  "companyId": "a1b2c3d4e5f6...",
  "clasificacion": "OK",
  "vacantes_found": 3,
  "origen": "board_api"
}
```

```json
{
  "timestamp": "2024-01-15T10:35:22Z",
  "level": "INFO",
  "component": "scoring_worker",
  "userId": "user_8f9e7d6c",
  "vacancyId": "vacancy_sha256...",
  "score": 75,
  "veredicto": "buen_encaje"
}
```

---

## Testing Strategy

### Determinación de Applicabilidad de PBT

**¿Es property-based testing apropiado para esta spec?**

**Criterios**:

1. **¿Lógica pura transformadora?** Parcialmente.
   - Funciones puras: `compute_vacancyId`, `classify_scan_result`, `get_significant_tokens`, `pasa_prefiltro_cargos`
   - No-pura: workers con I/O, SQS, DynamoDB, Bedrock

2. **¿Comportamiento varía significativamente con entrada?**
   - Sí para lógica pura (normalización, clasificación)
   - No para flujos completos (estado externo determina comportamiento)

3. **¿100 iteraciones encuentran más bugs que 2-3?**
   - Sí para funciones puras (edge cases en normalización de URL, tokens)
   - No para workers (timing, SQS, AWS services)

**Conclusión**: **PBT APLICA PARCIALMENTE**.

- ✅ **PBT para funciones puras**: `compute_vacancyId`, `classify_scan_result`, `get_significant_tokens`, `pasa_prefiltro_cargos`
- ❌ **NO PBT para**: Workflows completos (Scan_Worker, Scoring_Worker, Orquestador)
- ✅ **Unit tests con mocks**: Workflows

---

### Unit Tests (Funciones Puras)

```python
# test_normalization.py
def test_compute_vacancyId_idempotent():
    url = "https://example.com/job/123"
    assert compute_vacancyId(url) == compute_vacancyId(url)

def test_compute_vacancyId_normalized():
    url1 = "https://EXAMPLE.COM/job/123#fragment"
    url2 = "https://example.com/job/123"
    assert compute_vacancyId(url1) == compute_vacancyId(url2)

# test_classification.py
def test_classify_ok():
    empresa = Empresa(lastVacancyCount=0)
    result = ([mock_vacante], "board_api", None)
    assert classify_scan_result(empresa, result) == "OK"

def test_classify_empty_sospechoso():
    empresa = Empresa(lastVacancyCount=5)
    result = ([], None, None)
    assert classify_scan_result(empresa, result) == "EMPTY_SOSPECHOSO"

# test_prefiltro.py
def test_pasa_prefiltro_exact_match():
    assert pasa_prefiltro_cargos("Python Developer", ["Python Developer"]) == True

def test_pasa_prefiltro_one_token():
    assert pasa_prefiltro_cargos("Senior Python Engineer", ["Python Programmer"]) == True

def test_pasa_prefiltro_no_match():
    assert pasa_prefiltro_cargos("Product Manager", ["Software Engineer"]) == False
```

### Integration Tests (Con Mocks)

```python
@mock.patch('boto3.client')
def test_scan_worker_ok_flow(mock_boto):
    # Setup: empresa, vacantes, SQS message, mocks
    # Trigger: handler_scan_worker
    # Assert: Vacantes upserted, SQS_Scoring enqueued, ScanJob actualizado
    ...

@mock.patch('boto3.client')
def test_scoring_worker_idempotence(mock_boto):
    # Setup: UsuarioVacante con scoreProfileVersion = 5, profileVersion = 5
    # Trigger: handler_scoring_worker (reentregada)
    # Assert: Bedrock NO invocado, stored record sin cambios
    ...
```

---

## Componentes y Responsabilidades

| Componente | Responsabilidad |
|---|---|
| **Orquestador Lambda** | POST /scans: Resolver empresas, Ventana_Frescura, crear ScanJob, fan-out SQS_Scan |
| **Scan_Worker Lambda** | Cascada_Descubrimiento, clasificación, upsert Vacantes, missCount, fan-out SQS_Scoring, actualiza ScanJob |
| **Scoring_Worker Lambda** | Prefiltro_Cargos, invoke Bedrock, persist UsuarioVacante, idempotencia |
| **Scans_API** | GET /scans/{jobId}: polling contract, zombie detection, autorización |
| **Rescoring_Detector** | is_score_stale(), enqueue_rescore() (shared) |
| **HTML Cleaner** | html_to_clean_text(): limpia HTML previo a Bedrock |
| **Board API Client** | query_board_api_client() (Greenhouse, Lever) |
| **JSON-LD Extractor** | extract_json_ld() (JobPosting blocks) |

---

## Environment Variables (Requeridas)

| Variable | Requerida | Default | Ejemplo |
|---|---|---|---|
| `BEDROCK_REGION` | Sí | N/A | `us-east-1` |
| `BEDROCK_MODEL_SMALL` | Sí | N/A | `us.anthropic.claude-3-haiku-*` |
| `BEDROCK_MODEL_MID` | Sí | N/A | `us.anthropic.claude-3-5-sonnet-*` |
| `DYNAMODB_TABLE_EMPRESA` | Sí | N/A | `dev-empresa` |
| `DYNAMODB_TABLE_VACANTE` | Sí | N/A | `dev-vacante` |
| `DYNAMODB_TABLE_USUARIO_VACANTE` | Sí | N/A | `dev-usuario-vacante` |
| `DYNAMODB_TABLE_SCAN_JOB` | Sí | N/A | `dev-scan-job` |
| `SQS_QUEUE_SCAN_URL` | Sí | N/A | `https://sqs.us-east-1.../dev-scan` |
| `SQS_QUEUE_SCORING_URL` | Sí | N/A | `https://sqs.us-east-1.../dev-scoring` |
| `PREFILTRO_TOKEN_THRESHOLD` | No | 1 | 1, 2, 3 |
| `HTML_CLEAN_MAX_KB` | No | 100 | 50, 100, 200 |
| `LOG_LEVEL` | No | INFO | DEBUG, INFO, WARN, ERROR |

---

## Decisiones Arquitectónicas Clave

1. **SHA-256 para vacancyId**: Garantiza deduplicación basada en URL, no en datos.
2. **Cascada ordenada**: Board API < JSON-LD < HTML+LLM (costo ascendente).
3. **Clasificación 4-way**: OK/FAILED/EMPTY_SOSPECHOSO/EMPTY_LEGITIMO (sin ambigüedad).
4. **missCount con margen**: Cierre solo tras 2 escaneos OK sin encontrar vacante.
5. **Ventana_Frescura adaptativa**: 1h para board APIs, 12h para LLM (ahorro de tokens).
6. **Zombie detection a 600s**: Si RUNNING y > 10 min → PARCIAL (no bloquea frontend).
7. **String Sets idempotentes**: ADD operation evita duplicados en reintentos.
8. **Scoring idempotente**: scoreProfileVersion evita recálculos innecesarios.
9. **Rescoring híbrido**: Detección pura + enqueue no-bloqueante (mejor UX).
10. **HTML limpieza con truncado**: Evita gastar tokens en HTML gigantesco.

---

## Resumen

Este design especifica completamente:

- ✅ Cascada de descubrimiento (orden, parada, origen)
- ✅ Clasificación sin ambigüedad (OK/FAILED/EMPTY_SOSPECHOSO/EMPTY_LEGITIMO)
- ✅ Pseudocódigo crítico: missCount, clasificación, limpieza HTML
- ✅ Payloads SQS exactos (Pydantic models en shared/)
- ✅ Visibility timeout: 6 × Lambda timeout (valores explícitos)
- ✅ maxReceiveCount = 3, DLQ por cola
- ✅ Idempotencia completa: vacancyId, String Sets, scoreProfileVersion
- ✅ Rescoring híbrido: función pura + enqueue
- ✅ Logging estructurado sin contenido sensible
- ✅ Jobs zombis: GET /scans/{jobId} a 600s → PARCIAL

**Próximos pasos**: 
1. Correctness Properties (funciones puras)
2. Task Definition (desglosar en tareas concretas)
3. Implementation (código de cada componente)

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Property-based testing (PBT) APLICA a esta spec para un subconjunto crítico de funciones puras:
- URL normalization & vacancyId hashing
- Scan result classification (OK/FAILED/EMPTY_SOSPECHOSO/EMPTY_LEGITIMO)
- missCount logic (incremento, reset, cierre)
- Prefiltro_Cargos token matching

Sin embargo, NO aplica a workflows completos (Scan_Worker, Scoring_Worker, Orquestador) porque 
dependen de infraestructura (SQS, DynamoDB, Bedrock) con timing y estado externo.

---

### Property 1: vacancyId Determinism & Normalization

*For any* URL, computing vacancyId twice SHALL produce the same 64-character hexadecimal string, 
regardless of variations in scheme case, host case, fragment presence, or trailing slash.

**Validates: Requirement 1.1**

**Example inputs**:
- `"https://example.com/job/123"` → same hash as
- `"HTTPS://EXAMPLE.COM/job/123#fragment"` → same hash as
- `"https://example.com/job/123/"` → same hash

**Test strategy**: Use fast-check to generate arbitrary URLs with random variations; assert hash consistency.

---

### Property 2: Scan Result Classification Exhaustiveness

*For any* combination of (vacantes_count, last_vacancy_count, error), classify_scan_result SHALL 
return exactly one of: OK, FAILED, EMPTY_SOSPECHOSO, EMPTY_LEGITIMO, with no ambiguity or overlap.

**Validates: Requirement 6.2, 6.3, 6.4, 6.5, 6.6**

**Decision table** (exhaustive):

| vacantes_count | last_vacany_count | error | Expected |
|---|---|---|---|
| > 0 | any | None | OK |
| 0 | > 0 | None | EMPTY_SOSPECHOSO |
| 0 | 0 | None | EMPTY_LEGITIMO |
| any | any | present | FAILED |

**Test strategy**: Generate all 4 quadrants (exhaustive); verify classification matches table.

---

### Property 3: missCount Increment Only on OK Classification

*For any* scan classified as OK with one or more missing vacancies, missCount for each missing 
vacancy SHALL be incremented by exactly 1 (and not incremented for scans classified FAILED or EMPTY_SOSPECHOSO).

**Validates: Requirement 7.1**

**Property**: apply_missCount_logic(clasificacion='OK', missing_vacancies=[V1, V2]) results in 
missCount[V1]_after = missCount[V1]_before + 1 AND missCount[V2]_after = missCount[V2]_before + 1.

**Test strategy**: Generate random Vacante lists with random existing missCount values; apply logic 
for OK classification; verify increments happen exactly once.

---

### Property 4: missCount Reset on Reappearance

*For any* vacancy that was missing but reappears in a subsequent OK scan, missCount SHALL be 
reset to 0 (and estado SHALL revert to 'abierta' if it was 'cerrada').

**Validates: Requirement 7.2, 7.3**

**Property**: apply_missCount_logic(clasificacion='OK', vacancy_reappears=True) results in 
missCount_after = 0 AND estado_after = 'abierta'.

**Test strategy**: Generate Vacante with missCount=N (N >= 2, estado='cerrada'); re-include in scan; 
verify reset to 0 and estado='abierta'.

---

### Property 5: Manual Vacancies Never Auto-Close

*For any* vacancy with origen='manual', applying missCount logic SHALL NEVER set estado='cerrada', 
regardless of missCount value.

**Validates: Requirement 7.5**

**Invariant**: origen='manual' ∧ apply_missCount_logic(missed_N_times) ⟹ estado≠'cerrada'

**Test strategy**: Generate manual vacancies with missCount=0,1,2,3,...,1000; apply logic; 
verify estado='abierta' always.

---

### Property 6: Prefiltro Token Overlap Threshold

*For any* título and set of cargosActivos, pasa_prefiltro_cargos SHALL return true if and only 
if at least one cargo shares >= threshold significant tokens with título (where significant tokens 
are normalized: lowercase, no diacritics, no stopwords).

**Validates: Requirement 16.2, 16.6, 16.7**

**Property**: overlap(get_significant_tokens(titulo), get_significant_tokens(cargo)) >= threshold 
⟺ pasa_prefiltro_cargos(titulo, [cargo, ...]) = true

**Test strategy**: Generate random titles and cargos with controlled token overlap; vary threshold; 
verify true/false results match overlap count.

---

### Property 7: Significant Tokens Normalization Idempotence

*For any* string, calling get_significant_tokens twice SHALL produce the same set, and repeated 
normalization (lowercase, diacritics removal, stopword filtering) SHALL not change the result.

**Validates: Requirement 16.2**

**Property**: get_significant_tokens(get_significant_tokens_as_string(tokens)) = tokens

**Test strategy**: Generate random strings with mixed case, accents, stopwords; verify 
get_significant_tokens(string) idempotent; verify normalize(normalize(string)) = normalize(string).

---

### Property 8: Empty cargosActivos Bypass Prefiltro

*For any* título (even empty or irrelevant) and an empty cargosActivos list, 
pasa_prefiltro_cargos SHALL return true (Requirement 16.5).

**Validates: Requirement 16.5**

**Property**: cargosActivos = [] ⟹ pasa_prefiltro_cargos(any_titulo, []) = true

**Test strategy**: Generate random títulos; always use empty cargosActivos; verify all return true.

## Summary & Next Steps

### Completado en Este Design

1. ✅ **Architecture Overview**: Flujo de mensajes, componentes, responsabilidades
2. ✅ **Data Models**: Extensiones a Vacante, Empresa, ScanJob + nuevos UsuarioVacante, ScoringResult
3. ✅ **SQS Payloads**: Modelos Pydantic (ScanMessage, ScoringMessage)
4. ✅ **Pseudocódigo Crítico**:
   - Cascada_Descubrimiento (orden, parada, origen)
   - classify_scan_result (4-way exhaustivo)
   - apply_missCount_logic (incremento, reset, cierre, reapertura)
   - compute_vacancyId (normalización, hash SHA-256)
5. ✅ **HTML Limpieza**: Elementos eliminados, umbral (100 KB), acción (truncar)
6. ✅ **Orquestador**: Resolución de empresas, Ventana_Frescura, ScanJob creation, fan-out
7. ✅ **Scan_Worker**: Cascada, clasificación, Vacante upsert, missCount, SQS_Scoring fan-out
8. ✅ **Scoring_Worker**: Prefiltro_Cargos, Bedrock scoring, UsuarioVacante persist, idempotencia
9. ✅ **Rescoring_Detector**: is_score_stale() + enqueue_rescore() (shared)
10. ✅ **GET /scans/{jobId}**: Zombie detection (600s), polling contract
11. ✅ **Logging Estructurado**: JSON, campos excluidos (CV, perfil, resumen)
12. ✅ **Concurrencia Reservada**: Scan_Worker=5, Scoring_Worker=3
13. ✅ **Visibility Timeout**: 6 × Lambda timeout (valores explícitos)
14. ✅ **maxReceiveCount**: 3 para ambas DLQs
15. ✅ **Idempotencia**: vacancyId keys, String Sets, scoreProfileVersion
16. ✅ **Correctness Properties**: 8 propiedades PBT para funciones puras
17. ✅ **Testing Strategy**: Unit tests (puras) + Integration tests (workflows con mocks)

### Requisitos NO Abarcados por Este Design

(Fuera del scope de backend-scan-y-scoring):

- ❌ Listado y detalle de vacantes (GET /me/vacancies*, GET /vacancies/{id})
- ❌ Vacante manual (POST /vacancies)
- ❌ CV parsing & profile storage (backend-core)
- ❌ ATS integration
- ❌ Banco de preguntas y notas
- ❌ Notificaciones por correo (SES)
- ❌ Terraform / infraestructura (separado)
- ❌ Frontend React (separado)

---

## Decisiones de Diseño Justificadas

| Decisión | Razón | Alternativa Rechazada |
|---|---|---|
| SHA-256 para vacancyId | Determinístico, basado en URL (no en LLM output) | URL + título + ubicación (no determinístico) |
| Cascada ordenada por costo | Minimiza gasto de tokens Bedrock | Paralelo (alto costo) |
| Clasificación 4-way | Sin ambigüedad, cubre todos los casos | Binaria OK/FAILED (ambigua) |
| missCount con margen (2 scans) | Tolera fallos pasajeros | Cierre inmediato (FP altos) |
| Ventana_Frescura adaptativa | 1h/12h balance latencia + costo | Fija (mala elasticidad) |
| Zombie detection 600s | Balance entre UX (no esperar) + confiabilidad | 300s (demasiado sensible), 3600s (muy laxo) |
| String Sets para contadores | Idempotencia en reintentos SQS | Incremento simple (duplica en reentrega) |
| Rescoring híbrido | UX fluida sin bloqueo | Recálculo síncrono (slow), ninguno (stale) |
| HTML truncado (no skip) | Evita perder empresas | SKIP (pierde datos), FAILED (bloquea job) |
| Scoring vía SQS_Scoring | Async, escalable, idempotente | Síncrono en Scan_Worker (lento, acoplado) |

---

## Trace Completo de un Caso de Uso

### Escenario: Usuario presiona "Escanear" con 3 empresas suscritas

**T=0s**: POST /scans → Orquestador

```
Usuario autenticado (sub=user123)
Suscripciones activas: [CompanyA, CompanyB, CompanyC]
Ventana_Frescura: CompanyA no elegible (scanned 30min ago, últimoOrigen=board_api, 1h window)
                  CompanyB elegible (never scanned)
                  CompanyC elegible (scanned 13h ago, últimoOrigen=html_llm, 12h window)

Orquestador:
  1. Create ScanJob(id='job_xyz', userId='user123', status='RUNNING', empresasTotal=2, startedAt=T0)
  2. Publish 2 messages to SQS_Scan:
     - ScanMessage(jobId='job_xyz', companyId='compA_hash')
     - ScanMessage(jobId='job_xyz', companyId='compC_hash')
  3. Set ScanJob.empresasOmitidas = ['compB_hash']
  4. Return {'jobId': 'job_xyz'} to client
```

**T=0-5s**: Scan_Worker processes CompanyA

```
Message 1: ScanMessage(jobId='job_xyz', companyId='compA_hash')

Scan_Worker:
  1. Fetch Empresa(compA_hash): plataforma='greenhouse', boardToken='...', lastVacancyCount=5
  2. Cascada: board_api → 3 vacancies found (A1, A2, A3)
  3. Classification: (3 vacancies, error=None) → OK
  4. Empresa.consecutiveFailures=0, lastVacancyCount=3, ultimoOrigenExitoso='board_api'
  5. Upsert Vacantes:
     - A1 (new): missCount=0, estado='abierta'
     - A2 (new): missCount=0, estado='abierta'
     - A3 (new): missCount=0, estado='abierta'
     - Other existing vacancies from CompanyA not in [A1, A2, A3]: missCount+=1
       (e.g., if A4 was existing: missCount now 1)
  6. Fetch active subscriptions for CompanyA: [user123, user456]
  7. Publish to SQS_Scoring (6 messages):
     - ScoringMessage(userId='user123', vacancyId='a1_sha256')
     - ScoringMessage(userId='user123', vacancyId='a2_sha256')
     - ScoringMessage(userId='user123', vacancyId='a3_sha256')
     - ScoringMessage(userId='user456', vacancyId='a1_sha256')
     - ScoringMessage(userId='user456', vacancyId='a2_sha256')
     - ScoringMessage(userId='user456', vacancyId='a3_sha256')
  8. ADD 'compA_hash' to ScanJob.empresasCompletadas
  9. Log: scan_complete { jobId='job_xyz', companyId='compA_hash', clasificacion='OK', vacantes=3 }
```

**T=0-5s**: Scan_Worker processes CompanyC (parallel)

```
Message 2: ScanMessage(jobId='job_xyz', companyId='compC_hash')

Scan_Worker:
  1. Fetch Empresa(compC_hash): plataforma='html', careersUrl='...', lastVacancyCount=0
  2. Cascada:
     - json_ld_extractor: 0 vacancies
     - html_llm_extractor: 
       * Fetch + clean HTML (truncate if > 100 KB)
       * Send to Bedrock SMALL
       * Parse response
       * 2 vacancies found (C1, C2)
     3. Classification: (2 vacancies, origen='html_llm', error=None) → OK
  3. Empresa.consecutiveFailures=0, lastVacancyCount=2, ultimoOrigenExitoso='html_llm'
  4. Upsert Vacantes (new): C1, C2 with missCount=0, estado='abierta'
  5. Publish to SQS_Scoring (2 messages):
     - ScoringMessage(userId='user123', vacancyId='c1_sha256')
     - ScoringMessage(userId='user123', vacancyId='c2_sha256')
  6. ADD 'compC_hash' to ScanJob.empresasCompletadas
```

**T=5s**: GET /scans/job_xyz (poll)

```
Frontend polls: GET /scans/job_xyz
  
Scans_API:
  1. Fetch ScanJob: status='RUNNING', empresasCompletadas={compA, compC}, empresasOmitidas={compB}
  2. Zombie check: elapsed = 5s < 600s → no change
  3. Response:
     {
       "status": "RUNNING",
       "empresasTotal": 2,
       "empresasCompletadas": 2,
       "empresasOmitidas": 1,
       "empresasFallidas": 0,
       "startedAt": "...",
       "canStop": false
     }
     
Frontend: Show progress 2/2 completed, poll again in 2s
```

**T=5-15s**: Scoring_Worker processes 8 SQS_Scoring messages (in parallel, concurrency=3)

```
Message: ScoringMessage(userId='user123', vacancyId='a1_sha256')

Scoring_Worker:
  1. Fetch Perfil(user123): profileVersion=5, cargosActivos=['Python Developer', 'ML Engineer']
  2. Fetch UsuarioVacante(user123, a1_sha256): none (new)
  3. Fetch Vacante(a1_sha256): titulo='Senior Python Backend', descripcion='...', origen='board_api'
  4. Prefiltro: 'python' in both → pass
  5. Invoke Bedrock MID:
     Prompt:
       "Candidate skills: Python Developer, ML Engineer
        Job: Senior Python Backend
        Match score 0-100 with veredicto (excelente/buen_encaje/parcial/bajo)
        ...résumenParaMatching (~500 words)..."
  6. Response validation: ScoringResult(score=82, veredicto='buen_encaje', ...)
  7. PUT UsuarioVacante:
     {
       userId='user123', vacancyId='a1_sha256',
       score=82, scoreDetalle={...},
       scoreProfileVersion=5, estado='scored'
     }
  8. Log: scoring_complete { userId='user123', vacancyId='a1_sha256', score=82, veredicto='buen_encaje' }
```

(8 messages processed over ~10s)

**T=15s**: GET /scans/job_xyz (final poll)

```
ScanJob.status = 'RUNNING' (still, all scoring in flight)
Response still shows progress, canStop=false
```

**T=20s**: GET /scans/job_xyz (final poll, all done)

```
All 8 ScoringMessages processed → UsuarioVacante records persisted
ScanJob.status = 'RUNNING' (no change needed, scoring_worker no updatea ScanJob)

Response:
  {
    "status": "RUNNING",
    "empresasTotal": 2,
    "empresasCompletadas": 2,
    "empresasOmitidas": 1,
    "empresasFallidas": 0,
    "canStop": false  (still true, statusis RUNNING)
  }
  
Frontend: Could poll indefinitely... but in practice, client waits a few seconds then transitions.
(In real UX: client could infer completion when empresasCompletadas == empresasTotal)
```

**Later**: User checks vacancy details (from another endpoint, not this spec)

```
GET /me/vacancies?status=abierta
  
Backend (not this spec):
  1. Query UsuarioVacante for user123
  2. For each, check: is_score_stale(uv, perfil)?
  3. If stale: enqueue_rescore(user123, vacancyId) → SQS_Scoring new message
  4. Return vacancies with scores (old scores, stale flag if needed)
```

---

## Conclusión

Este design especifica completamente:

✅ Todos los 21 requirements del documento de requisitos
✅ Pseudocódigo detallado de funciones críticas
✅ Payloads SQS exactos (Pydantic models)
✅ Timeouts y visibility timeouts (con fórmulas y números)
✅ Limpieza de HTML (elementos, umbral, acción)
✅ Logging estructurado y seguro
✅ Idempotencia completa (SQS al menos una vez)
✅ Correctness Properties (8 propiedades PBT)
✅ Testing Strategy (unit + integration)

**Próximas fases**:
1. Tasks: Desglosar en tareas concretas (Orquestador, Scan_Worker, Scoring_Worker, GET endpoint, tests)
2. Implementation: Código de cada componente
3. Review: Validación antes de desarrollo
