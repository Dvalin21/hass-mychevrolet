# myChevrolet for Home Assistant

A Home Assistant integration for **Chevrolet / GMC / Buick / Cadillac plug-in and
electric vehicles** that are enrolled in the **myChevrolet / myGMC / myBuick /
myCadillac** app (US region, OnStar-backed). It exposes battery, charge, range,
odometer, tire-pressure and GPS data as sensors, and door-lock / remote-start /
honk-and-flash as controls — all by polling the same OnStar cloud API the mobile
app uses.

Built on top of [`pyonstar`](https://pypi.org/project/pyonstar/) (a pure-Python
port of the OnStarJS client), so all the hard parts — the Microsoft B2C login,
the GM API token exchange, the two-token caching and the command-status polling
— are handled by a battle-tested dependency rather than re-invented here.

> **Region:** This integration targets the **US** OnStar cloud
> (`na-mobile-api.gm.com`). Vehicles enrolled on a different regional backend
> (LATAM, Europe, etc.) use a different API and are **not** supported.

---

## Table of contents

- [Features](#features)
- [Supported vehicles](#supported-vehicles)
- [Entities](#entities)
- [Requirements](#requirements)
- [Installation](#installation)
  - [Home Assistant install button](#home-assistant-install-button)
  - [Manual install](#manual-install)
- [Configuration](#configuration)
  - [Setup fields](#setup-fields)
  - [Options](#options)
- [Services](#services)
- [How it works](#how-it-works)
  - [Polling model](#polling-model)
  - [Rate limiting and "cheater mode"](#rate-limiting-and-cheater-mode)
  - [Re-authentication](#re-authentication)
  - [Manual token fallback](#manual-token-fallback)
- [Development](#development)
- [Known limitations](#known-limitations)
- [Credits & references](#credits--references)
- [Disclaimer](#disclaimer)

---

## Features

- **Cloud-poll, no local hacks.** Talks to the OnStar cloud exactly like the
  official app. No root, no OBD dongle, no vehicle modification.
- **Config-flow setup.** Credentials are entered through the UI and stored by
  Home Assistant; nothing is hand-written except the optional token fallback.
- **Automatic device & entity registry.** One device per VIN, entities tagged
  with manufacturer/model so they group cleanly in your dashboard.
- **EV-aware.** Electric / plug-in-hybrid vehicles automatically get the extra
  battery, charge-state, plug, charger-power and EV-range sensors; a gasoline
  vehicle simply doesn't expose them.
- **Remote controls.** Lock/unlock doors, remote start/stop, honk & flash, plus a
  one-tap "update data" button — each gated on whether your vehicle's plan
  actually entitles that command.
- **Reauth on expiry.** When GM rotates or revokes tokens and login stops
  working, you get a re-auth prompt instead of a silent break.
- **Integration health.** A `sensor.<vehicle>_health` entity reports `ok`,
  `rate_limited`, or `error`, plus backoff timers and last successful update —
  so you know at a glance when data is stale.

## Supported vehicles

Any US-region vehicle that:

1. Appears in the **myChevrolet** (or myGMC / myBuick / myCadillac) app, and
2. Is enrolled in **OnStar** with data/remote services active.

This covers, for example, the **Bolt EV/EUV**, **Blazer EV**, **Equinox EV**,
**Silverado EV**, **Cadillac Lyriq**, **GMC Hummer EV**, and OnStar-linked
gasoline models. If the app can remote-start or lock your car, this integration
can too.

## Entities

Every entity hangs off a single device named after your vehicle (one per VIN).

| Platform | Entity | Only on | Description |
|---|---|---|---|
| Sensor | Odometer | all | Total distance (km, total-increasing). |
| Sensor | Battery Level | EV | State of charge (%). |
| Sensor | Health | all | Integration health: `ok`, `rate_limited`, or `error`. |
| Sensor | Charge State | EV | `charging` / `not_charging` / `fully_charged`. |
| Sensor | Plug State | EV | `plugged` / `unplugged`. |
| Sensor | Plug Voltage | EV | Available charge voltage (V). |
| Sensor | Charger Power Level | EV | Charge rate tier (e.g. `level_2`). |
| Sensor | EV Range | EV | Estimated driving range (km). |
| Sensor | Last Trip Efficiency | all | Most recent trip economy. |
| Sensor | Tire Pressure LF / RF / LR / RR | all | Per-wheel pressure (kPa) + status text. |
| Binary sensor | Plugged In | EV | On when the vehicle reports plugged in. |
| Device tracker | Location | all | Last GPS position (lat/long/heading/speed/altitude). |
| Lock | Door Lock | all | Lock / unlock the doors. |
| Button | Update Data | all | Force an immediate data refresh. |
| Button | Honk & Flash | all* | Honk and flash the lights. |
| Button | Remote Start | all* | Start the engine / drive unit. |
| Button | Remote Stop | all* | Cancel a running remote start. |

\* *Command buttons only appear if your vehicle's OnStar entitlements include
that command.*

## Requirements

- A **Home Assistant** instance (2023.x or newer recommended).
- A **myChevrolet / OnStar** account (US region) with remote services active.
- The vehicle's **VIN** (17 characters).
- Optional but often required: a **TOTP secret**. GM's login increasingly gates
  automated clients behind a time-based one-time password shown in the app's
  security setup; `pyonstar` supports it. Leave blank if your account doesn't
  use it.

## Installation

### Manual install (required first)

1. Copy the `mychevrolet` folder into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search for
   **myChevrolet**.

### Home Assistant install button (after manual install)

Once the files are in place, click the badge at the top of this page to start
the config flow directly:

[![Install myChevrolet in Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=mychevrolet)

### HACS (card only)

The **integration** is manual install only — it is not in the official Home
Assistant marketplace or HACS default store. Add `mychevrolet` manually as above.

The **card** (`hass-mychevrolet-card`) can be installed via HACS: add
`https://github.com/Dvalin21/hass-mychevrolet-card` as a custom repository
(category: **Frontend**), install **myChevrolet Status Card**, then force-refresh
your browser (`Ctrl+F5`).

Or manually: download `mychevrolet-status-card.js` from the latest release,
place it in `config/www/`, add a resource at `/local/mychevrolet-status-card.js`
(type: `module`), and force-refresh.

## Configuration

Setup is a config-flow form. Enter the account credentials and the target VIN;
the flow validates them against the OnStar cloud before creating the entry.

### Setup fields

| Field | Required | Notes |
|---|---|---|
| Account email | ✔ | Your myChevrolet login email. |
| Password | ✔ | Your myChevrolet password. |
| Vehicle VIN | ✔ | 17-char VIN of the car to add. One integration entry per VIN. |
| TOTP secret | – | Secret from GM's authenticator setup. Required if your account enforces 2FA for automated logins. |
| Device ID | – | Optional UUID identifying this client. Auto-generated if left blank. |
| Account PIN | – | Optional OnStar account PIN. |

### Options

After setup, open the integration's **Configure** dialog:

| Option | Default | Notes |
|---|---|---|
| Poll interval (minutes) | `30` | How often to refresh diagnostics + location. Minimum 5. |
| Cheater mode | `off` | See [below](#rate-limiting-and-cheater-mode). |

> **Why 30 minutes?** `diagnostics` is the slow, rate-limited call (GM's cloud
> can take up to ~180 s to answer and then throttles aggressive clients). Tight
> polling mostly buys you `500`/`429` errors, not fresher data.

## Services

| Service | Description |
|---|---|
| `mychevrolet.refresh_data` | Force an immediate diagnostics + location refresh on every configured vehicle. Useful right after issuing a command. |

## How it works

### Polling model

Each refresh cycle the coordinator:

1. Enumerates the account's vehicles (to read the command/entitlement list), then
2. Requests **location** and **diagnostics** in parallel.

Diagnostics is the rich payload — odometer, battery, charge/plug state, range,
tire pressure, trip economy — parsed in one place (`helpers.py`) so every entity
reads the same response paths.

### Rate limiting and "cheater mode"

GM's OnStar link is slow and aggressively rate-limited. Two strategies are built
in:

- **Standard mode (default):** on a `429`, the coordinator backs off that
  endpoint for **30 minutes** rather than hammering it. Only the endpoint that
  returned `429` is backed off — the other keeps polling.
- **Cheater mode (opt-in):** poll faster (2 min) and, on a `429`, recreate the
  client with a fresh device ID to escape GM's per-device-id rate bucket. The
  new device ID is persisted to your config entry, so it survives an HA
  restart. Enable this only if you hit throttling and understand it trades a
  bit more API traffic for fresher data.

### Re-authentication

`pyonstar` caches a Microsoft identity token and a GM API token under
`.storage/mychevrolet/`. When GM expires or revokes them and a call comes back
`401`/`403`, the config entry triggers a **re-auth** prompt — re-enter your
credentials and everything resumes without re-adding the vehicle.

### Manual token fallback

If GM's bot detection blocks the automated web login (you see `Access Denied`
during setup), you can drop in a token you captured by hand:

1. Log in through the normal flow until it fails.
2. Capture the `microsoft_tokens.json` the client wrote (or a token from a
   working session).
3. Place it at `.storage/mychevrolet/microsoft_tokens.json` in your HA config.

On the next start the client uses the file directly instead of re-running the
login.

## Development

The integration is tested with the Home Assistant test harness
(`pytest-homeassistant-custom-component`), with all OnStar network I/O mocked —
no credentials or live vehicle required.

```bash
python -m venv .venv && . .venv/bin/activate
pip install "pytest-homeassistant-custom-component==0.13.200" "pyonstar==0.0.14"
ruff check custom_components/mychevrolet tests
pytest
```

Tests assert that the config flow creates an entry, every expected entity
appears (including the EV-only ones), lock/remote commands reach the client, and
unload closes the client.

## Known limitations

- **US region only.** Other OnStar backends are unsupported.
- **Polling, not push.** State reflects the last successful poll; there is no
  real-time event stream.
- **No live lock state.** The OnStar diagnostics payload doesn't report a live
  door-lock status, so the lock entity shows an unknown state until a refresh
  confirms it.
- **Login can be fragile.** GM periodically tightens automated-login defenses;
  when that happens, use the manual token fallback above until `pyonstar` is
  updated.

## Credits & references

- [`pyonstar`](https://pypi.org/project/pyonstar/) — the OnStar/myChevrolet API
  client this integration wraps.
- Home Assistant [custom integration
  docs](https://developers.home-assistant.io/docs/creating_component_file_structure)
  and [config-flow
  guide](https://developers.home-assistant.io/docs/creating_custom_config_entries).

## Disclaimer

This is an **unofficial** project for personal use. It is not affiliated with,
endorsed by, or supported by General Motors, OnStar, or Home Assistant. It talks
to a third-party cloud API in a way that may change or be restricted at any time.
Use it at your own risk; the author is not responsible for vehicle damage,
lockouts, or service interruptions.
