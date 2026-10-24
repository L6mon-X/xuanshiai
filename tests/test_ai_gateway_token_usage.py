"""FIX-05（AI-09）：供应商 token 用量透传至网关审计。

- 供应商实际返回的用量（经 providers.last_token_usage 透传）进入
  ``GenerationAuditEvent.usage_cost``；
- 供应商未返回时保持 None（显式"未知"，不得当作零成本）；
- 失败调用不携带用量，且同任务内上一次成功调用的用量不得串染；
- 语音网关记录音频时长类用量元数据（不含音频/转写原文）。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel, SecretStr

from app.core.config import Settings
from app.services.ai.base import AITaskContext, ProviderError, ProviderErrorKind
from app.services.ai.gateway import AIGateway
from app.services.ai.providers import DeepSeekAIProvider, last_token_usage
from app.services.voice.base import TranscribeResult
from app.services.voice.gateway import VoiceGateway


class _Echo(BaseModel):
    reply: str


def _context() -> AITaskContext:
    return AITaskContext(
        task_id="task-1",
        request_id="req-1",
        scene="usage-test",
        provider="fake",
        model="fake-model",
        prompt_version="v1",
        schema_version="v1",
    )


def _capture_audit(monkeypatch: pytest.MonkeyPatch, target: str) -> list:
    events: list = []

    async def _capture(event: object) -> None:
        events.append(event)

    monkeypatch.setattr(target, _capture)
    return events


class _UsageProvider:
    """模拟真实 provider：返回结果前写入供应商用量。"""

    async def chat(
        self, messages: list[dict[str, str]], *, json_mode: bool = False
    ) -> Any:
        last_token_usage.set(
            {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
                "source": "provider",
                "model": "fake-model",
            }
        )
        return "好的"


class _NoUsageProvider:
    async def chat(
        self, messages: list[dict[str, str]], *, json_mode: bool = False
    ) -> Any:
        return "好的"


class _FailingProvider:
    async def chat(
        self, messages: list[dict[str, str]], *, json_mode: bool = False
    ) -> Any:
        raise ProviderError(
            code="AI_QUOTA_EXCEEDED",
            message="rate limited",
            kind=ProviderErrorKind.RETRYABLE,
        )


class _VoiceProvider:
    async def transcribe(self, request: Any) -> TranscribeResult:
        return TranscribeResult(text="转写文本", duration_ms=1234)


@pytest.mark.asyncio
async def test_chat_audit_records_provider_reported_usage(monkeypatch) -> None:
    events = _capture_audit(monkeypatch, "app.services.ai.gateway.record_generation_audit")
    gateway = AIGateway(provider=_UsageProvider())  # type: ignore[arg-type]
    outcome = await gateway.chat(_context(), [{"role": "user", "content": "hi"}])
    assert outcome.result == "好的"
    assert len(events) == 1
    usage = events[0].usage_cost
    assert usage == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
        "source": "provider",
        "model": "fake-model",
    }


@pytest.mark.asyncio
async def test_chat_audit_without_provider_usage_stays_unknown(monkeypatch) -> None:
    events = _capture_audit(monkeypatch, "app.services.ai.gateway.record_generation_audit")
    gateway = AIGateway(provider=_NoUsageProvider())  # type: ignore[arg-type]
    outcome = await gateway.chat(_context(), [{"role": "user", "content": "hi"}])
    assert outcome.result == "好的"
    assert len(events) == 1
    assert events[0].usage_cost is None


@pytest.mark.asyncio
async def test_failed_call_records_no_usage_and_no_stale_leak(monkeypatch) -> None:
    events = _capture_audit(monkeypatch, "app.services.ai.gateway.record_generation_audit")
    # 同任务内先置一次用量，模拟上一次成功调用的残留。
    last_token_usage.set({"total_tokens": 999, "source": "provider", "model": "old"})
    gateway = AIGateway(provider=_FailingProvider())  # type: ignore[arg-type]
    outcome = await gateway.chat(_context(), [{"role": "user", "content": "hi"}])
    assert outcome.error_code == "AI_QUOTA_EXCEEDED"
    assert len(events) == 1
    assert events[0].usage_cost is None
    assert events[0].status == "failed"


@pytest.mark.asyncio
async def test_voice_gateway_records_audio_duration_usage(monkeypatch) -> None:
    events = _capture_audit(monkeypatch, "app.services.voice.gateway.record_generation_audit")
    gateway = VoiceGateway(provider=_VoiceProvider())  # type: ignore[arg-type]
    outcome = await gateway.invoke(
        _context(), "transcribe", object(), response_type=TranscribeResult
    )
    assert outcome.result is not None
    assert len(events) == 1
    usage = events[0].usage_cost
    assert usage == {
        "audio_duration_ms": 1234,
        "source": "provider",
        "model": "fake-model",
    }


class _FlakyProvider:
    """第一次失败、第二次成功：验证重试后不残留上一次的用量。"""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(
        self, messages: list[dict[str, str]], *, json_mode: bool = False
    ) -> Any:
        self.calls += 1
        if self.calls == 1:
            raise ProviderError(
                code="AI_TEMPORARILY_UNAVAILABLE",
                message="upstream busy",
                kind=ProviderErrorKind.RETRYABLE,
            )
        last_token_usage.set(
            {
                "prompt_tokens": 5,
                "completion_tokens": 3,
                "total_tokens": 8,
                "source": "provider",
                "model": "fake-model",
            }
        )
        return "重试成功"


@pytest.mark.asyncio
async def test_retry_after_failure_records_only_fresh_usage(monkeypatch) -> None:
    """调用方重试：失败那次不记用量，成功那次记本次用量，二者不互相污染。"""
    events = _capture_audit(monkeypatch, "app.services.ai.gateway.record_generation_audit")
    provider = _FlakyProvider()
    gateway = AIGateway(provider=provider)  # type: ignore[arg-type]

    first = await gateway.chat(_context(), [{"role": "user", "content": "hi"}])
    second = await gateway.chat(_context(), [{"role": "user", "content": "hi"}])

    assert first.error_code == "AI_TEMPORARILY_UNAVAILABLE"
    assert second.result == "重试成功"
    assert len(events) == 2
    assert events[0].usage_cost is None
    assert events[1].usage_cost == {
        "prompt_tokens": 5,
        "completion_tokens": 3,
        "total_tokens": 8,
        "source": "provider",
        "model": "fake-model",
    }


# ---------------------------------------------------------------------------
# Provider 侧真实提取路径（不经手写 set，避免自证式断言）
# ---------------------------------------------------------------------------


def _deepseek_provider_with_usage(monkeypatch: pytest.MonkeyPatch, usage: Any) -> Any:
    """用 mock openai 客户端构造 DeepSeek provider，响应携带给定 usage。"""
    monkeypatch.setattr(
        "app.services.ai.providers.settings",
        Settings(
            _env_file=None,
            ai_deepseek_api_key=SecretStr("test-key"),
            ai_deepseek_model="deepseek-v4-flash",
        ),
    )
    message = MagicMock()
    message.content = "好的"
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return DeepSeekAIProvider(client=client)


class _CompletionUsage:
    """模拟 openai SDK 的 CompletionUsage（真整数）。"""

    def __init__(self, prompt: int, completion: int, total: int) -> None:
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = total


@pytest.mark.asyncio
async def test_provider_chat_publishes_sdk_usage(monkeypatch) -> None:
    provider = _deepseek_provider_with_usage(
        monkeypatch, _CompletionUsage(120, 45, 165)
    )
    last_token_usage.set(None)
    reply = await provider.chat([{"role": "user", "content": "hi"}])
    assert reply == "好的"
    assert last_token_usage.get() == {
        "prompt_tokens": 120,
        "completion_tokens": 45,
        "total_tokens": 165,
        "source": "provider",
        "model": "deepseek-v4-flash",
    }


@pytest.mark.asyncio
async def test_provider_chat_without_usage_publishes_none(monkeypatch) -> None:
    provider = _deepseek_provider_with_usage(monkeypatch, None)
    last_token_usage.set(None)
    assert await provider.chat([{"role": "user", "content": "hi"}]) == "好的"
    assert last_token_usage.get() is None


@pytest.mark.asyncio
async def test_provider_chat_ignores_non_integer_usage(monkeypatch) -> None:
    """非整数用量（供应商异常字段）一律降级为未知，不得写入审计。"""
    provider = _deepseek_provider_with_usage(
        monkeypatch, _CompletionUsage("many", None, -3)  # type: ignore[arg-type]
    )
    last_token_usage.set(None)
    assert await provider.chat([{"role": "user", "content": "hi"}]) == "好的"
    assert last_token_usage.get() is None
