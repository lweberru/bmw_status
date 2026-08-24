# BMW Status

[English](README.md) | [BMW Status Card Frontend](https://github.com/lweberru/bmw_status_card)

BMW Status ist die Home-Assistant-Backend-Integration fuer die
[BMW Status Card](https://github.com/lweberru/bmw_status_card). Beide Projekte
sind fuer den gemeinsamen Einsatz konzipiert: Diese Integration ueberfuehrt die
von `bmw-cardata-ha` gelieferten Entitaeten in einen versionierten
Praesentationsvertrag; die Karte rendert diesen Vertrag, ohne im Browser auf
Fahrzeug-Provider zuzugreifen.

Version: 0.2.5

## Funktionen

- Ein Config Entry und ein Statussensor pro `bmw-cardata-ha`-Fahrzeug.
- Ein versioniertes `presentation`-Attribut mit Fahrzeug-, Energie-, Reichweiten-,
  Oeffnungs-, Reifendruck-, Service- und Klimadaten.
- Serverseitig erzeugte und gecachte Fahrzeugbilder sowie MapTiler-Positionskarten.
- MapTiler- und Bildprovider-Schluessel verbleiben in der Backend-Konfiguration;
  sie werden weder an den Browser noch ueber den Sensor veroeffentlicht.
- Aktionen zum Aktualisieren von Daten und Verwalten gecachter Bild-Assets.

## Voraussetzungen

1. Installiere und konfiguriere `bmw-cardata-ha` mit mindestens einem Fahrzeug.
2. Installiere dieses Repository ueber HACS als **Integration**.
3. Installiere das zugehoerige [BMW Status Card Frontend](https://github.com/lweberru/bmw_status_card)
   ueber HACS als **Frontend**-Plugin.

## Einrichtung

1. Oeffne in Home Assistant **Einstellungen → Geraete & Dienste → Integration hinzufuegen**.
2. Waehle **BMW Status**.
3. Waehle das CarData-Fahrzeug und konfiguriere die optionalen Fahrzeugdetails.
4. Konfiguriere bei Bedarf serverseitige Karten- und Bildprovider.
5. Fuege eine BMW Status Card fuer den erzeugten Sensor hinzu, zum Beispiel `sensor.status`.

Der Statussensor veroeffentlicht `attributes.presentation`. Nutze dieses Attribut
ueber die zugehoerige Karte; es ist der stabile Anzeigevertrag zwischen Backend
und Frontend.

## Aktionen

- `bmw_status.refresh`: Aktualisiert die Praesentation aus den aktuellen CarData-States.
- `bmw_status.regenerate_images`: Erzeugt gecachte visuelle Assets fuer einen Entry neu.
- `bmw_status.clear_image_cache`: Loescht nur den lokalen Asset-Cache eines Entry.

Alle Aktionen akzeptieren optional `entry_id`, was bei mehreren Fahrzeugen
nuetzlich ist.

## Lokale Entwicklung

Der Devcontainer startet Home Assistant unter `http://localhost:8123` mit einer
lokalen, produktionsnahen CarData-Fixture.

1. Oeffne den Ordner `bmw_status` in VS Code und waehle **Reopen in Container**.
2. Oeffne `http://localhost:8123` und schliesse das Home-Assistant-Onboarding ab.
3. Fuege **BMW Status** hinzu und waehle das Fixture-Fahrzeug.
4. Oeffne `http://localhost:8123/lovelace/fahrzeug`, um die zugehoerige Karte zu pruefen.

Die Fixture unterstuetzt die Szenarien `parked`, `driving` und `attention` ueber
die Aktion `cardata.set_fixture_scenario`. Sie ist ausschliesslich fuer die lokale
Entwicklung vorgesehen und wird fuer die Produktivinstallation nicht benoetigt.
