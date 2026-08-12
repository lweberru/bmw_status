# BMW Status: Backend-Migration

## Ausgangslage

Die `bmw-status-card` enthält derzeit neben der Darstellung fachliche Logik:

- Erkennung und Priorisierung von Fahrzeug-Entities
- Ableitung von Fahrzeug-, Tür-, Reifen- und Ladeszenarien
- Generierung von `vehicle-status-card`-Konfigurationen
- Berechnung von Bildnamen, Cache-Keys, Prompts und Compositor-Layern
- Direkte Aufrufe von `image_compositor`, `upload_file` und AI-Diensten

Damit wird ein Bild erst erzeugt, wenn ein Browser die Karte rendert. Das führt zu Verzögerungen, browserabhängigen Nebenwirkungen und einer schwer testbaren Fachlogik.

## Zielbild

Die Zielarchitektur besteht ausschließlich aus zwei eigenen Komponenten:

```text
bmw-cardata-ha --> bmw_status --> bmw-status-card
                    Backend       Frontend
```

`bmw_status` wird eine Home-Assistant-Integration mit einem Coordinator und einem Config Entry pro Fahrzeug.

1. Der Coordinator beobachtet die relevanten Quell-Entities von `bmw-cardata-ha`, einschließlich Motion State.
2. Er normalisiert deren Zustände zu einem stabilen Fahrzeugmodell und ermittelt daraus den Darstellungszustand.
3. Bei einer relevanten Änderung berechnet und persistiert er die benötigten Bilder selbst im Hintergrund unter `/config/www`.
4. Er veröffentlicht eine fertige, versionierte Darstellungsprojektion als Entity-Attribute.
5. Die `bmw-status-card` liest ausschließlich diese Projektion und rendert sie. Sie ruft keine Dienste auf, generiert keine Bilder und enthält keine Status-/Prompt-/Cache-Logik mehr.

`image_compositor` und `upload_file` werden aufgelöst. Ihre BMW-spezifischen Funktionen werden als interne Python-Module von `bmw_status` umgesetzt. Es gibt keine Runtime-Abhängigkeit mehr auf diese Integrationen.

Vorgeschlagener Vertrag zwischen Backend und Karte:

```text
sensor.bmw_status_<fahrzeug>
  state: <kurzer, lesbarer Fahrzeugstatus>
  attributes:
    schema_version: 1
    presentation: <vollständige, serialisierbare Kartenprojektion>
    image_status: ready | pending | error | disabled
    updated_at: <ISO-Zeitstempel>
    error: <optionale, gekürzte Diagnose>
```

Die Projektion enthält die bereits ausgewählten Entities, Texte, Badges, Bereiche und die fertigen lokalen Bild-URLs. Die eigene `bmw-status-card` bildet sie zustandslos auf ihre Anzeige ab. Solange sie intern die `vehicle-status-card` als Basis-Komponente einbettet, erzeugt sie daraus deren Child-Card-Konfiguration; diese technische Zuordnung gehört ausschließlich ins Frontend.

Der Vertrag soll bevorzugt als fachliche `presentation` umgesetzt werden, nicht als direktes `vehicle_status_card_config`:

- `presentation` beschreibt das Fahrzeug und seine Anzeige semantisch, etwa Status, gewählte Entities, Labels, Badges, Bild-URLs und Kartenbereiche. Die eigene Frontendkarte bildet diese Daten ohne eigene Fachlogik auf ihre Darstellung ab.
- `vehicle_status_card_config` wäre die bereits vollständig erzeugte Konfiguration der fremden `vehicle-status-card`. Das reduziert die Zuordnung im Frontend weiter, bindet `bmw_status` aber dauerhaft an deren YAML-Format und Versionsänderungen.

## Bildjob-Strategie

Pro Fahrzeug ist maximal ein Bildjob gleichzeitig aktiv. Relevante Statusänderungen werden gebündelt; während ein Job läuft, ersetzt der jüngste Zustand einen noch nicht gestarteten Folgejob.

Fehler werden klassifiziert und in Metadaten mit Zeitpunkt, Provider, Fehlerklasse und gekürzter Ursache gespeichert:

