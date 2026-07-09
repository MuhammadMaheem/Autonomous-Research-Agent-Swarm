"""Verify API keys and model access. Run: uv run python scripts/smoke_keys.py"""
import asyncio
import os

from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    from langchain_groq import ChatGroq

    for model in ("openai/gpt-oss-120b", "llama-3.1-8b-instant"):
        llm = ChatGroq(model=model, max_tokens=20, temperature=0)
        resp = await llm.ainvoke("Reply with exactly: OK")
        usage = resp.usage_metadata or {}
        print(f"{model}: {resp.content!r} (tokens={usage.get('total_tokens')})")

    if os.getenv("TAVILY_API_KEY"):
        print("TAVILY_API_KEY: set")
    else:
        print("TAVILY_API_KEY: missing -> web search will use DuckDuckGo (ddgs) fallback")


if __name__ == "__main__":
    asyncio.run(main())
