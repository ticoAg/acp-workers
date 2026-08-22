import pytest


@pytest.fixture(autouse=True)
def _cli_json(monkeypatch) -> None:
    """Existing tests parse stdout as JSON. Markdown coverage lives in test_output.py."""
    monkeypatch.setenv("ACPW_OUTPUT", "json")
