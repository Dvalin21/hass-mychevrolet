"""Tests that load the myChevrolet integration end to end.

Network calls to the OnStar cloud are mocked; the real config flow,
coordinator, and every platform are exercised.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mychevrolet.const import DOMAIN

ENTRY_DATA = {
    CONF_USERNAME: "user@example.com",
    CONF_PASSWORD: "secret",
    "vin": "1HGABC1234567890X",
    "device_id": "test-device-id",
    "onstar_pin": "",
}

# A diagnostics response shaped exactly like the verified pyonstar contract:
# onstar.diagnostics() returns {commandResponse: {status, body: {diagnosticResponse}}}.
# The coordinator stores this verbatim under data["diagnostics"], and helpers walk
# data["diagnostics"]["commandResponse"]["body"]["diagnosticResponse"].
DIAGNOSTICS = {
    "commandResponse": {
        "status": "SUCCESS",
        "body": {
            "diagnosticResponse": [
                {
                    "name": "ODOMETER",
                    "diagnosticElement": [{"name": "ODOMETER", "value": 42000.5}],
                },
                {
                    "name": "TIRE PRESSURE",
                    "diagnosticElement": [
                        {"name": "TIRE PRESSURE LF", "value": 230, "message": "OK"},
                        {"name": "TIRE PRESSURE RF", "value": 235},
                        {"name": "TIRE PRESSURE LR", "value": 228},
                        {"name": "TIRE PRESSURE RR", "value": 232},
                    ],
                },
                {
                    "name": "LAST TRIP ELECTRIC ECON",
                    "diagnosticElement": [{"name": "LAST TRIP ELECTRIC ECON", "value": 3.2}],
                },
            ]
        },
    }
}

# An EV advertises an EV BATTERY LEVEL diagnostic, so EV-only sensors appear.
EV_DIAGNOSTICS = {
    "commandResponse": {
        "body": {
            "diagnosticResponse": [
                {
                    "name": "EV BATTERY LEVEL",
                    "diagnosticElement": [{"name": "EV BATTERY LEVEL", "value": 78}],
                },
                {
                    "name": "EV CHARGE STATE",
                    "diagnosticElement": [{"name": "EV CHARGE STATE", "value": "charging"}],
                },
                {
                    "name": "EV PLUG STATE",
                    "diagnosticElement": [{"name": "EV PLUG STATE", "value": "plugged"}],
                },
                {
                    "name": "EV PLUG VOLTAGE",
                    "diagnosticElement": [{"name": "EV PLUG VOLTAGE", "value": 230.4}],
                },
                {
                    "name": "CHARGER POWER LEVEL",
                    "diagnosticElement": [{"name": "CHARGER POWER LEVEL", "value": "level_2"}],
                },
                {
                    "name": "VEHICLE RANGE",
                    "diagnosticElement": [{"name": "VEHICLE RANGE", "value": 210.0}],
                },
                {
                    "name": "ODOMETER",
                    "diagnosticElement": [{"name": "ODOMETER", "value": 42000.5}],
                },
                {
                    "name": "TIRE PRESSURE",
                    "diagnosticElement": [
                        {"name": "TIRE PRESSURE LF", "value": 230},
                        {"name": "TIRE PRESSURE RF", "value": 235},
                        {"name": "TIRE PRESSURE LR", "value": 228},
                        {"name": "TIRE PRESSURE RR", "value": 232},
                    ],
                },
            ]
        }
    }
}

# onstar.location() returns {commandResponse: {body: {location: {...}}}}.
LOCATION = {
    "commandResponse": {
        "status": "SUCCESS",
        "body": {"location": {"latitude": 37.7749, "longitude": -122.4194, "heading": 90}},
    }
}

VEHICLE_DATA = {
    "vin": "1HGABC1234567890X",
    "name": "My Bolt",
    "commands": {"command": [{"name": "start", "url": "/start"}, {"name": "alert", "url": "/alert"}]},
}


def _make_onstar() -> MagicMock:
    """Build a fake OnStar client whose async methods return canned data."""
    onstar = MagicMock()
    onstar.get_account_vehicles = AsyncMock(return_value={"vehicles": {"vehicle": [VEHICLE_DATA]}})
    onstar.get_vehicle_data = MagicMock(return_value=VEHICLE_DATA)
    onstar.is_command_available = MagicMock(
        side_effect=lambda name: name in ("start", "alert", "cancelStart", "lockDoor", "unlockDoor")
    )
    onstar.location = AsyncMock(return_value=LOCATION)
    onstar.diagnostics = AsyncMock(return_value=EV_DIAGNOSTICS)
    onstar.lock_door = AsyncMock(return_value={})
    onstar.unlock_door = AsyncMock(return_value={})
    onstar.start = AsyncMock(return_value={})
    onstar.cancel_start = AsyncMock(return_value={})
    onstar.alert = AsyncMock(return_value={})
    onstar.close = AsyncMock(return_value=None)
    return onstar


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in every test."""
    yield


