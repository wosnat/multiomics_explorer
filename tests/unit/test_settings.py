"""Tests for configuration settings."""

import os

from multiomics_explorer.config.settings import Settings


def test_default_settings():
    """Default settings should have sensible values."""
    s = Settings()
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.model_temperature == 0.0
    assert s.neo4j_auth is None  # no user/password by default


def test_neo4j_auth_when_set():
    """Auth tuple should be returned when user and password are both set."""
    s = Settings(neo4j_user="neo4j", neo4j_password="test")
    assert s.neo4j_auth == ("neo4j", "test")


def test_kg_repo_path_none_by_default():
    """KG repo path should be None by default."""
    s = Settings()
    assert s.kg_repo is None


def test_settings_from_env(monkeypatch):
    """Settings should read from environment variables."""
    monkeypatch.setenv("NEO4J_URI", "bolt://remotehost:7687")
    monkeypatch.setenv("MODEL", "gpt-4o")
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    s = Settings()
    assert s.neo4j_uri == "bolt://remotehost:7687"
    assert s.model == "gpt-4o"
    assert s.model_provider == "openai"
