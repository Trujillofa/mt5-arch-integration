"""Environment-based settings for the MT5 Arch integration."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _expand_path(value: str | Path | None) -> Path | None:
    if value is None or value == "":
        return None
    return Path(str(value)).expanduser().resolve()


class Settings(BaseSettings):
    """Load from environment / .env. Passwords are never printed by the CLI."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    mt5_login: int | None = Field(
        default=None,
        validation_alias=AliasChoices("MT5_LOGIN", "mt5_login"),
    )
    mt5_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MT5_PASSWORD", "mt5_password"),
    )
    mt5_server: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MT5_SERVER", "mt5_server"),
    )
    mt5_terminal_path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("MT5_TERMINAL_PATH", "mt5_terminal_path"),
    )

    mt5_rpyc_host: str = Field(
        default="localhost",
        validation_alias=AliasChoices("MT5_RPYC_HOST", "mt5_rpyc_host"),
    )
    mt5_rpyc_port: int = Field(
        default=18812,
        validation_alias=AliasChoices("MT5_RPYC_PORT", "mt5_rpyc_port"),
    )

    wineprefix: Path = Field(
        default_factory=lambda: Path.home() / ".mt5",
        validation_alias=AliasChoices("WINEPREFIX", "wineprefix"),
    )
    winearch: str = Field(
        default="win64",
        validation_alias=AliasChoices("WINEARCH", "winearch"),
    )

    # Backend: "file" (MQL5 EA bridge — recommended on Wine) or "rpyc" (mt5linux)
    mt5_backend: str = Field(
        default="file",
        validation_alias=AliasChoices("MT5_BACKEND", "mt5_backend"),
    )
    mt5_bridge_dir: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("MT5_BRIDGE_DIR", "mt5_bridge_dir"),
    )
    mt5_bridge_max_age: float = Field(
        default=15.0,
        validation_alias=AliasChoices("MT5_BRIDGE_MAX_AGE", "mt5_bridge_max_age"),
    )
    broker: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MT5_BROKER", "BROKER", "mt5_broker", "broker"),
    )

    @field_validator("mt5_terminal_path", "wineprefix", "mt5_bridge_dir", mode="before")
    @classmethod
    def expand_paths(cls, value: object) -> object:
        if value is None or value == "":
            return None if value == "" else value
        # Windows-style paths (C:\...) must not go through Path.resolve on Linux
        if isinstance(value, str) and (value.startswith("C:") or value.startswith("c:")):
            return value
        expanded = _expand_path(value)  # type: ignore[arg-type]
        return expanded

    def has_credentials(self) -> bool:
        return bool(self.mt5_login and self.mt5_password and self.mt5_server)

    def redacted_summary(self) -> dict[str, object]:
        return {
            "mt5_backend": self.mt5_backend or "file",
            "mt5_login": self.mt5_login,
            "mt5_password": "***" if self.mt5_password else None,
            "mt5_server": self.mt5_server,
            "mt5_rpyc_host": self.mt5_rpyc_host,
            "mt5_rpyc_port": self.mt5_rpyc_port,
            "mt5_bridge_dir": str(self.mt5_bridge_dir) if self.mt5_bridge_dir else None,
            "mt5_bridge_max_age": self.mt5_bridge_max_age,
            "wineprefix": str(self.wineprefix),
            "mt5_terminal_path": str(self.mt5_terminal_path) if self.mt5_terminal_path else None,
            "broker": self.broker,
        }
