from __future__ import annotations

from dataclasses import dataclass

import redis.asyncio as aioredis
import structlog

from app.config import MODEL_REGISTRY, settings

log = structlog.get_logger(__name__)

MODEL_KEYS: tuple[str, ...] = ("LLM_MODEL", "LLM_FALLBACK")
HASH_KEY = "ai_engine:runtime_models"

RUNTIME_KEY_TO_SETTINGS_ATTR: dict[str, str] = {
    "LLM_MODEL": "llm_model",
    "LLM_FALLBACK": "llm_fallback",
    "CRITIC_MODEL": "critic_model",
    "METADATA_EXTRACTOR_MODEL": "metadata_extractor_model",
    "COMPRESSION_MODEL": "compression_model",
    "PROPOSITIONAL_CHUNKER_MODEL": "propositional_chunker_model",
    "CONTEXTUAL_CHUNKER_MODEL": "contextual_chunker_model",
}

MODEL_KEYS = tuple(RUNTIME_KEY_TO_SETTINGS_ATTR.keys())


@dataclass(frozen=True)
class RuntimeModelEntry:
    effective: str
    default: str
    overridden: bool


class RuntimeConfigUnavailable(Exception):
    """Raised when runtime model overrides cannot be written."""


class RuntimeModelConfig:
    """Redis-backed runtime overrides for primary/fallback model selection."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    def _get_redis(self) -> aioredis.Redis:
        return aioredis.from_url(self._redis_url, decode_responses=True)

    @staticmethod
    def _default_for(key: str) -> str:
        attr = RUNTIME_KEY_TO_SETTINGS_ATTR.get(key)
        if attr is None:
            raise ValueError(f"Unknown runtime model key: {key}")

        value = getattr(settings, attr, None)
        if isinstance(value, str) and value:
            return value

        # Secondary model knobs are optional in settings; when unset, we
        # inherit the primary model to keep runtime config always concrete.
        return settings.llm_model

    @staticmethod
    def _validate_key(key: str) -> None:
        if key not in MODEL_KEYS:
            raise ValueError(f"Unknown runtime model key: {key}")

    @staticmethod
    def _provider_key_available(model_name: str) -> bool:
        cfg = MODEL_REGISTRY.get(model_name)
        if cfg is None:
            return False
        if cfg.provider == "openai":
            return bool(settings.openai_api_key)
        if cfg.provider == "anthropic":
            return bool(settings.anthropic_api_key)
        return False

    async def get_overrides(self) -> dict[str, str]:
        redis = self._get_redis()
        try:
            raw = await redis.hgetall(HASH_KEY)
            return {k: v for k, v in raw.items() if k in MODEL_KEYS}
        except Exception as exc:
            log.warning("runtime_model_overrides_read_failed", error=str(exc)[:200])
            return {}
        finally:
            await redis.aclose()

    async def set_overrides(self, changes: dict[str, str | None]) -> None:
        redis = self._get_redis()
        try:
            async with redis.pipeline(transaction=False) as pipe:
                for key, value in changes.items():
                    self._validate_key(key)
                    if value is None:
                        pipe.hdel(HASH_KEY, key)
                    else:
                        pipe.hset(HASH_KEY, key, value)
                await pipe.execute()
        except Exception as exc:
            raise RuntimeConfigUnavailable(str(exc)) from exc
        finally:
            await redis.aclose()

    async def get(self, key: str) -> str | None:
        """Return override for a single key, or None when unset/unavailable."""
        self._validate_key(key)
        overrides = await self.get_overrides()
        return overrides.get(key)

    async def set(self, key: str, value: str | None) -> None:
        """Set (or clear) one runtime override key."""
        self._validate_key(key)
        await self.set_overrides({key: value})

    async def effective(self, key: str) -> str:
        """Resolved value for one key: override if present, else default."""
        self._validate_key(key)
        override = await self.get(key)
        return override or self._default_for(key)

    async def snapshot(self) -> dict[str, RuntimeModelEntry]:
        overrides = await self.get_overrides()
        return {
            key: RuntimeModelEntry(
                effective=overrides.get(key) or self._default_for(key),
                default=self._default_for(key),
                overridden=key in overrides,
            )
            for key in MODEL_KEYS
        }

    async def reset_all(self) -> None:
        """Clear all runtime model overrides at once."""
        redis = self._get_redis()
        try:
            await redis.delete(HASH_KEY)
        except Exception as exc:
            raise RuntimeConfigUnavailable(str(exc)) from exc
        finally:
            await redis.aclose()

    def available_models(self) -> list[str]:
        models: list[str] = []
        for name in MODEL_REGISTRY:
            if self._provider_key_available(name):
                models.append(name)

        # Always expose defaults even if keys are currently missing.
        defaults = {settings.llm_model, settings.llm_fallback}
        for model_name in sorted(defaults):
            if model_name in MODEL_REGISTRY and model_name not in models:
                models.append(model_name)

        return sorted(models)


runtime_model_config = RuntimeModelConfig(settings.redis_url)
