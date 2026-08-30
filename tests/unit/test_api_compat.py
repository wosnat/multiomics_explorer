import warnings
import pytest
from multiomics_explorer.api._compat import deprecated_alias


def test_new_only_passes_through():
    assert deprecated_alias(old=None, new=[1], old_name="publication_doi", new_name="publication_dois") == [1]


def test_old_warns_and_is_used():
    with pytest.warns(DeprecationWarning, match="publication_doi.*publication_dois"):
        out = deprecated_alias(old=["x"], new=None, old_name="publication_doi", new_name="publication_dois")
    assert out == ["x"]


def test_both_raises():
    with pytest.raises(ValueError, match="both"):
        deprecated_alias(old=1, new=2, old_name="min_value", new_name="min_value")


def test_listify_wraps_bare_str():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert deprecated_alias(old=None, new="coculture", old_name="treatment_type", new_name="treatment_type", listify=True) == ["coculture"]
        assert deprecated_alias(old="nitrogen", new=None, old_name="category", new_name="gene_categories", listify=True) == ["nitrogen"]


def test_none_none_is_none():
    assert deprecated_alias(old=None, new=None, old_name="a", new_name="b") is None
