"""Constants for the myChevrolet integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "mychevrolet"
VERSION = "0.1.0"

# Config-entry keys
CONF_VIN = "vin"
CONF_TOTP_SECRET = "totp_secret"
CONF_DEVICE_ID = "device_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_CHEATER_MODE = "cheater_mode"

# Defaults
DEFAULT_SCAN_INTERVAL = 30  # minutes
MIN_SCAN_INTERVAL = 5  # minutes
DEFAULT_CHEATER_MODE = False

# pyonstar command-failure / rate-limit handling
RATE_LIMIT_STATUS_CODE = 429
# Back off a rate-limited endpoint for this long in standard (non-cheater) mode.
# GM's OnStar link is slow and aggressively rate-limited (500 then 429). 30
# minutes is long enough to cool off without losing a whole day of updates.
RATE_LIMIT_BACKOFF = timedelta(minutes=30)
# What the coordinator fetches each cycle. Diagnostics is the expensive,
# rate-limited call (up to ~180s per pyonstar); location is cheap.
UPDATE_TIMEOUT_SECONDS = 240

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.LOCK,
    Platform.SENSOR,
]

# Diagnostic names returned by pyonstar diagnostics() (verbatim from the OnStar
# command set). Sensors key off these; a missing name just yields an unknown
# entity rather than an error.
DIAG_ODOMETER = "ODOMETER"
DIAG_EV_BATTERY_LEVEL = "EV BATTERY LEVEL"
DIAG_EV_CHARGE_STATE = "EV CHARGE STATE"
DIAG_EV_PLUG_STATE = "EV PLUG STATE"
DIAG_EV_PLUG_VOLTAGE = "EV PLUG VOLTAGE"
DIAG_CHARGER_POWER_LEVEL = "CHARGER POWER LEVEL"
DIAG_VEHICLE_RANGE = "VEHICLE RANGE"
DIAG_LAST_TRIP_ECON = "LAST TRIP ELECTRIC ECON"
DIAG_TIRE_PRESSURE = "TIRE PRESSURE"

# Token-file fallback location (relative to HA config). If GM's bot detection
# blocks the automated web login ("Access Denied"), drop a manually captured
# microsoft_tokens.json here (see README) and pyonstar will use it directly.
TOKEN_DIR = ".storage/mychevrolet"
