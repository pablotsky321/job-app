"""
Companies and subscriptions management endpoints.

Provides:
- GET /companies: List all companies in shared catalog (paginated)
- POST /companies: Add a new company to catalog
- GET /me/companies: List user's subscriptions
- PUT /me/companies/{companyId}: Toggle subscription active/inactive

All user-specific endpoints (/me/companies*) require authentication and extract
userId from JWT via Depends(get_current_user_id).

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1-7.8, 8.1-8.8, 9.1-9.8
"""

from typing import List, Optional
from datetime import datetime, timezone
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
import boto3

from backend.shared.logging_config import get_contextual_logger
from backend.shared.validators import (
    normalize_url,
    compute_company_id,
    detect_platform_hostname_only,
    validate_empresa_url,
)
from backend.shared.db import (
    query_by_pk,
    put_item,
    update_item,
    scan_items,
    TABLES,
    _get_dynamodb_client,
)
from backend.shared.errors import (
    ValidationError as ValidationErrorException,
    PlatformDetectionFailed,
    CompanyAlreadyExists,
    CompanyNotFound,
    SubscriptionNotFound,
)
from backend.api.routes.auth import get_current_user_id
from backend.api.models.requests import AddCompanyRequest, ToggleSubscriptionRequest

# Initialize logger
logger = get_contextual_logger(__name__)

# Create two routers: one for public companies, one for user subscriptions
companies_router = APIRouter(prefix="/companies", tags=["companies"])
subscriptions_router = APIRouter(prefix="/me/companies", tags=["subscriptions"])


# ============================================================================
# Response Models
# ============================================================================


class CompanyListItem(BaseModel):
    """Company item in list response."""

    companyId: str
    nombre: str
    careersUrl: str
    plataforma: str
    lastScannedAt: Optional[str] = None
    lastScanStatus: Optional[str] = None
    lastVacancyCount: int
    consecutiveFailures: int


class CompaniesListResponse(BaseModel):
    """Response for GET /companies."""

    companies: List[CompanyListItem]
    total: int
    hasMore: bool


class CompanyCreateResponse(BaseModel):
    """Response for POST /companies (201 Created)."""

    companyId: str
    nombre: str
    plataforma: str
    createdAt: str


class SubscriptionItem(BaseModel):
    """Company subscription item in user's list."""

    companyId: str
    nombre: str
    plataforma: str
    addedAt: str
    lastScannedAt: Optional[str] = None
    lastScanStatus: Optional[str] = None
    lastVacancyCount: int
    consecutiveFailures: int


class SubscriptionListResponse(BaseModel):
    """Response for GET /me/companies."""

    subscriptions: List[SubscriptionItem]


class SubscriptionUpdateResponse(BaseModel):
    """Response for PUT /me/companies/{companyId}."""

    companyId: str
    activa: bool
    updatedAt: str


# ============================================================================
# GET /companies - List all companies (paginated)
# ============================================================================


