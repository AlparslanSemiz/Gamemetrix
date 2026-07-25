"""Request and response bodies for the /api/account endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from ...services.account_state import COLLECTION_TYPES, AlertState

MAX_EMAIL_LENGTH = 320
MAX_PASSWORD_LENGTH = 128
MIN_PASSWORD_LENGTH = 12
MIN_PASSWORD_DISTINCT_CHARS = 4
MAX_DISPLAY_NAME_LENGTH = 80
MIN_DISPLAY_NAME_LENGTH = 2
MAX_COLLECTION_ENTRIES = 5000
MAX_MERGED_COLLECTION_ENTRIES = 10_000
MAX_ALERT_KEYS = 1000
MAX_ALERT_KEY_LENGTH = 240
MIN_TOKEN_LENGTH = 32
MAX_TOKEN_LENGTH = 256


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MessageResponse(BaseModel):
    message: str


def validate_password_strength(value: str) -> str:
    if value != value.strip() or len(set(value)) < MIN_PASSWORD_DISTINCT_CHARS:
        raise ValueError("Choose a less repetitive password without leading or trailing spaces.")
    return value


class RegisterPayload(StrictPayload):
    display_name: str = Field(min_length=MIN_DISPLAY_NAME_LENGTH, max_length=MAX_DISPLAY_NAME_LENGTH)
    email: EmailStr = Field(max_length=MAX_EMAIL_LENGTH)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("display_name")
    @classmethod
    def collapse_display_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < MIN_DISPLAY_NAME_LENGTH:
            raise ValueError("Display name must contain at least two visible characters.")
        return normalized

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return validate_password_strength(value)


class LoginPayload(StrictPayload):
    email: EmailStr = Field(max_length=MAX_EMAIL_LENGTH)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class TokenPayload(StrictPayload):
    token: str = Field(min_length=MIN_TOKEN_LENGTH, max_length=MAX_TOKEN_LENGTH)


class VerifyEmailPayload(TokenPayload):
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class ResetPasswordPayload(TokenPayload):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return validate_password_strength(value)


class ForgotPasswordPayload(StrictPayload):
    email: EmailStr = Field(max_length=MAX_EMAIL_LENGTH)


class CollectionsPayload(StrictPayload):
    watchlist: list[str] = Field(default_factory=list, max_length=MAX_COLLECTION_ENTRIES)
    playing: list[str] = Field(default_factory=list, max_length=MAX_COLLECTION_ENTRIES)
    seen: list[str] = Field(default_factory=list, max_length=MAX_COLLECTION_ENTRIES)
    completed: list[str] = Field(default_factory=list, max_length=MAX_COLLECTION_ENTRIES)
    on_hold: list[str] = Field(default_factory=list, max_length=MAX_COLLECTION_ENTRIES)
    dropped: list[str] = Field(default_factory=list, max_length=MAX_COLLECTION_ENTRIES)
    liked: list[str] = Field(default_factory=list, max_length=MAX_COLLECTION_ENTRIES)
    favorites: list[str] = Field(default_factory=list, max_length=MAX_COLLECTION_ENTRIES)


class PreferencePayload(StrictPayload):
    min_discount: int = Field(default=20, ge=1, le=90)
    min_score: int = Field(default=80, ge=1, le=100)
    upcoming_days: int = Field(default=45, ge=1, le=365)
    email_digest_enabled: bool = False
    marketing_enabled: bool = False
    settings: dict = Field(default_factory=dict)


class MergePayload(StrictPayload):
    collections: CollectionsPayload = Field(default_factory=CollectionsPayload)
    preferences: PreferencePayload = Field(default_factory=PreferencePayload)
    read_alerts: list[str] = Field(default_factory=list, max_length=MAX_COLLECTION_ENTRIES)
    dismissed_alerts: list[str] = Field(default_factory=list, max_length=MAX_COLLECTION_ENTRIES)

    @model_validator(mode="after")
    def validate_total_collection_size(self) -> "MergePayload":
        total = sum(len(getattr(self.collections, key)) for key in COLLECTION_TYPES)
        if total > MAX_MERGED_COLLECTION_ENTRIES:
            raise ValueError("Combined collection payload is too large.")
        return self


class PreferencePatch(StrictPayload):
    min_discount: int | None = Field(default=None, ge=1, le=90)
    min_score: int | None = Field(default=None, ge=1, le=100)
    upcoming_days: int | None = Field(default=None, ge=1, le=365)
    email_digest_enabled: bool | None = None
    marketing_enabled: bool | None = None
    settings: dict | None = None


class AlertStatePayload(StrictPayload):
    state: AlertState


class AlertStateBulkPayload(AlertStatePayload):
    keys: list[str] = Field(min_length=1, max_length=MAX_ALERT_KEYS)

    @field_validator("keys")
    @classmethod
    def validate_keys(cls, values: list[str]) -> list[str]:
        cleaned = list(
            dict.fromkeys(value for value in values if value and len(value) <= MAX_ALERT_KEY_LENGTH)
        )
        if not cleaned:
            raise ValueError("At least one valid alert key is required.")
        return cleaned


class DeleteAccountPayload(StrictPayload):
    confirmation: Literal["DELETE"]
    current_password: str | None = Field(default=None, max_length=MAX_PASSWORD_LENGTH)
