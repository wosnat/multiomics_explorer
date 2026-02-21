"""Application settings loaded from environment variables / .env file."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration for the multiomics explorer agent."""

    # Neo4j connection
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = ""
    neo4j_password: str = ""

    # LLM configuration (used with langchain init_chat_model)
    model: str = "claude-sonnet-4-5-20250929"
    model_provider: str = "anthropic"
    model_temperature: float = 0.0

    # API keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Optional: path to KG builder repo for richer schema metadata
    kg_repo_path: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def neo4j_auth(self) -> tuple[str, str] | None:
        """Return auth tuple for Neo4j driver, or None if no auth configured."""
        if self.neo4j_user and self.neo4j_password:
            return (self.neo4j_user, self.neo4j_password)
        return None

    @property
    def kg_repo(self) -> Path | None:
        """Return Path to KG repo if configured and exists."""
        if self.kg_repo_path:
            p = Path(self.kg_repo_path)
            if p.exists():
                return p
        return None


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
