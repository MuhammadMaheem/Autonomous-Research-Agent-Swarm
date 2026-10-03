from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    tavily_api_key: str | None = None

    # Free OpenRouter models only (enforced below). Tried in order; a model that is
    # rate-limited upstream is put on cooldown and the next one takes over.
    reasoner_models: list[str] = [  # planner / critic / synthesizer / citation judge
        "google/gemma-4-31b-it:free",
        "qwen/qwen3.8-27b:free",
        "poolside/laguna-xs-2.1:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    ]
    worker_models: list[str] = [  # search summaries, RAG answers
        "google/gemma-4-26b-a4b-it:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "poolside/laguna-xs-2.1:free",
        "qwen/qwen3.8-27b:free",
        "liquid/lfm-2.5-2.6b:free",
    ]
    reasoning_headroom: int = 1500   # extra max_tokens so hidden reasoning can't starve the answer
    rate_limit_cooldown_s: int = 60

    @field_validator("reasoner_models", "worker_models")
    @classmethod
    def _free_only(cls, models: list[str]) -> list[str]:
        paid = [m for m in models if not m.endswith(":free")]
        if paid or not models:
            raise ValueError(f"only ':free' OpenRouter models are allowed, got {paid or 'empty list'}")
        return models

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