| Fehlerklasse | Verhalten |
| --- | --- |
| Kontingent, Rate Limit oder Abrechnungsfehler | Kein automatischer Retry bis zu einem vom Provider vorgegebenen `retry_after` oder bis zum nächsten manuellen `regenerate_images`-Aufruf |
| Temporärer Netzwerk- oder Providerfehler | Begrenzte Retries mit exponentiellem Backoff |
| Zeitüberschreitung oder unvollständige Providerantwort | Begrenzte Retries mit exponentiellem Backoff |
| Ungültige Konfiguration, Authentifizierung oder nicht unterstütztes Modell | Kein automatischer Retry; Diagnose veröffentlichen |
| Dateisystemfehler | Kein Retry, bis der lokale Fehler behoben ist; Diagnose veröffentlichen |

Bei jedem Fehler bleibt das letzte gültige Bild sichtbar. Der Entity-Status meldet zusätzlich `image_status: error` mit einer gekürzten Diagnose; ein später erfolgreicher Job setzt ihn wieder auf `ready`.

## Besitzgrenzen

| Bereich | Zielbesitzer | Entscheidung |
| --- | --- | --- |
| BMW-spezifische Entity-Erkennung, Statusableitung, Präsentationsmodell, Bild-Jobs, Cache und lokale Bildpersistenz | `bmw_status` | Backend-Alleinbesitz |
| Gemini-/OpenAI-Inpainting | `bmw_status` | Über interne Provider-Adapter |
| `image_compositor` und `upload_file` | Keine Zielkomponente | Wird nach abgeschlossener Migration entfernt |
| `bmw-cardata-ha` | Externe Quellintegration | Einzige fachliche Datenquelle |
| `bmw-status-card` | Frontend-Karte | Ausschließlich Darstellung |

Die Bilddateien werden durch `bmw_status` ausschließlich in einem eigenen, pro Fahrzeug getrennten Unterordner von `/config/www/bmw_status/` geschrieben. Alle Pfade, Dateinamen, Metadaten, Bereinigung und Existenzprüfungen bleiben dadurch intern und BMW-spezifisch.

## Ablaufplan

### Phase 0: Entscheidungen und Vertrag festschreiben

- Entity-Vertrag, Versionierung und Fehlerzustände definieren.
- Auslösepolitik für Bildjobs festlegen: relevante Zustandsänderung, Konfigurationsänderung, manueller Refresh, Start von Home Assistant.
- Fehlerklassifikation, Retry-Backoff und die Auswertung von Provider-`retry_after` festlegen.
- Datenschutz- und Geheimnisstrategie festlegen: Provider-Schlüssel gehören in den Config Entry beziehungsweise dessen Options, niemals in Entity-Attribute oder Karten-YAML.
- Der MapTiler-Key gehört ausschließlich in die Konfiguration der `bmw-status-card`; `bmw_status` speichert und veröffentlicht ihn nicht.
- Den Umzug der bisherigen Bildfunktionen aus `image_compositor` und `upload_file` als interne `bmw_status`-Module abgrenzen.

**Abnahme:** Ein kleines Beispiel der `presentation`-Attribute ist vereinbart und kann ohne Browser gerendert werden.

### Phase 1: `bmw_status` als Integration grundlegen

- HACS-/Integrationstruktur unter `bmw_status/custom_components/bmw_status/` anlegen.
- `manifest.json`, Config Flow und Options Flow erstellen.
- Ein Fahrzeug über einen gefilterten Dropdown aus den verfügbaren `bmw-cardata-ha`-Geräten auswählen; ein Config Entry repräsentiert genau dieses Fahrzeug.
- Im Einrichtungsdialog die vom Fahrzeug benötigten Einstellungen in sinnvolle Schritte gliedern: Fahrzeug, Karte/Map, Bild-Provider und Bildverhalten.
- Coordinator, Lifecycle, Unload und Diagnose-Grundgerüst implementieren.
- Eine Status-Entity mit `schema_version` und leerer Projektion bereitstellen.

**Abnahme:** Eine Integration lässt sich über die UI anlegen, neu laden und sauber entfernen; die Status-Entity ist vorhanden.

### Phase 2: Fachmodell und reine Berechnung migrieren

- Die vorhandene Auswahl der `bmw-cardata-ha`-Entities, Elektrifizierungs-Erkennung, Motion-State-Auswertung, Reifen-/Tür-/Klima-/Servicezuordnung und Labels nach Python übernehmen.
- Aus den normalisierten Entity-Snapshots ein testbares, typisiertes Domänenmodell bilden.
- Daraus eine serialisierbare Präsentationsprojektion mit semantischen Daten und Badges erzeugen.
- Keine Netzwerk-, Dateisystem- oder Service-Aufrufe in diesen Berechnungsmodulen zulassen.
- Die vollständige Unit- und Integrationstestmatrix wird nach Phase 4 und vor Phase 5 umgesetzt.

