"""Tests for gateway response decoding."""

import json

import pytest

from custom_components.ot_pi_climate.gateway import OpenThermGateway


def test_decode_snapshot_with_shell_prefix() -> None:
    snapshot = OpenThermGateway._decode_snapshot('otgw> {"Tout":42.5,"Flame":true,"DHW":true}')

    assert snapshot["Tout"] == 42.5
    assert snapshot["Flame"] is True


@pytest.mark.parametrize("response", ["", "ok", '{"Tout":42}'])
def test_decode_snapshot_rejects_invalid_data(response: str) -> None:
    with pytest.raises(json.JSONDecodeError):
        OpenThermGateway._decode_snapshot(response)
