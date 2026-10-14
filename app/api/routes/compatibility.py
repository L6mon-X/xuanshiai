"""Small unauthenticated compatibility endpoints used by external probes.

Some OpenAI-compatible clients probe ``/models`` before sending any request.
These endpoints intentionally expose only service metadata and never secrets.
"""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelList(BaseModel):
    object: str = "list"
    data: list[ModelInfo]


class ServiceStatus(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    api_prefix: str


class PublicConfig(BaseModel):
    service: str
    version: str
    environment: str
    api_prefix: str
    ai_provider: str
    ai_model: str
    ai_enabled: bool
    docs_enabled: bool


router = APIRouter()
legacy_router = APIRouter()


def _models() -> ModelList:
    model_names = {settings.ai_model}
    if settings.ai_avatar_model:
        model_names.add(settings.ai_avatar_model)
    created = int(datetime.now(timezone.utc).timestamp())
    return ModelList(
        data=[
            ModelInfo(id=name, created=created, owned_by=settings.ai_provider_name)
            for name in sorted(model_names)
        ]
    )


def _status() -> ServiceStatus:
    return ServiceStatus(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        api_prefix=settings.api_prefix,
    )


def _config() -> PublicConfig:
    return PublicConfig(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        api_prefix=settings.api_prefix,
        ai_provider=settings.ai_provider_name,
        ai_model=settings.ai_model,
        ai_enabled=settings.ai_enabled,
        docs_enabled=settings.docs_enabled,
    )


@router.get("/models", response_model=ModelList, tags=["系统"], summary="OpenAI 兼容模型列表")
async def models() -> ModelList:
    return _models()


@router.get("/status", response_model=ServiceStatus, tags=["系统"], summary="兼容服务状态")
async def status() -> ServiceStatus:
    return _status()


@router.get("/config", response_model=PublicConfig, tags=["系统"], summary="兼容公开配置")
async def config() -> PublicConfig:
    return _config()


@legacy_router.get("/api/models", response_model=ModelList, tags=["系统"], include_in_schema=False)
async def legacy_models() -> ModelList:
    return _models()


@legacy_router.get("/api/status", response_model=ServiceStatus, tags=["系统"], include_in_schema=False)
async def legacy_status() -> ServiceStatus:
    return _status()


@legacy_router.get("/api/config", response_model=PublicConfig, tags=["系统"], include_in_schema=False)
async def legacy_config() -> PublicConfig:
    return _config()
