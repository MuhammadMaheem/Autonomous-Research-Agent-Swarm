from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    groq_api_key: str = ""
    tavily_api_key: str | None = None

    model_reasoner: str = "openai/gpt-oss-120b"
    model_worker: str = "llama-3.1-8b-instant"
    # Tried in order when the reasoner hits daily token limits.
    reasoner_fallbacks: list[str] = [
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "llama-3.3-70b-versatile",
    ]

    coverage_threshold: float = 0.75
    max_iterations: int = 2          # max critic loop-backs
    max_subquestions: int = 6        # initial plan cap
    max_subquestions_total: int = 9  # cap after replans
    token_budget: int = 80_000       # per run
    llm_concurrency: int = 2

    search_results_per_query: int = 4
    sandbox_timeout_s: int = 15
    sandbox_cpu_s: int = 10

    db_path: Path = BACKEND_DIR / "data" / "swarm.db"
    corpus_dir: Path = BACKEND_DIR / "data" / "corpus"
    reports_dir: Path = BACKEND_DIR / "reports"


settings = Settings()
