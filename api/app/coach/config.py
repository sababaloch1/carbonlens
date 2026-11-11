"""S4 AI Sustainability Coach - configuration (read from environment)."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CoachSettings:
    openai_api_key: str | None
    model: str
    timeout_s: float
    max_retries: int
    max_tokens_recs: int
    max_tokens_chat: int
    max_tokens_insights: int
    max_tokens_learning: int
    chat_history_window: int
    max_chat_message_chars: int
    max_ai_recommendations: int


def get_settings() -> CoachSettings:
    return CoachSettings(
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        timeout_s=float(os.getenv("COACH_OPENAI_TIMEOUT", "30")),
        max_retries=int(os.getenv("COACH_OPENAI_RETRIES", "2")),
        max_tokens_recs=int(os.getenv("COACH_MAX_TOKENS_RECS", "1200")),
        max_tokens_chat=int(os.getenv("COACH_MAX_TOKENS_CHAT", "600")),
        max_tokens_insights=int(os.getenv("COACH_MAX_TOKENS_INSIGHTS", "700")),
        max_tokens_learning=int(os.getenv("COACH_MAX_TOKENS_LEARNING", "900")),
        chat_history_window=int(os.getenv("COACH_CHAT_HISTORY_WINDOW", "10")),
        max_chat_message_chars=int(os.getenv("COACH_MAX_CHAT_CHARS", "2000")),
        max_ai_recommendations=int(os.getenv("COACH_MAX_AI_RECS", "5")),
    )