@companies_router.get("", response_model=CompaniesListResponse)
async def list_companies(
    limit: int = Query(20, ge=10, le=100, description="Page size (10-100, default 20)"),
    offset: int = Query(0, ge=0, description="Page offset (default 0)"),
):
    """
    List all companies in the shared catalog.

    Endpoint: GET /companies
    Auth: Not required

    Query Parameters:
        - limit (int): Page size, 10-100, default 20
        - offset (int): Page offset, default 0

    Response (HTTP 200):
        - companies: List of company objects
        - total: Total number of companies
        - hasMore: Boolean indicating if more results exist

    Logic:
    1. Scan Empresas table (all companies)
    2. Sort case-insensitively by nombre
    3. Return raw stored fields only (no derived/computed flags)
    4. Log retrieval operation

    Company fields returned:
        - companyId, nombre, careersUrl, plataforma
        - lastScannedAt, lastScanStatus, lastVacancyCount, consecutiveFailures

    Requirements:
    - 6.1: Paginate listing
    - 6.2: Sort by nombre case-insensitively
    - 6.3: Return raw stored fields only
    - 6.4: Return {"companies", "total", "hasMore"}
    - 6.5: No auth required
    """
    logger.info(
        "list_companies_start",
        context={
            "limit": limit,
            "offset": offset,
        },
    )

    try:
        # Scan all companies
        items = scan_items("empresas")

        # Sort case-insensitively by nombre
        items.sort(key=lambda x: x.get("nombre", "").lower())

        total = len(items)
        paginated_items = items[offset : offset + limit]

        # Convert to response format
        companies = []
        for item in paginated_items:
            company_item = CompanyListItem(
                companyId=item.get("companyId"),
                nombre=item.get("nombre"),
                careersUrl=item.get("careersUrl"),
                plataforma=item.get("plataforma"),
                lastScannedAt=item.get("lastScannedAt"),
                lastScanStatus=item.get("lastScanStatus"),
                lastVacancyCount=item.get("lastVacancyCount", 0),
                consecutiveFailures=item.get("consecutiveFailures", 0),
            )
            companies.append(company_item)

        has_more = (offset + limit) < total

        logger.info(
            "list_companies_success",
            context={
                "total": total,
                "returned": len(companies),
                "has_more": has_more,
            },
        )

        return CompaniesListResponse(
            companies=companies,
            total=total,
            hasMore=has_more,
        )

    except Exception as e:
        logger.error(
            "list_companies_error",
            context={
                "error": str(e),
            },
        )
        raise


# ============================================================================
# POST /companies - Add a new company to catalog
# ============================================================================


@companies_router.post("", response_model=CompanyCreateResponse, status_code=201)
async def add_company(request: AddCompanyRequest):
    """
    Add a new company to the shared catalog.

    Endpoint: POST /companies
    Auth: Not required

    Request Body:
        - careersUrl (str): Company careers page URL (http/https)

    Response (HTTP 201):
        - companyId: SHA-256 hash of normalized URL
        - nombre: Extracted company name
        - plataforma: Detected platform (greenhouse, lever, html)
        - createdAt: Timestamp

    Error Responses:
        - HTTP 400: Malformed URL or platform detection failed
        - HTTP 409: Company already exists (duplicate URL)

    Logic:
    1. Validate careersUrl via validate_empresa_url (400 if invalid)
    2. Normalize URL and compute companyId (SHA-256 hash)
    3. Detect platform using ONLY hostname check (detect_platform_hostname_only)
    4. Check if companyId already exists (409 if found)
    5. Extract company nombre from URL domain (domain.com → "domain")
    6. Create Empresas entry with lastScannedAt=null, lastScanStatus=null, etc.
    7. Return 201 with companyId, nombre, plataforma, createdAt

    Requirements:
    - 7.1: Accept careersUrl
    - 7.2: Validate URL (400 on invalid)
    - 7.3: Normalize URL via normalize_url
    - 7.4: Compute companyId via compute_company_id (SHA-256)
    - 7.5: Detect platform via detect_platform_hostname_only (pure hostname check, no HTTP)
    - 7.6: Map platform detection failure to 400 platform_detection_failed
    - 7.7: Return 409 company_already_exists if hash exists
    - 7.8: Return 201 with companyId, nombre, plataforma, createdAt
    """
    logger.info(
        "add_company_start",
        context={},
    )

    try:
        # Step 1: Validate URL
        is_valid, error_msg = validate_empresa_url(request.careersUrl)
        if not is_valid:
            logger.warning(
                "add_company_validation_failed",
                context={
                    "reason": error_msg,
                },
            )
            raise ValidationErrorException(
                message="Invalid company URL",
                details=error_msg,
            )

        # Step 2: Normalize URL and compute company ID
        normalized_url = normalize_url(request.careersUrl)
        company_id = compute_company_id(normalized_url)

        # Step 3: Detect platform (pure hostname check)
        try:
            plataforma = detect_platform_hostname_only(normalized_url)
        except ValueError as e:
            logger.warning(
                "add_company_platform_detection_failed",
                context={
                    "error": str(e),
                },
            )
            raise PlatformDetectionFailed(details=str(e))

        # Step 4: Check if company already exists
        existing = query_by_pk("empresas", "companyId", company_id)

        if existing:
            logger.warning(
                "add_company_already_exists",
                context={
                    "company_id": company_id,
                },
            )
            raise CompanyAlreadyExists(company_id=company_id)

        # Step 5: Extract company nombre from URL domain
        parsed = urlparse(normalized_url)
        domain = parsed.netloc.lower()
        # Extract main domain (e.g., "example.com" → "example")
        nombre = domain.split(".")[0].title()

        # Step 6: Create Empresas entry
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        company_item = {
            "companyId": company_id,
            "nombre": nombre,
            "careersUrl": normalized_url,
            "plataforma": plataforma,
            "lastScannedAt": None,
            "lastScanStatus": None,
            "lastVacancyCount": 0,
            "consecutiveFailures": 0,
            "createdAt": created_at,
        }

        put_item("empresas", company_item)

        logger.info(
            "add_company_success",
            context={
                "company_id": company_id,
                "nombre": nombre,
                "plataforma": plataforma,
            },
        )

        # Step 7: Return response
        return CompanyCreateResponse(
            companyId=company_id,
            nombre=nombre,
            plataforma=plataforma,
            createdAt=created_at,
        )

    except (ValidationErrorException, PlatformDetectionFailed, CompanyAlreadyExists):
        raise
    except Exception as e:
        logger.error(
            "add_company_error",
            context={
                "error": str(e),
            },
        )
        raise