**Abnahme:** Für identische Snapshots erzeugt das Backend dieselbe fachliche Projektion wie die bestehende Karte; isolierte Verhaltenchecks prüfen die Kernklassifikation bis zur geplanten Testphase.

### Phase 3: Reaktive Aktualisierung und Bildjobs

- Relevante Source-Entities dynamisch abonnieren und Änderungen debouncen.
- Einen deduplizierten Job-Manager einführen: pro Fahrzeug höchstens ein laufender Job; identische Zustands- und Konfigurations-Keys werden nicht erneut gerendert.
- Fehler klassifizieren: Rate-Limit-/Kontingent- und Konfigurationsfehler sperren automatische Wiederholungen; temporäre Netzwerk-, Provider- und Timeout-Fehler erhalten begrenzte Retries mit exponentiellem Backoff.
- Cache-, Dateinamen- und Metadatenlogik aus Karte, `image_compositor` und `upload_file` als interne Backend-Module migrieren.
- Provider-Adapter für Gemini und OpenAI-Inpainting implementieren; `ai_task` und generische Endpoints entfallen.
- Ausschließlich den stabilen `state_render`-Ansatz implementieren; Masken-, Overlay- und Compose-Logik entfallen.
- Bilder direkt und atomar in den eigenen `/config/www/bmw_status/<fahrzeug>/`-Pfad schreiben.
- Jobs von der Coordinator-Aktualisierung trennen: Der aktuelle fachliche Zustand bleibt sofort sichtbar, während `image_status: pending` gesetzt wird.
- Bei Erfolg atomar Bild-URLs und Projektion aktualisieren; bei Fehlern vorhandene letzte gültige Bilder behalten und eine Diagnose veröffentlichen.

**Abnahme:** Eine relevante Zustandsänderung erzeugt genau einen Hintergrundjob; beim Öffnen der Karte ist das vorbereitete Bild ohne Service-Aufruf aus dem Browser verfügbar.

### Phase 4: Konfiguration und Bedienung

- Alle Backend-relevanten Einstellungen aus dem Karteneditor in den Config/Options Flow verschieben: Fahrzeug, Provider, Modell, Bildgröße, View-/Scene-Strategie, Pfade, MapTiler und Cache-/Aktualisierungsregeln.
- API-Schlüssel mit Home-Assistant-Konventionen speichern und im UI maskieren.
- Dienste für explizite Aktionen bereitstellen, mindestens `refresh`, `regenerate_images` und `clear_image_cache`.
- Der Karteneditor beschränkt sich auf Auswahl der `bmw_status`-Entity sowie Darstellungsoptionen.

**Abnahme:** Bilder können vollständig ohne geöffnete Lovelace-Ansicht erzeugt und neu erzeugt werden.

### Phase 4.5: Lokale Home-Assistant-Entwicklungsumgebung

- Einen Dev Container mit Home Assistant, `pytest` und `pytest-homeassistant-custom-component` bereitstellen.
- `bmw_status` und die lokale `bmw-cardata-ha`-Integration unter `/config/custom_components` einbinden.
- Eine persistente, aber lokale Home-Assistant-Konfiguration und einen Debug-Logger für beide Integrationen bereitstellen.
- Den Config Flow, die Dienste, die State-Subscriptions und die lokale Bildablage unter `http://localhost:8123` manuell prüfen.
- Keine Produktivdaten oder Provider-Schlüssel einchecken; Test-Schlüssel nur über den lokalen Options Flow eingeben.

**Abnahme:** Der Dev Container startet Home Assistant, erkennt beide Custom Components und kann einen `bmw_status`-Config-Entry anlegen.

### Testphase: Nach Phase 4, vor Phase 5

- Unit-Tests für Fachmodell, Projektion, Cache-Key und Zustandsübergänge schreiben.
- Integrationstests mit simulierten Home-Assistant-States, Registry und Services schreiben.
- Vertrags-Snapshots für BEV, PHEV, Mild-Hybrid und Verbrenner ergänzen.

**Abnahme:** Die Backend-Testmatrix läuft grün, bevor die Frontendkarte auf den neuen Vertrag umgestellt wird.

