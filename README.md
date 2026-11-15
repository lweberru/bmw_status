# BMW Status

[Deutsch](README.de.md) | [BMW Status Card frontend](https://github.com/lweberru/bmw_status_card)

BMW Status is the Home Assistant backend integration for the
[BMW Status Card](https://github.com/lweberru/bmw_status_card). They are designed
to be used together: this integration turns the entities supplied by
`bmw-cardata-ha` into a versioned presentation contract, while the card renders
that contract without querying vehicle providers in the browser.

Version: 0.4.0

## Features

- One configuration entry and status sensor per `bmw-cardata-ha` vehicle.
- A versioned `presentation` attribute with vehicle, energy, range, opening,
	tire-pressure, service and climate data.
- Server-side generated and cached vehicle images and MapTiler location maps.
- Generated vehicle images use season, time of day and broad Open-Meteo weather
	categories such as sun, rain or snow. Temperature, precipitation amounts and
	location names do not affect the image prompt or trigger regeneration.
- MapTiler and image-provider credentials remain in the backend configuration;
	they are never exposed to the browser or published through the sensor.
- Services to refresh data and manage cached image assets.

## Requirements

1. Install and configure `bmw-cardata-ha` with at least one vehicle.
2. Install this repository through HACS as an **Integration**.
3. Install the companion [BMW Status Card frontend](https://github.com/lweberru/bmw_status_card)
	 through HACS as a **Frontend** plugin.

## Setup

1. In Home Assistant, open **Settings → Devices & services → Add integration**.
2. Select **BMW Status**.
3. Select the CarData vehicle and configure the optional vehicle details.
4. Configure server-side map and image providers when required.
5. Add a BMW Status Card for the generated sensor, for example `sensor.status`.

OpenAI image generation can be selected in the integration options using an
OpenAI project API key. Switching providers resets the previous key, model, and
size. The default is `gpt-image-2.5-flare` at `1024x1024`, requested as PNG with
`low` quality to keep costs down. The model remains configurable. Existing model
settings are preserved; replace `gpt-image-1` in the options if previously saved.
API credit is required; a ChatGPT login alone does not authorize these requests.

The latest cached vehicle image stays visible while a new scene is generated
or the image provider is unavailable. Changes to telemetry that do not affect
the image prompt reuse the existing render.

The status sensor publishes `attributes.presentation`. Use that attribute only
through the companion card; it is the stable display contract between the
backend and frontend.

## Fuel consumption

Setup and integration options include a **Fuel consumption** step (currently
labelled **Spritverbrauch**). Tank-level and odometer sensors are detected on the
selected vehicle, or can be selected explicitly. Supported units are L or %
and km or mi. Percentage levels require the tank capacity in liters.

Enter lifetime fuel already consumed **before the integration's first sample**
as `initial_total_liters`. Lifetime distance uses the initial odometer plus
observed distance. Without that historical fuel baseline, lifetime consumption
stays unknown. Optionally provide both liters and kilometers since the previous
refueling at that same starting point; otherwise the first tank period is
marked incomplete. Refueling is inferred from a rise of at least 5 L by default;
the threshold is configurable and partial refills are supported.

The existing status sensor adds `presentation.fuel_consumption`, containing
`total`, `since_refuel` and `today`, each with `liters`, `distance_km`,
`average_l_per_100km` and `incomplete`. It also publishes tracking start,
last detected refill time/amount and explicit `issues`. Unknown values are
`null`; an average without distance is not fabricated.

These are **tank-level estimates**, not exact trip-computer or pump readings.
Small refills, sensor resolution and consumption hidden between reports limit
accuracy. Deltas belong to their observation day in Home Assistant's timezone;
cross-midnight deltas cannot be split accurately without intermediate samples.
Daily counters roll over at midnight even while parked.

Counters and references persist per config entry in Home Assistant storage,
restore before the first refresh and survive image-cache clearing. Options
changes reload the entry. Historical baselines always refer to the original
tracking start shown in the card, including when edited later; they are not
added again on restart. Tank-period baselines apply only before the first
detected refill. Changing sensors or percentage tank capacity re-baselines
the affected measurement without resetting totals and marks coverage incomplete.

## Services

- `bmw_status.refresh`: Refreshes the presentation from the current CarData states.
- `bmw_status.regenerate_images`: Regenerates cached visual assets for an entry.
- `bmw_status.clear_image_cache`: Clears only the local asset cache for an entry.

When image generation is enabled, Open-Meteo is queried with the current BMW
tracker coordinates and cached for 15 minutes. Configure the optional Google
Geocode entity in the image-generation settings to add a readable location to
the prompt. If the geocode entity or weather service is unavailable, image
generation continues with the remaining context.

All services accept an optional `entry_id`, which is useful with multiple vehicles.

## Local development

The dev container starts Home Assistant at `http://localhost:8123` with a local,
production-shaped CarData fixture.

1. Open the `bmw_status` folder in VS Code and choose **Reopen in Container**.
2. Open `http://localhost:8123` and complete Home Assistant onboarding.
3. Add **BMW Status** and select the fixture vehicle.
4. Open `http://localhost:8123/lovelace/fahrzeug` to inspect the companion card.

The fixture supports `parked`, `driving` and `attention` scenarios through the
`cardata.set_fixture_scenario` action. It is intentionally local only and is not
needed for production installation.
