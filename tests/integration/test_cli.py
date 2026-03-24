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

    def test_cypher_write_blocked(self):
        result = runner.invoke(app, ["cypher", "CREATE (n:Test)"])
        assert result.exit_code == 1
        assert "Write operations" in result.stdout

    def test_cypher_syntax_error(self):
        result = runner.invoke(app, ["cypher", "MATC (n) RETURNN n"])
        assert result.exit_code == 1
        assert "Syntax error" in result.stdout

    def test_cypher_bad_label_shows_warning(self):
        result = runner.invoke(app, ["cypher", "MATCH (n:NonExistentLabel_XYZ) RETURN n LIMIT 1"])
        assert result.exit_code == 0
        assert "Warning" in result.stdout

    def test_cypher_truncated_message(self):
        result = runner.invoke(app, ["cypher", "MATCH (g:Gene) RETURN g.locus_tag AS tag", "--limit", "1"])
        assert result.exit_code == 0
        assert "more" in result.stdout

    def test_cypher_json_output(self):
        result = runner.invoke(app, ["cypher", "MATCH (g:Gene) RETURN count(g) AS cnt", "--json"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert "cnt" in data[0]

    def test_schema_validate(self):
        result = runner.invoke(app, ["schema-validate"])
        # May pass or show diffs — should not crash
        assert result.exit_code in (0, 1)