# ============================================================================
# GET /me/companies - List user's subscriptions
# ============================================================================


@subscriptions_router.get("", response_model=SubscriptionListResponse)
async def list_user_subscriptions(
    user_id: str = Depends(get_current_user_id),
):
    """
    List all active companies the user is subscribed to.

    Endpoint: GET /me/companies
    Auth: Required (JWT)

    Response (HTTP 200):
        - subscriptions: List of subscription objects

    Logic:
    1. Query Suscripciones table by userId
    2. Filter for activa=true only
    3. Left-join with Empresas to get company details
    4. Sort by addedAt descending (most recent first)
    5. Return raw stored fields only (no derived/computed flags)
    6. Log retrieval

    Subscription fields returned:
        - companyId, nombre, plataforma, addedAt
        - lastScannedAt, lastScanStatus, lastVacancyCount, consecutiveFailures

    Requirements:
    - 8.1: Query Suscripciones by userId
    - 8.2: Filter for activa=true only
    - 8.3: Left-join Empresas for details
    - 8.4: Sort by addedAt descending
    - 8.5: Return raw stored fields only
    - 8.6: Return {"subscriptions": [...]}
    """
    logger.info(
        "list_user_subscriptions_start",
        context={"user_id": user_id},
    )

    try:
        # Step 1-2: Query suscripciones by userId and filter active
        suscripciones_items = query_by_pk("suscripciones", "userId", user_id, limit=1000)

        # Get DynamoDB client for Empresas queries
        dynamodb = _get_dynamodb_client()
        empresas_table = dynamodb.Table(TABLES["empresas"])

        # Step 3: Filter for active and left-join with Empresas
        subscriptions = []
        for item in suscripciones_items:
            if not item.get("activa", False):
                continue

            company_id = item.get("companyId")

            # Get company details
            try:
                company_response = empresas_table.get_item(Key={"companyId": company_id})
                if "Item" not in company_response:
                    # Company not found, skip this subscription
                    continue

                company = company_response["Item"]

                subscription_item = SubscriptionItem(
                    companyId=company_id,
                    nombre=company.get("nombre"),
                    plataforma=company.get("plataforma"),
                    addedAt=item.get("addedAt"),
                    lastScannedAt=company.get("lastScannedAt"),
                    lastScanStatus=company.get("lastScanStatus"),
                    lastVacancyCount=company.get("lastVacancyCount", 0),
                    consecutiveFailures=company.get("consecutiveFailures", 0),
                )
                subscriptions.append(subscription_item)
            except Exception as e:
                logger.warning(
                    "list_user_subscriptions_company_lookup_failed",
                    context={
                        "user_id": user_id,
                        "company_id": company_id,
                        "error": str(e),
                    },
                )
                continue

        # Step 4: Sort by addedAt descending
        subscriptions.sort(key=lambda x: x.addedAt, reverse=True)

        logger.info(
            "list_user_subscriptions_success",
            context={
                "user_id": user_id,
                "count": len(subscriptions),
            },
        )

        return SubscriptionListResponse(subscriptions=subscriptions)

    except Exception as e:
        logger.error(
            "list_user_subscriptions_error",
            context={
                "user_id": user_id,
                "error": str(e),
            },
        )
        raise


