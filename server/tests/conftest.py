"""Shared test fixtures – mocks the Supabase client so tests run without real credentials."""
import pytest
from unittest.mock import patch, MagicMock


def _make_supabase_mock():
    """Build a chainable Supabase MagicMock that returns empty data by default."""
    mock_sb = MagicMock()

    class _Result:
        data = []

    result = _Result()

    # Every chain ends with .execute() or .maybe_single().execute() returning a result object
    chain = MagicMock()
    chain.execute.return_value = result
    chain.maybe_single.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.range.return_value = chain
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.delete.return_value = chain
    chain.upsert.return_value = chain

    table_mock = MagicMock()
    table_mock.select.return_value = chain
    table_mock.insert.return_value = chain
    table_mock.update.return_value = chain
    table_mock.delete.return_value = chain
    table_mock.upsert.return_value = chain

    mock_sb.table.return_value = table_mock
    return mock_sb


@pytest.fixture
def test_db():
    """Patch the Supabase client at the point where models import it."""
    mock_sb = _make_supabase_mock()
    # Patch at the source module so all importers see the mock
    with patch("database.supabase_client.get_sb", return_value=mock_sb), \
         patch("database.supabase_client._client", mock_sb):
        yield mock_sb
