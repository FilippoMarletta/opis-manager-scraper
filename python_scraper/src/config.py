import os
from dataclasses import dataclass, field
from typing import Dict, List

from dotenv import load_dotenv


# API


@dataclass(frozen=True)
class RetryConfig:
    total: int = 3
    backoff_factor: int = 2
    status_forcelist: List[int] = field(
        default_factory=lambda: [429, 500, 502, 503, 504]
    )
    allowed_methods: List[str] = field(default_factory=lambda: ["POST"])


@dataclass(frozen=True)
class ApiConfig:
    base_url: str = "https://public.smartedu.unict.it/EnqaDataViewer"
    timeout: int = 120
    headers: Dict[str, str] = field(
        default_factory=lambda: {
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
    )
    retry: RetryConfig = field(default_factory=RetryConfig)


# DATABASE


@dataclass(frozen=True)
class DbConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "opis_manager"

    @classmethod
    def from_env(cls) -> "DbConfig":
        """Factory method for creating a database configuration by reading environment variables."""
        load_dotenv()
        return cls(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "opis_manager"),
        )


# SCRAPER


@dataclass(frozen=True)
class ScraperConfig:
    academic_years: tuple[int, ...] = (2021, 2022, 2023, 2024)
    delay: float = 1.0
    max_workers: int = 3
    debug_mode: bool = False

    @classmethod
    def from_env(cls) -> "ScraperConfig":
        """Factory method for creating a scraper configuration by reading environment variables."""
        load_dotenv()
        debug = os.getenv("DEBUG_MODE", "false").lower() in ("true", "1", "t")
        return cls(debug_mode=debug)
