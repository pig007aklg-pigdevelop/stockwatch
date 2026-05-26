"""LangChain ChatOpenAI factory (DeepSeek via OpenAI-compatible API)."""
import os

from langchain_openai import ChatOpenAI

from app.config import config


def get_llm() -> ChatOpenAI:
    api_key = (config.OPENAI_API_KEY or "").strip()
    base_url = (config.OPENAI_BASE_URL or "https://api.openai.com/v1").strip()
    model = (config.OPENAI_MODEL or "gpt-4o-mini").strip()

    # LangChain / OpenAI SDK may ignore empty constructor args and fall back to env;
    # set explicitly so .env via config always wins.
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    if base_url:
        os.environ["OPENAI_BASE_URL"] = base_url

    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.3,
        max_tokens=2000,
    )
