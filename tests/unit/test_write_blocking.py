"""P0: Tests for write-blocking in run_cypher."""

import re

import pytest

from multiomics_explorer.api.functions import _WRITE_KEYWORDS


class TestWriteBlocking:
    """Verify _WRITE_KEYWORDS regex blocks all write operations."""

    @pytest.mark.parametrize("keyword", [
        "CREATE", "DELETE", "MERGE", "SET", "REMOVE", "DROP",
        "create", "delete", "merge", "set", "remove", "drop",
    ])
    def test_blocks_write_keyword(self, keyword):
        query = f"{keyword} (n:Gene {{name: 'x'}})"
        assert _WRITE_KEYWORDS.search(query), f"Should block '{keyword}'"

    def test_blocks_detach_delete(self):
        query = "MATCH (n) DETACH DELETE n"
        assert _WRITE_KEYWORDS.search(query)

    def test_blocks_call_subquery(self):
        query = "CALL { CREATE (n:Gene) }"
        assert _WRITE_KEYWORDS.search(query)

    def test_allows_plain_read(self):
        query = "MATCH (g:Gene) RETURN g.locus_tag LIMIT 10"
        assert _WRITE_KEYWORDS.search(query) is None

    def test_allows_contains_set_in_string(self):
        """Reads with 'SET' as a substring in a property value should pass."""
        query = 'MATCH (g:Gene) WHERE g.product CONTAINS "RESET" RETURN g'
        # 'RESET' contains 'SET' but as a substring, not a word boundary
        assert _WRITE_KEYWORDS.search(query) is None

    def test_allows_description_with_remove(self):
        """Property values containing write-keyword substrings should be OK."""
        query = 'MATCH (g:Gene) WHERE g.product CONTAINS "REMOVED" RETURN g'
        assert _WRITE_KEYWORDS.search(query) is None

    def test_blocks_set_as_word(self):
        query = "MATCH (n:Gene) SET n.name = 'x'"
        assert _WRITE_KEYWORDS.search(query)

    def test_blocks_mixed_case(self):
        query = "MATCH (n) DeLeTe n"
        assert _WRITE_KEYWORDS.search(query)

    def test_blocks_multiline_query(self):
        query = "MATCH (n)\nDELETE n"
        assert _WRITE_KEYWORDS.search(query)
