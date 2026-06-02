"""Application settings loaded from environment variables / .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration for the multiomics explorer."""

    # Neo4j connection. NEO4J_USERNAME is the canonical name (Neo4j BKM —
    # matches the Aura "Connect" credential file). NEO4J_USER is accepted
    # as a back-compat alias.
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = Field(
        default="",
        validation_alias=AliasChoices("NEO4J_USERNAME", "NEO4J_USER"),
    )
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    # Optional: path to KG builder repo for richer schema metadata
    kg_repo_path: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "populate_by_name": True,
    }

    @property
    def neo4j_auth(self) -> tuple[str, str] | None:
        """Return auth tuple for Neo4j driver, or None if no auth configured."""
        if self.neo4j_username and self.neo4j_password:
            return (self.neo4j_username, self.neo4j_password)
        return None

    @property
    def kg_repo(self) -> Path | None:
        """Return Path to KG repo if configured and exists."""
        if self.kg_repo_path:
            p = Path(self.kg_repo_path)
            if p.exists():
                return p
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
