"""LLM access layer: model tiering, global concurrency cap, retry/backoff, JSON-mode structured output.

Reasoner (planner/critic/citation-judge): openai/gpt-oss-120b (200k tokens/day free).
Worker (search summaries, RAG answers):   llama-3.1-8b-instant (500k tokens/day free).
On daily-limit errors the reasoner falls back down `settings.reasoner_fallbacks`.
"""
import asyncio
import json
import re
from typing import Literal, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from app.config import settings

T = TypeVar("T", bound=BaseModel)
Role = Literal["reasoner", "worker"]

_semaphore: asyncio.Semaphore | None = None
_daily_limited: set[str] = set()  # models that hit their TPD/RPD cap this process


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.llm_concurrency)
    return _semaphore


def _is_daily_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "rate_limit" in msg and ("per day" in msg or "tpd" in msg or "rpd" in msg or "daily" in msg)


def _is_retryable(exc: Exception) -> bool:
    if _is_daily_limit(exc):
        return False  # retrying within the day won't help; trigger model fallback instead
    msg = str(exc).lower()
    status = getattr(exc, "status_code", None)
    if status in (408, 409, 429, 500, 502, 503, 504):
        return True
    return any(k in msg for k in ("rate limit", "rate_limit", "timeout", "connection", "temporarily", "overloaded", "503", "429"))


def _model_for(role: Role) -> str:
    if role == "worker":
        return settings.model_worker
    for m in [settings.model_reasoner, *settings.reasoner_fallbacks]:
        if m not in _daily_limited:
            return m
    return settings.reasoner_fallbacks[-1]


def make_llm(role: Role, *, temperature: float = 0.2, max_tokens: int = 1024,
             json_mode: bool = False, streaming: bool = False) -> ChatGroq:
    model = _model_for(role)
    extra: dict = {}
    if "gpt-oss" in model:
        extra["reasoning_effort"] = "low"
    model_kwargs: dict = {}
    if json_mode:
        model_kwargs["response_format"] = {"type": "json_object"}
    return ChatGroq(
        model=model,
        api_key=settings.groq_api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
        max_retries=0,  # tenacity owns retries
        model_kwargs=model_kwargs,
        **extra,
    )


def _tokens(msg: BaseMessage) -> int:
    usage = getattr(msg, "usage_metadata", None) or {}
    return usage.get("total_tokens", 0) or 0


async def _invoke(role: Role, messages: list[BaseMessage], **llm_kwargs) -> BaseMessage:
    last_exc: Exception | None = None
    for _attempt_model in range(3):  # allows up to 2 daily-limit fallbacks for the reasoner
        llm = make_llm(role, **llm_kwargs)
        try:
            async for retry_ctx in AsyncRetrying(
                retry=retry_if_exception(_is_retryable),
                wait=wait_random_exponential(multiplier=2, min=5, max=60),
                stop=stop_after_attempt(7),
                reraise=True,
            ):
                with retry_ctx:
                    async with _sem():
                        return await llm.ainvoke(messages)
        except Exception as exc:
            last_exc = exc
            if role == "reasoner" and _is_daily_limit(exc):
                _daily_limited.add(llm.model_name)
                continue
            raise
    raise last_exc  # type: ignore[misc]


async def complete(role: Role, system: str, user: str, *,
                   temperature: float = 0.2, max_tokens: int = 1024) -> tuple[str, int]:
    msg = await _invoke(role, [SystemMessage(system), HumanMessage(user)],
                        temperature=temperature, max_tokens=max_tokens)
    return str(msg.content), _tokens(msg)


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    m = _JSON_BLOCK.search(text)
    if not m:
        raise ValueError(f"no JSON object in response: {text[:200]!r}")
    return json.loads(m.group(0))


async def structured(role: Role, system: str, user: str, schema: type[T], *,
                     temperature: float = 0.0, max_tokens: int = 1024, retries: int = 2) -> tuple[T, int]:
    """JSON-mode call parsed into `schema`; on parse/validation failure, retries with the error appended."""
    total = 0
    prompt = user
    last_err = ""
    for _ in range(retries + 1):
        msg = await _invoke(role, [SystemMessage(system), HumanMessage(prompt)],
                            temperature=temperature, max_tokens=max_tokens, json_mode=True)
        total += _tokens(msg)
        try:
            return schema.model_validate(_extract_json(str(msg.content))), total
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_err = str(exc)[:600]
            prompt = f"{user}\n\nYour previous response was invalid: {last_err}\nReturn ONLY corrected JSON matching the schema."
    raise ValueError(f"structured output failed after {retries + 1} attempts: {last_err}")


async def stream_complete(role: Role, system: str, user: str, *, on_chunk,
                          temperature: float = 0.3, max_tokens: int = 1400) -> tuple[str, int]:
    """Streaming completion; awaits `on_chunk(text, reset=False)` per buffered chunk.

    Retries the whole stream on rate limits (signalling `reset=True` so consumers clear
    partial output); falls back to a non-streaming call as a last resort.
    """
    for attempt in range(3):
        llm = make_llm(role, temperature=temperature, max_tokens=max_tokens, streaming=True)
        parts: list[str] = []
        tokens = 0
        buf = ""
        try:
            async with _sem():
                if attempt:
                    await on_chunk("", reset=True)
                async for chunk in llm.astream([SystemMessage(system), HumanMessage(user)]):
                    text = chunk.content if isinstance(chunk.content, str) else ""
                    if text:
                        parts.append(text)
                        buf += text
                        if len(buf) >= 48:
                            await on_chunk(buf)
                            buf = ""
                    usage = getattr(chunk, "usage_metadata", None)
                    if usage:
                        tokens = usage.get("total_tokens", 0)
            if buf:
                await on_chunk(buf)
            full = "".join(parts)
            return full, tokens or max(1, len(full) // 4)
        except Exception as exc:
            if attempt < 2 and _is_retryable(exc):
                await asyncio.sleep(8 * (2 ** attempt))
                continue
            text, tokens = await complete(role, system, user, temperature=temperature, max_tokens=max_tokens)
            await on_chunk("", reset=True)
            await on_chunk(text)
            return text, tokens
