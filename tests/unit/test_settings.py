"""Tests for configuration settings."""

from multiomics_explorer.config.settings import Settings


def test_default_settings():
    """Default settings should have sensible values."""
    # _env_file=None isolates from a developer's local .env (which legitimately
    # points at a real, possibly remote KG) so this tests true code defaults.
    s = Settings(_env_file=None)
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.neo4j_database == "neo4j"
    assert s.neo4j_auth is None  # no username/password by default


def test_neo4j_auth_when_set():
    """Auth tuple should be returned when username and password are both set."""
    s = Settings(neo4j_username="neo4j", neo4j_password="test")
    assert s.neo4j_auth == ("neo4j", "test")


def test_kg_repo_path_none_by_default():
    """KG repo path should be None by default."""
    s = Settings(_env_file=None)  # isolate from local .env (see test_default_settings)
    assert s.kg_repo is None


def test_settings_from_env_neo4j_username(monkeypatch):
    """NEO4J_USERNAME (canonical) should populate neo4j_username."""
    monkeypatch.setenv("NEO4J_URI", "bolt://remotehost:7687")
    monkeypatch.setenv("NEO4J_USERNAME", "explorer")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    s = Settings()
    assert s.neo4j_uri == "bolt://remotehost:7687"
    assert s.neo4j_username == "explorer"
    assert s.neo4j_auth == ("explorer", "secret")


def test_settings_from_env_neo4j_user_alias(monkeypatch):
    """NEO4J_USER (back-compat alias) should still populate neo4j_username."""
    monkeypatch.setenv("NEO4J_USER", "explorer")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    s = Settings()
    assert s.neo4j_username == "explorer"
    assert s.neo4j_auth == ("explorer", "secret")


def test_neo4j_database_from_env(monkeypatch):
    """NEO4J_DATABASE should override the default."""
    monkeypatch.setenv("NEO4J_DATABASE", "research")
    s = Settings()
    assert s.neo4j_database == "research"