### Phase 5: Frontend auf reine Darstellung reduzieren

- Die Karte liest die Status-Entity und prüft `schema_version`.
- Direkte `callWS`-/Service-Aufrufe, AI-Clients, Cache-Prüfungen, Prompt-Erzeugung und Bilddatei-Logik entfernen.
- Den Editor auf Entity-Auswahl, Lesefehler und visuelle Optionen reduzieren.
- Einen eindeutigen Lade-, Fehler- und Kompatibilitätszustand für fehlende oder veraltete Backend-Projektionen darstellen.
- Die bestehende Konfiguration wird nicht migriert; die neue Integration und die vereinfachte Karte werden neu eingerichtet.

**Abnahme:** Eine Suche im Frontend nach `image_compositor`, `upload_file`, `generate_image`, `ai_task` und `call_service` liefert keine Produktionsaufrufe mehr.

### Phase 6: Qualität, Migration und Freigabe

- Frontend-Tests für Projektion, Fehlerzustände und Schema-Version ergänzen.
- Neueinrichtungs-Anleitung, Konfigurationsreferenz und Fehlerdiagnose dokumentieren.
- Entfernte Integrationen und die alte umfangreiche Kartenkonfiguration als Breaking Change dokumentieren.

**Abnahme:** Ein frisches Setup funktioniert dokumentiert; alle Tests und Linter laufen grün.

## TODO und offene Entscheidungen

### Vor Implementierungsbeginn

- [x] **Instanzmodell:** Genau ein `bmw_status`-Config-Entry pro Fahrzeug.
- [x] **Quellbindung:** `bmw-cardata-ha` ist die einzige Datenquelle; das Fahrzeug wird beim Einrichten über einen gefilterten Dropdown gewählt.
- [x] **Bildstrategie:** Ausschließlich `state_render`; Masken, Overlay und Compose entfallen.
- [x] **Provider:** Nur Gemini und OpenAI-Inpainting; `ai_task` und Generic Endpoint entfallen.
- [x] **Abhängigkeiten:** `image_compositor` und `upload_file` werden nicht weitergeführt; deren nötige BMW-Funktionen wandern nach `bmw_status`.
- [x] **Kompatibilität:** Breaking Change, keine Übergangsphase und keine Konfigurationsmigration.
- [x] **Entity-Vertrag:** Fachliche `presentation`. Die eigene `bmw-status-card` bildet sie ohne Fachlogik auf ihre Darstellung ab und erzeugt bei Bedarf intern die Konfiguration für die eingebettete `vehicle-status-card`.
- [x] **Aktualisierungsstrategie:** Maximal ein aktiver Job je Fahrzeug; relevante Änderungen werden gebündelt. Temporäre Fehler erhalten begrenzte Retries mit exponentiellem Backoff, Kontingent-/Rate-Limit-Fehler nicht.
- [x] **Fehlerverhalten:** Letztes gültiges Bild bleibt sichtbar; Fehlerklasse und gekürzte Ursache werden veröffentlicht.
- [x] **Schlüsselverwaltung:** Provider-Schlüssel werden im Config Entry beziehungsweise Options Flow gespeichert und im UI maskiert.
- [x] **Datenhaltung:** Bilddateien und JSON-Metadaten/Cache-Index liegen intern unter `/config/www/bmw_status/<fahrzeug>/`.

### Nach den Entscheidungen

- [ ] Beispiel-Projektion mit mindestens einem realen Fahrzeug-Snapshot als Vertragstest hinzufügen.
- [ ] Technische Modulstruktur und Schnittstellen aus Phase 1 konkretisieren.
- [ ] Migrationsreihenfolge als umsetzbare Tickets schneiden.
- [ ] Erst danach Implementierung beginnen.

## Bekannte technische Risiken

- Bildgenerierung kann teuer und langsam sein. Sie muss entkoppelt, dedupliziert und begrenzt werden.
- Entity-Attribute dürfen keine API-Schlüssel, großen Bilddaten oder ungebremst wachsende Historie enthalten.
- Die gleiche State-Änderung kann mehrere Source-Entities betreffen. Der Coordinator benötigt eine kohärente Snapshot-/Debounce-Strategie.
- Bei Compositor-/Provider-Ausfällen muss die Anzeige weiter funktionieren und einen verständlichen Status liefern.
- Die Präsentationsprojektion ist ein API-Vertrag. Änderungen benötigen `schema_version` und eine Migrationsstrategie.