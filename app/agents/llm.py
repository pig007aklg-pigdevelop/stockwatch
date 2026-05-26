"""LangChain ChatOpenAI factory (DeepSeek via OpenAI-compatible API)."""
from langchain_openai import ChatOpenAI

from app.config import config


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
        model=config.OPENAI_MODEL,
        temperature=0.3,
        max_tokens=2000,
    )
