"""LLM access layer: OpenRouter free-model pools, global concurrency cap, cooldown-based failover,
JSON-mode structured output.

Each role (reasoner / worker) has an ordered pool of `:free` models in `settings`. When a model is
rate-limited upstream (free models often are), returns nothing, or errors, it goes on cooldown and
the next model in the pool takes the call immediately instead of sleeping on the same one.
"""
import asyncio
import json
import logging
import re
import time
from typing import Literal, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)
Role = Literal["reasoner", "worker"]

log = logging.getLogger("app.llm")

MAX_ATTEMPTS = 12
_semaphore: asyncio.Semaphore | None = None
_cooldown: dict[str, float] = {}  # model -> monotonic time before which it is skipped


class BadResponse(RuntimeError):
    """Model output is unusable: empty (hidden reasoning ate the budget) or leaked chain-of-thought."""


# Chain-of-thought that some free reasoning endpoints emit as plain content instead of the reasoning field.
_LEAKED_REASONING = re.compile(
    r"\s*(we need to|we must|we should|let'?s (think|craft|write|draft|see)|the user (wants|asks|is asking)|"
    r"okay,? (so|let)|first,? (i|we) (need|should|must))\b", re.IGNORECASE)


def _check_output(model: str, text: str, max_tokens: int) -> None:
    """Raises BadResponse for empty output, leaked reasoning, or runaway length (~4 chars/token)."""
    if not text.strip():
        raise BadResponse(f"{model} returned empty content")
    if _LEAKED_REASONING.match(text):
        raise BadResponse(f"{model} leaked chain-of-thought: {text[:60]!r}")
    if len(text) > 5 * (max_tokens + settings.reasoning_headroom):
        raise BadResponse(f"{model} ignored max_tokens ({len(text)} chars)")


def _cool(model: str, exc: Exception) -> bool:
    """Puts `model` on cooldown if `exc` is failover material; False means the error should propagate."""
    wait = 0 if _is_daily_limit(exc) else _cooldown_for(exc)
    if wait:
        _cooldown[model] = time.monotonic() + wait
        log.warning("llm failover: %s cooling down %ss (%s)", model, wait, str(exc)[:140])
    return bool(wait)


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.llm_concurrency)
    return _semaphore


def _is_daily_limit(exc: Exception) -> bool:
    """Account-wide free-tier request cap — no model in the pool can help until it resets."""
    msg = str(exc).lower()
    return "free-models-per-day" in msg or "per-day" in msg or "per day" in msg


def _cooldown_for(exc: Exception) -> float:
    """Seconds to skip a model after `exc`; 0 means the error is not model-failover material."""
    msg = str(exc).lower()
    status = getattr(exc, "status_code", None)
    if status == 429 or "rate limit" in msg or "rate-limited" in msg:
        return settings.rate_limit_cooldown_s
    if isinstance(exc, BadResponse) or "length limit" in msg:
        return 300
    if isinstance(exc, TypeError) and "nonetype" in msg:  # HTTP 200 with an error body and no `choices`
        return settings.rate_limit_cooldown_s
    if status in (400, 404, 422):  # model doesn't support a parameter / endpoint gone
        return 600
    if status in (408, 409, 500, 502, 503, 504) or any(
            k in msg for k in ("timeout", "timed out", "connection", "temporarily", "overloaded",
                               "upstream error", "resourceexhausted", "provider returned error")):
        return 20
    return 0


def _pool(role: Role) -> list[str]:
    return settings.reasoner_models if role == "reasoner" else settings.worker_models


async def _pick(role: Role) -> str:
    """First model in the role's pool that is not cooling down; waits for the soonest if all are."""
    pool = _pool(role)
    while True:
        now = time.monotonic()
        for m in pool:
            if _cooldown.get(m, 0) <= now:
                return m
        await asyncio.sleep(min(max(min(_cooldown[m] for m in pool) - now, 1), 30))


def make_llm(model: str, *, temperature: float = 0.2, max_tokens: int = 1024,
             json_mode: bool = False, streaming: bool = False) -> ChatOpenAI:
    model_kwargs: dict = {}
    if json_mode:
        model_kwargs["response_format"] = {"type": "json_object"}
    return ChatOpenAI(
        model=model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=temperature,
        max_tokens=max_tokens + settings.reasoning_headroom,
        streaming=streaming,
        stream_usage=True,
        max_retries=0,  # failover below owns retries
        timeout=120,
        model_kwargs=model_kwargs,
        extra_body={"reasoning": {"effort": "low"}},
    )


def _tokens(msg: BaseMessage) -> int:
    usage = getattr(msg, "usage_metadata", None) or {}
    return usage.get("total_tokens", 0) or 0


async def _invoke(role: Role, messages: list[BaseMessage], **llm_kwargs) -> BaseMessage:
    last_exc: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        model = await _pick(role)
        try:
            async with _sem():
                msg = await make_llm(model, **llm_kwargs).ainvoke(messages)
            _check_output(model, str(msg.content), llm_kwargs.get("max_tokens", 1024))
            return msg
        except Exception as exc:
            last_exc = exc
            if not _cool(model, exc):
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

    On a failure the model is put on cooldown and the whole stream restarts on the next model
    (signalling `reset=True` so consumers clear partial output); falls back to a non-streaming
    call as a last resort.
    """
    for attempt in range(4):
        model = await _pick(role)
        llm = make_llm(model, temperature=temperature, max_tokens=max_tokens, streaming=True)
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
                            _check_output(model, "".join(parts), max_tokens)  # vet before consumers see it
                            await on_chunk(buf)
                            buf = ""
                    usage = getattr(chunk, "usage_metadata", None)
                    if usage:
                        tokens = usage.get("total_tokens", 0)
            if buf:
                await on_chunk(buf)
            full = "".join(parts)
            _check_output(model, full, max_tokens)
            return full, tokens or max(1, len(full) // 4)
        except Exception as exc:
            if _cool(model, exc):
                continue
            text, tokens = await complete(role, system, user, temperature=temperature, max_tokens=max_tokens)
            await on_chunk("", reset=True)
            await on_chunk(text)
            return text, tokens
    text, tokens = await complete(role, system, user, temperature=temperature, max_tokens=max_tokens)
    await on_chunk("", reset=True)
    await on_chunk(text)
    return text, tokens
