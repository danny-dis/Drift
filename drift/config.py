"""All configuration in one place."""

import os
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
PROVIDER_PRESETS = {"openai": None, "openrouter": "https://openrouter.ai/api/v1"}
PROVIDER_KEY_ENV_VARS = {"openrouter": "OPENROUTER_API_KEY"}


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    config["provider"] = os.environ.get("DRIFT_PROVIDER") or config.get("provider", "openai")
    provider = config["provider"]
    config["base_url"] = os.environ.get("DRIFT_BASE_URL") or config.get("base_url") or PROVIDER_PRESETS.get(provider)
    provider_key_var = PROVIDER_KEY_ENV_VARS.get(provider)
    config["api_key"] = ((os.environ.get(provider_key_var) if provider_key_var else None) or os.environ.get("OPENAI_API_KEY") or config.get("api_key"))
    config["model"] = os.environ.get("DRIFT_MODEL") or config.get("model", "gpt-4o")
    config["ollama_api_key"] = os.environ.get("OLLAMA_API_KEY") or config.get("ollama_api_key")

    # Continuous-operation defaults. The prompt is a workbench, never the memory.
    config.setdefault("thinking_pace_seconds", 45)
    config.setdefault("max_thoughts_in_context", 12)
    config.setdefault("context_max_items", 18)
    config.setdefault("context_max_chars", 7000)
    config.setdefault("environment_path", "./environment")
    config.setdefault("reflection_threshold", 50)
    config.setdefault("memory_retrieval_count", 5)
    config.setdefault("embedding_model", "text-embedding-3-small")
    config.setdefault("recency_decay_rate", 0.995)
    config.setdefault("max_tool_rounds", 12)

    project_root = os.path.dirname(os.path.dirname(__file__))
    if not os.path.isabs(config["environment_path"]):
        config["environment_path"] = os.path.join(project_root, config["environment_path"])
    if provider == "custom" and not config.get("base_url"):
        raise ValueError("Provider 'custom' requires base_url in config.yaml or DRIFT_BASE_URL env var")
    return config


config = load_config()