# ============================================================================
# PUT /me/companies/{companyId} - Toggle subscription
# ============================================================================


@subscriptions_router.put("/{company_id}", response_model=SubscriptionUpdateResponse)
async def toggle_subscription(
    company_id: str,
    request: ToggleSubscriptionRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Activate or deactivate a company subscription for the user.

    Endpoint: PUT /me/companies/{companyId}
    Auth: Required (JWT)

    Path Parameters:
        - companyId (str): Company ID (SHA-256 hash)

    Request Body:
        - activa (bool): True to activate, False to deactivate

    Response (HTTP 200):
        - companyId, activa, updatedAt

    Error Responses:
        - HTTP 404: Subscription not found for this (userId, companyId)
        - HTTP 400: Company not found in Empresas table

    Logic:
    1. Validate subscription exists for (userId, companyId) (404 if missing)
    2. Validate companyId exists in Empresas (400 if missing)
    3. Set activa flag
    4. If reactivating (activa=true): Update addedAt to current timestamp
    5. If deactivating (activa=false): Keep addedAt unchanged
    6. Persist to Suscripciones
    7. Return 200 with companyId, activa, updatedAt

    Requirements:
    - 9.1: Accept PUT with activa flag
    - 9.2: Validate subscription exists (404 subscription_not_found)
    - 9.3: Validate company exists (400 company_not_found)
    - 9.4: Set activa flag
    - 9.5: Refresh addedAt on reactivation
    - 9.6: Persist atomically
    - 9.7: Return 200 with companyId, activa, updatedAt
    - 9.8: Log operation
    """
    logger.info(
        "toggle_subscription_start",
        context={
            "user_id": user_id,
            "company_id": company_id,
            "activa": request.activa,
        },
    )

    try:
        # Get DynamoDB client
        dynamodb = _get_dynamodb_client()
        suscripciones_table = dynamodb.Table(TABLES["suscripciones"])
        empresas_table = dynamodb.Table(TABLES["empresas"])

        # Step 1: Validate subscription exists
        subscription_response = suscripciones_table.get_item(
            Key={"userId": user_id, "companyId": company_id}
        )

        if "Item" not in subscription_response:
            logger.warning(
                "toggle_subscription_not_found",
                context={
                    "user_id": user_id,
                    "company_id": company_id,
                },
            )
            raise SubscriptionNotFound()

        # Step 2: Validate company exists in Empresas
        company_response = empresas_table.get_item(Key={"companyId": company_id})

        if "Item" not in company_response:
            logger.warning(
                "toggle_subscription_company_not_found",
                context={
                    "company_id": company_id,
                },
            )
            raise CompanyNotFound(company_id=company_id)

        # Step 3-5: Prepare update
        updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if request.activa:
            # Reactivating: update addedAt and activa
            suscripciones_table.update_item(
                Key={"userId": user_id, "companyId": company_id},
                UpdateExpression="SET activa = :activa, addedAt = :addedAt",
                ExpressionAttributeValues={
                    ":activa": True,
                    ":addedAt": updated_at,
                },
            )
        else:
            # Deactivating: only update activa, keep addedAt unchanged
            suscripciones_table.update_item(
                Key={"userId": user_id, "companyId": company_id},
                UpdateExpression="SET activa = :activa",
                ExpressionAttributeValues={
                    ":activa": False,
                },
            )

        logger.info(
            "toggle_subscription_success",
            context={
                "user_id": user_id,
                "company_id": company_id,
                "activa": request.activa,
            },
        )

        return SubscriptionUpdateResponse(
            companyId=company_id,
            activa=request.activa,
            updatedAt=updated_at,
        )

    except (SubscriptionNotFound, CompanyNotFound):
        raise
    except Exception as e:
        logger.error(
            "toggle_subscription_error",
            context={
                "user_id": user_id,
                "company_id": company_id,
                "error": str(e),
            },
        )
        raise
