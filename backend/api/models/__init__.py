"""Request and response models for API endpoints."""

from .requests import (
    ParseCVRequest,
    SaveProfileRequest,
    SetRolesRequest,
    AddCompanyRequest,
    ToggleSubscriptionRequest,
)

__all__ = [
    "ParseCVRequest",
    "SaveProfileRequest",
    "SetRolesRequest",
    "AddCompanyRequest",
    "ToggleSubscriptionRequest",
]
