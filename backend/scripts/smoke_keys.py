"""Verify the OpenRouter key and free-model access. Run: uv run python scripts/smoke_keys.py"""
import asyncio
import os
import time

from app.config import settings
from app.services.llm import make_llm


async def probe(model: str) -> None:
    t = time.monotonic()
    try:
        resp = await make_llm(model, temperature=0, max_tokens=20).ainvoke("Reply with exactly: OK")
        tokens = (resp.usage_metadata or {}).get("total_tokens")
        print(f"  OK   {model}: {str(resp.content).strip()[:40]!r} (tokens={tokens}, {time.monotonic() - t:.1f}s)")
    except Exception as exc:  # free models are often rate-limited upstream; report, don't abort
        print(f"  FAIL {model}: {str(exc)[:110]}")


async def main() -> None:
    if not settings.openrouter_api_key:
        raise SystemExit("OPENROUTER_API_KEY missing -> add it to backend/.env")
    for role, models in (("reasoner", settings.reasoner_models), ("worker", settings.worker_models)):
        print(f"{role} pool:")
        for m in models:
            await probe(m)

    print("TAVILY_API_KEY:", "set" if os.getenv("TAVILY_API_KEY") or settings.tavily_api_key
          else "missing -> web search will use DuckDuckGo (ddgs) fallback")


if __name__ == "__main__":
    asyncio.run(main())