@pytest.fixture
def mock_onstar():
    """Patch pyonstar.OnStar so no real network/credentials are needed.

    Yields the client instance so tests can assert on its awaited calls.
    """
    instance = _make_onstar()
    with patch("custom_components.mychevrolet.OnStar", return_value=instance):
        yield instance


async def _create_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="My Bolt (1HGABC1234567890X)")
    entry.add_to_hass(hass)
    return entry


async def test_config_flow_creates_entry(hass: HomeAssistant, mock_onstar) -> None:
    """The user flow validates credentials and creates a unique-id entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    with patch(
        "custom_components.mychevrolet.config_flow._validate",
        return_value="My Bolt (1HGABC1234567890X)",
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "user@example.com",
                CONF_PASSWORD: "secret",
                "vin": "1HGABC1234567890X",
            },
        )
    assert result2["type"] == "create_entry"
    assert result2["result"].unique_id == "1HGABC1234567890X"


async def test_setup_creates_entities(hass: HomeAssistant, mock_onstar) -> None:
    """Setup produces the expected entities across all platforms."""
    real_entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="My Bolt (1HGABC1234567890X)")
    real_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(real_entry.entry_id)
    await hass.async_block_till_done()

    states = {s.entity_id: s for s in hass.states.async_all()}
    # Entity IDs are derived from the device title, so match by suffix. The
    # device_tracker is the documented exception: ScannerEntity sets
    # use_device_name=False, so it is exactly "device_tracker.location".
    def _state(suffix: str):
        for entity_id, state in states.items():
            if entity_id.endswith(suffix):
                return state
        return None

    assert _state("_odometer") is not None
    assert _state("_odometer").state == "42000.5"
    # EV-only sensors appear because an EV BATTERY LEVEL diagnostic is present.
    assert _state("_battery_level") is not None
    assert _state("_charge_state") is not None
    assert _state("_plugged_in") is not None
    assert "device_tracker.location" in states
    assert _state("_door_lock") is not None
    # Buttons: refresh always; honk_flash + remote_start because commands are available.
    assert _state("_update_data") is not None
    assert _state("_honk_flash") is not None
    assert _state("_remote_start") is not None


async def test_setup_unloads(hass: HomeAssistant, mock_onstar) -> None:
    """Unloading tears the entry down and closes the OnStar client."""
    real_entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="My Bolt")
    real_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(real_entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(real_entry.entry_id)
    await hass.async_block_till_done()
    assert real_entry.state is not None
    assert mock_onstar.close.await_count == 1


async def test_lock_entity_calls_commands(hass: HomeAssistant, mock_onstar) -> None:
    """Lock/unlock entities invoke the coordinator commands."""
    real_entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="My Bolt")
    real_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(real_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "lock", "lock", {"entity_id": "lock.my_bolt_door_lock"}, blocking=True
    )
    await hass.services.async_call(
        "lock", "unlock", {"entity_id": "lock.my_bolt_door_lock"}, blocking=True
    )
    assert mock_onstar.lock_door.await_count == 1
    assert mock_onstar.unlock_door.await_count == 1
