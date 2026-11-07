"""Type definitions for OnStar client."""
from enum import Enum
from typing import List, TypedDict


class CommandResponseStatus(Enum):
    """Command response status values."""
    SUCCESS = "success"
    FAILURE = "failure"
    IN_PROGRESS = "inProgress"
    PENDING = "pending"


class AlertRequestAction(Enum):
    """Alert request actions."""
    HONK = "Honk"
    FLASH = "Flash"


class AlertRequestOverride(Enum):
    """Alert request overrides."""
    DOOR_OPEN = "DoorOpen"
    IGNITION_ON = "IgnitionOn"


class ChargeOverrideMode(Enum):
    """Charge override modes."""
    CHARGE_NOW = "CHARGE_NOW"
    CANCEL_OVERRIDE = "CANCEL_OVERRIDE"


class ChargingProfileChargeMode(Enum):
    """Charging profile charge modes."""
    DEFAULT_IMMEDIATE = "DEFAULT_IMMEDIATE"
    IMMEDIATE = "IMMEDIATE"
    DEPARTURE_BASED = "DEPARTURE_BASED"
    RATE_BASED = "RATE_BASED"
    PHEV_AFTER_MIDNIGHT = "PHEV_AFTER_MIDNIGHT"


class ChargingProfileRateType(Enum):
    """Charging profile rate types."""
    OFFPEAK = "OFFPEAK"
    MIDPEAK = "MIDPEAK"
    PEAK = "PEAK"


class DiagnosticRequestItem(Enum):
    """Diagnostic request items."""
    AMBIENT_AIR_TEMPERATURE = "AMBIENT AIR TEMPERATURE"
    ENGINE_COOLANT_TEMP = "ENGINE COOLANT TEMP"
    ENGINE_RPM = "ENGINE RPM"
    EV_BATTERY_LEVEL = "EV BATTERY LEVEL"
    EV_CHARGE_STATE = "EV CHARGE STATE"
    EV_ESTIMATED_CHARGE_END = "EV ESTIMATED CHARGE END"
    EV_PLUG_STATE = "EV PLUG STATE"
    EV_PLUG_VOLTAGE = "EV PLUG VOLTAGE"
    EV_SCHEDULED_CHARGE_START = "EV SCHEDULED CHARGE START"
    FUEL_TANK_INFO = "FUEL TANK INFO"
    GET_CHARGE_MODE = "GET CHARGE MODE"
    GET_COMMUTE_SCHEDULE = "GET COMMUTE SCHEDULE"
    HANDS_FREE_CALLING = "HANDS FREE CALLING"
    HOTSPOT_CONFIG = "HOTSPOT CONFIG"
    HOTSPOT_STATUS = "HOTSPOT STATUS"
    INTERM_VOLT_BATT_VOLT = "INTERM VOLT BATT VOLT"
    LAST_TRIP_DISTANCE = "LAST TRIP DISTANCE"
    LAST_TRIP_FUEL_ECONOMY = "LAST TRIP FUEL ECONOMY"
    LIFETIME_EV_ODOMETER = "LIFETIME EV ODOMETER"
    LIFETIME_FUEL_ECON = "LIFETIME FUEL ECON"
    LIFETIME_FUEL_USED = "LIFETIME FUEL USED"
    ODOMETER = "ODOMETER"
    OIL_LIFE = "OIL LIFE"
    TIRE_PRESSURE = "TIRE PRESSURE"
    VEHICLE_RANGE = "VEHICLE RANGE"


class DoorRequestOptions(TypedDict, total=False):
    """Door request options."""
    delay: int


class TrunkRequestOptions(TypedDict, total=False):
    """Trunk request options."""
    delay: int


class AlertRequestOptions(TypedDict, total=False):
    """Alert request options."""
    action: List[AlertRequestAction]
    delay: int
    duration: int
    override: List[AlertRequestOverride]


class ChargeOverrideOptions(TypedDict, total=False):
    """Charge override options."""
    mode: ChargeOverrideMode


class SetChargingProfileRequestOptions(TypedDict, total=False):
    """Set charging profile request options."""
    charge_mode: ChargingProfileChargeMode
    rate_type: ChargingProfileRateType


class DiagnosticsRequestOptions(TypedDict, total=False):
    """Diagnostics request options."""
    diagnostic_item: List[str] 