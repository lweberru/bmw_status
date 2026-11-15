# BMW Status

[English](README.md) | [BMW Status Card Frontend](https://github.com/lweberru/bmw_status_card)

BMW Status ist die Home-Assistant-Backend-Integration fuer die
[BMW Status Card](https://github.com/lweberru/bmw_status_card). Beide Projekte
sind fuer den gemeinsamen Einsatz konzipiert: Diese Integration ueberfuehrt die
von `bmw-cardata-ha` gelieferten Entitaeten in einen versionierten
Praesentationsvertrag; die Karte rendert diesen Vertrag, ohne im Browser auf
Fahrzeug-Provider zuzugreifen.

Version: 0.4.0

## Funktionen

- Ein Config Entry und ein Statussensor pro `bmw-cardata-ha`-Fahrzeug.
- Ein versioniertes `presentation`-Attribut mit Fahrzeug-, Energie-, Reichweiten-,
  Oeffnungs-, Reifendruck-, Service- und Klimadaten.
- Serverseitig erzeugte und gecachte Fahrzeugbilder sowie MapTiler-Positionskarten.
- Fahrzeugbilder verwenden Jahreszeit, Tageszeit und grobe Wetterbedingungen
  von Open-Meteo wie Sonne, Regen oder Schnee. Temperatur, Niederschlagsmenge und
  Ortsnamen beeinflussen den Bildprompt nicht und loesen keine Neugenerierung aus.
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

Fuer OpenAI in den Integrationsoptionen den Bildprovider `openai` waehlen
und einen OpenAI-Projekt-API-Schluessel eintragen. Beim Providerwechsel werden
der bisherige Schluessel und die Modell-/Groessenvorgaben zurueckgesetzt.
Vorgabe ist `gpt-image-2.5-flare` mit `1024x1024` Pixeln; OpenAI-Bilder
werden als PNG mit Qualitaet `low` angefordert, um die Kosten gering zu halten.
Das Bildmodell bleibt frei konfigurierbar. Bereits gespeicherte Modelle werden
nicht automatisch ersetzt: `gpt-image-1` muss in den Optionen geaendert werden.
Die API benoetigt eigenes Guthaben; ein ChatGPT-Login allein reicht nicht.

Das letzte gecachte Fahrzeugbild bleibt sichtbar, waehrend eine neue Szene
generiert wird oder der Bildprovider nicht erreichbar ist. Messwertaenderungen,
die den Bildprompt nicht beeinflussen, verwenden das bestehende Bild weiter.

Der Statussensor veroeffentlicht `attributes.presentation`. Nutze dieses Attribut
ueber die zugehoerige Karte; es ist der stabile Anzeigevertrag zwischen Backend
und Frontend.

## Spritverbrauch

Der Configflow und die Integrationsoptionen enthalten den Schritt **Spritverbrauch**:

- Tankstand- und Kilometerstand-Sensor werden am gewaehlten Fahrzeug automatisch
  erkannt. Alternativ lassen sich vorhandene Sensoren explizit auswaehlen.
- Tankstand muss Liter oder Prozent liefern, Kilometerstand km oder mi.
  Bei Prozent ist der **Tankinhalt in Litern** erforderlich.
- **Anfangsverbrauch gesamt** ist der bereits verbrauchte Kraftstoff seit
  Erstzulassung bis zum ersten Erfassungszeitpunkt dieser Integration, in Litern.
  Die Lebenszeitstrecke ergibt sich aus dem ersten Kilometerstand plus erfasster
  Strecke. Ohne Anfangsverbrauch bleibt der Lebenszeitverbrauch unbekannt.
- Optional Anfangsverbrauch und Anfangsstrecke seit dem letzten Tanken
  gemeinsam angeben. Ohne diese Werte ist das erste Tankintervall unvollstaendig.
- Die Tankerkennung reagiert auf einen Anstieg ab **5 L** (konfigurierbar),
  auch bei Teilbetankung. Kleine Anstiege werden als Messschwankung ignoriert.

Das additive Attribut `presentation.fuel_consumption` enthaelt `total`,
`since_refuel` und `today`, jeweils mit `liters`, `distance_km`,
`average_l_per_100km` und `incomplete`. Hinzu kommen Erfassungsbeginn,
Tankereigniszeit, geschaetzte Nachfuellmenge und Hinweise auf fehlende Daten.
Bei fehlenden Grundlagen werden `null` und erklaerende `issues` statt erfundener
Werte veroeffentlicht. Es bleibt beim vorhandenen Statussensor.

Die Werte sind **Tankstand-basierte Schaetzungen**, keine exakten Bordcomputer-
oder Zapfsaeulenmessungen. Kleine Betankungen, Verbrauch waehrend eines
Tankintervalls zwischen zwei Meldungen und Sensorauflosung begrenzen die
Genauigkeit. Verbrauch und Strecke werden dem Tag ihrer Beobachtung in der
Home-Assistant-Zeitzone zugeordnet; eine Verteilung ueber Mitternacht ist ohne
Zwischenmessungen nicht rekonstruierbar. Der Tageszaehler wechselt um Mitternacht
auch bei parkendem Fahrzeug. Bei Strecke 0 bleibt der Durchschnitt unbekannt.

Zaehler und Messreferenzen werden getrennt je Config Entry in Home Assistants
`.storage` gespeichert, vor der ersten Aktualisierung wiederhergestellt und
nicht durch das Leeren des Bildcaches geloescht. Optionsaenderungen laden den
Entry neu. Anfangswerte beziehen sich auch nachtraeglich auf den urspruenglichen
Erfassungsbeginn (in der Karte sichtbar); sie werden nicht bei Neustarts erneut
addiert. Tankintervall-Anfangswerte gelten nur vor dem ersten erkannten Tanken.
Ein Wechsel der Sensoren oder des Tankinhalts setzt die betroffene Messreferenz
neu, behaelt Summen und kennzeichnet die Erfassung als unvollstaendig.

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
