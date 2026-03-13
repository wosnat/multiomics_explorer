"""P2: CLI smoke tests against live Neo4j."""

import pytest
from typer.testing import CliRunner

from multiomics_explorer.cli.main import app

runner = CliRunner()


@pytest.mark.kg
class TestCLI:
    def test_schema_exits_zero(self):
        result = runner.invoke(app, ["schema"])
        assert result.exit_code == 0
        assert "Gene" in result.stdout

    def test_schema_json(self):
        result = runner.invoke(app, ["schema", "--json"])
        assert result.exit_code == 0
        assert "Gene" in result.stdout

    def test_stats_exits_zero(self):
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0

    def test_cypher_simple_query(self):
        result = runner.invoke(app, ["cypher", "MATCH (g:Gene) RETURN count(g) AS cnt"])
        assert result.exit_code == 0
        assert "cnt" in result.stdout

    def test_schema_validate(self):
        result = runner.invoke(app, ["schema-validate"])
        # May pass or show diffs — should not crash
        assert result.exit_code in (0, 1)
