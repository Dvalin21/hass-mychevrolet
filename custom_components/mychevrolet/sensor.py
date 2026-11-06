"""Sensor platform for myChevrolet."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfPressure,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .entity import MyChevroletEntity
from .helpers import get_diagnostic_value, get_diagnostics, is_ev

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass, entry, async_add_entities
) -> None:  # type: ignore[no-untyped-def]
    """Set up sensors from the diagnostics the vehicle supports."""
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    vin = entry.data["vin"]

    sensors: list[SensorEntity] = [MyChevroletOdometer(coordinator, vin)]

    # Integration health sensor — always present, reflects coordinator health.
    sensors.append(MyChevroletHealthSensor(coordinator, vin))

    diagnostics = get_diagnostics(coordinator.data)
    ev = is_ev(diagnostics)
    if ev:
        sensors += [
            MyChevroletSensor(coordinator, vin, "battery_level", "Battery Level",
                              PERCENTAGE, SensorDeviceClass.BATTERY, SensorStateClass.MEASUREMENT),
            MyChevroletSensor(coordinator, vin, "charge_state", "Charge State",
                              None, SensorDeviceClass.ENUM, None,
                              options=["charging", "not_charging", "fully_charged", "unknown"]),
            MyChevroletSensor(coordinator, vin, "plug_state", "Plug State",
                              None, SensorDeviceClass.ENUM, None,
                              options=["plugged", "unplugged", "unknown"]),
            MyChevroletSensor(coordinator, vin, "plug_voltage", "Plug Voltage",
                              UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                              SensorStateClass.MEASUREMENT),
            MyChevroletSensor(coordinator, vin, "charger_power_level", "Charger Power Level",
                              None, SensorDeviceClass.ENUM, None),
            MyChevroletSensor(coordinator, vin, "ev_range", "EV Range",
                              UnitOfLength.KILOMETERS, SensorDeviceClass.DISTANCE,
                              SensorStateClass.MEASUREMENT),
        ]

    sensors += [
        MyChevroletSensor(coordinator, vin, "last_trip_efficiency", "Last Trip Efficiency",
                          None, None, SensorStateClass.MEASUREMENT),
        MyChevroletTirePressure(coordinator, vin, "lf", "Left Front"),
        MyChevroletTirePressure(coordinator, vin, "rf", "Right Front"),
        MyChevroletTirePressure(coordinator, vin, "lr", "Left Rear"),
        MyChevroletTirePressure(coordinator, vin, "rr", "Right Rear"),
    ]

    async_add_entities(sensors)


class MyChevroletOdometer(MyChevroletEntity, SensorEntity):
    """Odometer reading, available on every vehicle."""

    _attr_name = "Odometer"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, vin):  # type: ignore[no-untyped-def]
        super().__init__(coordinator, "odometer", "Odometer")

    @property
    def native_value(self) -> float | None:
        """Return the odometer value."""
        value = get_diagnostic_value(
            get_diagnostics(self.coordinator.data), "ODOMETER"
        )
        return _to_float(value)


class MyChevroletSensor(MyChevroletEntity, SensorEntity):
    """A diagnostic-backed sensor with a fixed name/unit/device class."""

    def __init__(
        self,
        coordinator,  # type: ignore[no-untyped-def]
        vin,
        unique_id,
        name,
        unit,
        device_class,
        state_class,
        options=None,
    ):
        super().__init__(coordinator, unique_id, name)
        self._diagnostic = unique_id.upper()
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        if options is not None:
            self._attr_options = options

    @property
    def native_value(self) -> Any:
        """Return the diagnostic value, mapped for enum sensors."""
        diagnostics = get_diagnostics(self.coordinator.data)
        if self._attr_device_class is SensorDeviceClass.ENUM:
            return _enum(self._diagnostic, diagnostics)
        return _to_float(get_diagnostic_value(diagnostics, self._diagnostic))


class MyChevroletTirePressure(MyChevroletEntity, SensorEntity):
    """Per-wheel tire pressure."""

    _attr_native_unit_of_measurement = UnitOfPressure.KPA
    _attr_device_class = SensorDeviceClass.PRESSURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, vin, position, position_name):  # type: ignore[no-untyped-def]
        super().__init__(coordinator, f"tire_pressure_{position}", f"Tire Pressure {position_name}")
        self._position = position.upper()

    @property
    def native_value(self) -> float | None:
        """Return this wheel's pressure."""
        diagnostics = get_diagnostics(self.coordinator.data)
        return _to_float(
            get_diagnostic_value(diagnostics, "TIRE PRESSURE", f"TIRE PRESSURE {self._position}")
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attach the raw status text when present."""
        diagnostics = get_diagnostics(self.coordinator.data)
        if not diagnostics:
            return {}
        for diagnostic in diagnostics:
            if diagnostic.get("name") == "TIRE PRESSURE":
                for element in diagnostic.get("diagnosticElement", []):
                    if element.get("name") == f"TIRE PRESSURE {self._position}":
                        message = element.get("message")
                        return {"status": message} if message else {}
        return {}


def _to_float(value: Any) -> float | None:
    """Coerce a numeric diagnostic value to float, or None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _enum(name: str, diagnostics) -> str | None:  # type: ignore[no-untyped-def]
    """Normalise an enum-like diagnostic value to a HA-friendly state."""
    from .helpers import get_diagnostic_value

    value = get_diagnostic_value(diagnostics, name)
    if value is None:
        return None
    known = {"charging", "not_charging", "fully_charged", "plugged", "unplugged"}
    lowered = str(value).lower()
    return lowered if lowered in known else "unknown"


class MyChevroletHealthSensor(MyChevroletEntity, SensorEntity):
    """Integration health: last update success and rate-limit status."""

    _attr_name = "Health"
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coordinator, vin):  # type: ignore[no-untyped-def]
        super().__init__(coordinator, "health", "Health")

    @property
    def native_value(self) -> str:
        """Return the integration health state."""
        if self.coordinator.is_rate_limited:
            return "rate_limited"
        if self.coordinator.last_update_success:
            return "ok"
        return "error"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return health detail attributes."""
        attrs: dict[str, Any] = {}
        if self.coordinator.last_successful_update is not None:
            attrs["last_successful_update"] = self.coordinator.last_successful_update
        if self.coordinator.is_rate_limited:
            attrs["rate_limited"] = True
            dbr = self.coordinator.diagnostics_backoff_remaining
            lbr = self.coordinator.location_backoff_remaining
            if dbr is not None:
                attrs["diagnostics_backoff_remaining_seconds"] = round(dbr, 1)
            if lbr is not None:
                attrs["location_backoff_remaining_seconds"] = round(lbr, 1)
        return attrs
