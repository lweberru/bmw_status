# BMW Status

[Deutsch](README.de.md) | [BMW Status Card frontend](https://github.com/lweberru/bmw_status_card)

BMW Status is the Home Assistant backend integration for the
[BMW Status Card](https://github.com/lweberru/bmw_status_card). They are designed
to be used together: this integration turns the entities supplied by
`bmw-cardata-ha` into a versioned presentation contract, while the card renders
that contract without querying vehicle providers in the browser.

Version: 0.2.5

## Features

- One configuration entry and status sensor per `bmw-cardata-ha` vehicle.
- A versioned `presentation` attribute with vehicle, energy, range, opening,
	tire-pressure, service and climate data.
- Server-side generated and cached vehicle images and MapTiler location maps.
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

The status sensor publishes `attributes.presentation`. Use that attribute only
through the companion card; it is the stable display contract between the
backend and frontend.

## Services

- `bmw_status.refresh`: Refreshes the presentation from the current CarData states.
- `bmw_status.regenerate_images`: Regenerates cached visual assets for an entry.
- `bmw_status.clear_image_cache`: Clears only the local asset cache for an entry.

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