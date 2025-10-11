from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, HttpUrl, model_validator


DEFAULT_CONFIG_PATH = Path(os.getenv("SARASWATI_CONFIG", Path.cwd() / "config.yml"))


class AuthConfig(BaseModel):
    """Authentication and user management settings."""
    pass


class ExternalAuthConfig(BaseModel):
    """Configuration for an external auth provider (introspection-based)."""

    service: Optional[HttpUrl] = Field(None, description="Base URL for the external auth service")
    login_path: str = Field("/api/auth/login", description="Relative path to the login endpoint on the auth service")
    introspect_path: Optional[str] = Field(
        "/introspect",
        description="Relative path to the token introspection endpoint. Use null to disable remote introspection.",
    )
    audience: Optional[str] = Field(None, description="JWT audience to validate against for tokens returned by the external provider")
    issuer: Optional[str] = Field(None, description="Expected JWT issuer for external tokens")
    cache_ttl_seconds: int = Field(300, description="How long to cache token introspection results")


class NativeAuthConfig(BaseModel):
    """Configuration for the native (Elasticsearch-backed) auth provider."""

    jwt_secret: Optional[str] = Field(
        None,
        description="Shared secret for signing and validating locally-issued JWTs",
    )
    jwt_algorithm: str = Field("HS256", description="JWT HMAC algorithm to use for local tokens")
    audience: Optional[str] = Field(None, description="JWT audience for locally-issued tokens")
    issuer: Optional[str] = Field(None, description="JWT issuer for locally-issued tokens")
    cache_ttl_seconds: int = Field(300, description="Default token TTL (seconds) for locally-issued tokens")


class ElasticsearchConfig(BaseModel):
    """Elasticsearch connectivity configuration."""

    hosts: List[str] = Field(default_factory=lambda: ["http://localhost:9200"], description="Elasticsearch hosts")
    notes_index: str = Field("notes", description="Index used for storing note metadata")
    versions_index: str = Field("note_versions", description="Index used for storing note versions")
    reviews_index: str = Field("note_reviews", description="Index used for storing note review records")
    review_events_index: str = Field(
        "note_review_events",
        description="Index used for storing timeline events related to note reviews",
    )
    # Index for storing user records when using Elasticsearch-based auth
    users_index: str = Field("users", description="Index used for storing user records for auth")


class EmbeddingConfig(BaseModel):
    """Vector embedding provider configuration."""

    provider: str = Field("ollama", description="Name of embedding provider")
    base_url: HttpUrl = Field(..., description="Base URL for the embedding service")
    model: str = Field(..., description="Embedding model identifier")
    timeout_seconds: int = Field(30, description="HTTP timeout for embedding calls")


class SaraswatiSettings(BaseModel):
    """Top-level application configuration object."""

    environment: str = Field("development", description="Environment name")
    frontend_base_path: str = Field("/knowledge", description="Base path for the frontend")
    api_prefix: str = Field("/knowledge/api", description="API route prefix")
    store_backend: Literal["elastic"] = Field(
        "elastic",
        description="Primary persistence backend to use for notes data",
    )
    # Top-level auth selection and per-system configs
    auth_system: Literal["introspect", "decode", "elastic"] = Field(
        "elastic",
        description=(
            "Auth system selection: 'introspect' to use a remote provider, 'decode' to locally decode JWTs, "
            "or 'elastic' to use an Elasticsearch-backed user store with locally-issued JWTs"
        ),
    )
    # legacy/top-level auth holder (kept as an empty/defaulted object for compatibility)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    auth_external: ExternalAuthConfig = Field(default_factory=ExternalAuthConfig)
    auth_native: NativeAuthConfig = Field(default_factory=NativeAuthConfig)
    elasticsearch: Optional[ElasticsearchConfig] = None
    embedding: EmbeddingConfig
    # HTTP callback endpoints to notify observers about lifecycle events (order preserved)
    # Each webhook can specify headers and the list of events it cares about.
    class WebhookConfig(BaseModel):
        url: HttpUrl = Field(..., description="Callback URL for the observer")
        headers: Optional[Dict[str, str]] = Field(default_factory=dict, description="Optional headers to send with the callback")
        events: List[str] = Field(default_factory=list, description="List of event names to receive. Empty list means all events")

    webhooks: List[WebhookConfig] = Field(default_factory=list, description="List of observer webhook configs")

    @model_validator(mode="after")
    def _validate_backend(self) -> "SaraswatiSettings":
        if not self.elasticsearch:
            raise ValueError("Elasticsearch configuration is required for this application")
        # Auth configuration sanity checks
        if self.auth_system in ("decode", "elastic") and not self.auth_native.jwt_secret:
            raise ValueError("auth_native.jwt_secret is required when auth_system is 'decode' or 'elastic'")
        if self.auth_system == "introspect" and not self.auth_external.service:
            raise ValueError("auth_external.service is required when auth_system is 'introspect'")
        return self


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def build_settings(config_path: Optional[Path] = None) -> SaraswatiSettings:
    """Instantiate settings from a YAML file."""

    resolved_path = Path(config_path or DEFAULT_CONFIG_PATH)
    if not resolved_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {resolved_path}")

    data = _load_yaml(resolved_path)
    return SaraswatiSettings(**data)


@lru_cache(maxsize=1)
def get_settings() -> SaraswatiSettings:
    """Cached accessor for settings."""

    return build_settings()
