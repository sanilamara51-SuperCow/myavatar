from dataclasses import dataclass
from typing import Dict, Literal

ProviderKind = Literal[
    "openai_compatible",
    "anthropic_compatible",
    "gemini_compatible",
    "local_ollama",
    "custom_http",
]

ModelCapability = Literal["text", "vision", "reflection"]


@dataclass(frozen=True)
class ProviderProfile:
    provider_id: str
    name: str
    kind: ProviderKind
    base_url: str
    api_key_env: str
    extra_headers_json: str = "{}"
    enabled: bool = True


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    provider_id: str
    model_name: str
    capability: ModelCapability
    context_window: int = 0
    supports_vision: bool = False
    supports_json_mode: bool = True
    enabled: bool = True


@dataclass(frozen=True)
class ResolvedModelRoute:
    provider_id: str
    provider_kind: str
    base_url: str
    api_key_env: str
    extra_headers_json: str
    model_id: str
    model_name: str
    capability: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "provider_kind": self.provider_kind,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "extra_headers_json": self.extra_headers_json,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "capability": self.capability,
        }

