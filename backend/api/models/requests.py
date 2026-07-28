"""
Request body schemas for API endpoints.

These are request-only Pydantic models, separate from domain models in shared/models.py.
They define the shape of incoming request bodies for validation and documentation.
All models use ConfigDict(extra="ignore") for forward compatibility with future clients.

Requirements: 1.1, 3.1, 5.1, 7.1, 9.1
"""

from typing import List
from pydantic import BaseModel, ConfigDict, Field
from backend.shared.models import PerfilEstructurado


class ParseCVRequest(BaseModel):
    """Request body for POST /me/profile/parse.
    
    Contains raw CV text to be parsed into structured profile.
    Note: max_length validation is NOT applied here; instead, the endpoint
    validates the size (≤50KB) and returns HTTP 413 if exceeded.
    This allows us to return a proper error response instead of FastAPI's
    default 422 validation error.
    """

    cvText: str = Field(..., description="Raw CV text (≤50KB)")

    model_config = ConfigDict(extra="ignore")


class SaveProfileRequest(BaseModel):
    """Request body for PUT /me/profile.
    
    Contains the structured profile to be saved.
    """

    perfilEstructurado: PerfilEstructurado = Field(
        ..., description="Structured profile object from CV parsing or manual editing"
    )

    model_config = ConfigDict(extra="ignore")


class SetRolesRequest(BaseModel):
    """Request body for PUT /me/roles.
    
    Contains the list of active job roles/titles selected by the user.
    """

    cargosActivos: List[str] = Field(
        ...,
        description="List of active job roles (0-10 items, each ≤50 chars)",
    )

    model_config = ConfigDict(extra="ignore")


class AddCompanyRequest(BaseModel):
    """Request body for POST /companies.
    
    Contains the careers URL for a company to be added to the shared catalog.
    """

    careersUrl: str = Field(..., description="Company careers page URL (http/https)")

    model_config = ConfigDict(extra="ignore")


class ToggleSubscriptionRequest(BaseModel):
    """Request body for PUT /me/companies/{companyId}.
    
    Contains the subscription activation state.
    """

    activa: bool = Field(..., description="Whether the subscription is active (true) or inactive (false)")

    model_config = ConfigDict(extra="ignore")


class ManualVacancyRequest(BaseModel):
    """Request body for POST /me/vacancies/manual.
    
    Contains pasted job posting text, URL, and company name for manual vacancy registration.
    """

    textoPegado: str = Field(..., min_length=1, max_length=20000, description="Pasted job posting text (1-20000 chars)")
    enlace: str = Field(..., description="Job posting URL (absolute http/https)")
    nombreEmpresa: str = Field(..., min_length=1, max_length=200, description="Company name (1-200 chars after trim)")

    model_config = ConfigDict(extra="ignore")


class CreateEntryRequest(BaseModel):
    """Request body for POST /me/vacancies/{companyId}/{vacancyId}/entries."""

    tipo: str = Field(..., description="Entry type: 'preguntas' or 'nota_entrevista'")
    contenido: str = Field(..., min_length=1, max_length=5000, description="Entry content (1-5000 chars)")

    model_config = ConfigDict(extra="ignore")
