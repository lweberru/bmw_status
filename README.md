# BMW Status

`bmw_status` ist das Backend für `bmw-status-card`.

Version: 0.2.4

## Aktueller Stand

Die Integration kann pro `bmw-cardata-ha`-Fahrzeug eingerichtet werden und stellt
`sensor.bmw_status_<fahrzeug>_status` bereit. Der Sensor veröffentlicht einen
versionierten Präsentationsvertrag. Die Integration klassifiziert bereits die
CarData-Entities und beobachtet deren Zustände reaktiv. Die interne Bildpipeline
speichert PNG-Dateien und JSON-Metadaten unter `/config/www/bmw_status/` und wird
mit Gemini- oder OpenAI-Optionen in Phase 4 aktiviert.

1. Installiere und richte `bmw-cardata-ha` mit mindestens einem Fahrzeug ein.
2. Füge dieses Repository in HACS als Custom Repository vom Typ **Integration** hinzu und installiere **BMW Status**.
3. Füge **BMW Status** über Einstellungen > Geräte & Dienste hinzu.
4. Wähle das Fahrzeug im Dropdown aus und konfiguriere optional das Kennzeichen.
5. Aktiviere die Bildgenerierung mit Gemini oder OpenAI, falls vorbereitete Bilder gewünscht sind.

Die Positionskarte wird im Backend mit MapTiler erzeugt, lokal gecacht und als
Bild-URL im Praesentationsvertrag veroeffentlicht. Der MapTiler-Schluessel bleibt
im Config Entry und wird weder an den Browser noch ueber den Sensor weitergegeben.

## Backend-Aktionen

- `bmw_status.refresh`: Aktualisiert die Präsentation aus den CarData-States.
- `bmw_status.regenerate_images`: Erzwingt ein neues Bild für den aktuellen Zustand.
- `bmw_status.clear_image_cache`: Löscht ausschließlich den lokalen Bildcache des gewählten Fahrzeugs.

Alle Aktionen akzeptieren optional `entry_id`, um bei mehreren Fahrzeugen nur einen
Config Entry anzusprechen.

Die Konfiguration von Provider, Modell und Bildverhalten folgt in Phase 4.

## Lokale Home-Assistant-Entwicklung

Der Dev Container startet Home Assistant unter `http://localhost:8123`, bindet
`bmw_status` ein und stellt standardmäßig eine lokale CarData-Fixture bereit.

1. Öffne den Ordner `bmw_status` in VS Code und wähle **Reopen in Container**.
2. Rufe `http://localhost:8123` auf und schließe die lokale Home-Assistant-Ersteinrichtung ab.
3. Die Dev-Umgebung stellt standardmäßig eine lokale CarData-Fixture mit dem Gerät **BMW Status Dev Vehicle** bereit. Füge danach **BMW Status** über Geräte & Dienste hinzu und wähle dieses Gerät.
4. Die lokale Kartenansicht ist unter `http://localhost:8123/lovelace/fahrzeug` verfügbar und liest `sensor.status`.

Die Fixture stellt vollständige Fahrzeugwerte für Verriegelung, Laden, Energie,
Reichweiten, Kilometerstand, Öffnungen, Reifen, Service und Klima bereit. Zum
Umschalten rufe in **Entwicklerwerkzeuge → Aktionen**
`cardata.set_fixture_scenario` mit einem dieser Werte auf:

- `parked`: Normaler, geparkter Fahrzeugzustand.
- `driving`: Fahrzustand mit aktualisierten Reichweiten und aktivem Klima.
- `attention`: Geparktes Fahrzeug mit niedrigem Tank, offenen Öffnungen und zu niedrigem Reifendruck.

Alternativ mit dem lokalen API-Helfer:

```sh
python3 tools/ha_api_read.py --local call cardata set_fixture_scenario --data scenario=attention
```

Die Karte wird über die bestehenden `bmw_status`-Subscriptions automatisch
aktualisiert. Ein zusätzlicher `bmw_status.refresh` ist nur hilfreich, wenn ein
expliziter Aktualisierungspunkt getestet werden soll.

Falls `bmw-cardata-ha` nicht neben diesem Repository liegt, setze vor dem Start
`BMW_CARDATA_PATH` auf dessen lokalen Repository-Pfad. Der Pfad muss auf einen
Ordner zeigen, der `custom_components/cardata` enthält. Damit ersetzt die echte
CarData-Integration die lokale Fixture; dafür werden gültige BMW-Zugangsdaten benötigt.

In einem Zscaler-Netzwerk exportiere die lokal installierte Root-CA nach
`.devcontainer/zscaler-root-ca.crt` und erstelle den Container neu. Die Datei
wird nicht versioniert und beim Start in den Container-Truststore importiert.
Der Dev Container verwendet das offizielle Image
`ghcr.io/home-assistant/home-assistant:2026.8.1` (Python 3.14) und eine lokale,
begrenzte SSL-Kompatibilitätsanpassung für die ältere Zscaler-Root-CA. Die
reguläre Zertifikats- und Hostnamenprüfung bleibt aktiviert.

Die persistente lokale Home-Assistant-Konfiguration liegt im Docker-Volume
`bmw_status_devcontainer_ha_config`. Sie enthält lokale Zugangsdaten und
Provider-Schlüssel und wird nicht in Git gespeichert. Zum vollständigen
Zurücksetzen lösche dieses Docker-Volume über Docker Desktop.