"""FlowHub - Configuration profiles."""

from enum import Enum


class ConfigProfile(str, Enum):
    DEV = "dev"
    PRODUCTION = "production"

    @classmethod
    def from_string(cls, value: str) -> "ConfigProfile":
        try:
            return cls(value.strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"FLOWHUB_ENV {value!r} is not valid. Must be one of: {valid}"
            )

    def is_production(self) -> bool:
        return self == ConfigProfile.PRODUCTION

    def is_dev(self) -> bool:
        return self == ConfigProfile.DEV

    def banner(self) -> str:
        banners = {
            ConfigProfile.DEV: "[LOCAL DEVELOPMENT]",
            ConfigProfile.PRODUCTION: "[PRODUCTION]",
        }
        return banners[self]
