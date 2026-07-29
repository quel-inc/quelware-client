import pytest
import typer

from quelware_client.cli.unit_config import _parse_controls


def test_parses_key_value_pairs() -> None:
    assert _parse_controls(["quel3.monitor.mode=loopback"]) == {
        "quel3.monitor.mode": "loopback"
    }


def test_keeps_equals_in_value() -> None:
    assert _parse_controls(["a=b=c"]) == {"a": "b=c"}


def test_multiple_pairs() -> None:
    assert _parse_controls(["a=1", "b=2"]) == {"a": "1", "b": "2"}


@pytest.mark.parametrize("bad", ["noequals", "=value"])
def test_rejects_malformed(bad: str) -> None:
    with pytest.raises(typer.BadParameter):
        _parse_controls([bad])
