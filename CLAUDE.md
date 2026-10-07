# EV PV-Laden – Hinweise für Claude

Home-Assistant-Add-on für PV-Überschussladen mit go-e Charger V4 (über die Integration
marq24 goecharger_api2), Hausakku-Priorität und Übergabe an den EV Tracker. Ersetzt evcc.
Dazu eine eigene HA-Integration (`custom_components/ev_pv_laden_prognose`), die die
PV-Prognose ins Energie-Dashboard bringt.

Sprache: Deutsch (Code-Bezeichner, Oberfläche, Commits, Doku). In Python-Dateien
Umlaute in Bezeichnern und Kommentaren als ae/oe/ue, in Texten der Oberfläche echte Umlaute.

## Regeln (verbindlich)

- **Nichts live schreiben ohne ausdrückliches OK im Chat:** keine Befehle an Wallbox
  oder Wechselrichter/Hausakku, keine Änderungen an Automationen, Helfern oder
  Einstellungen in Home Assistant. Lesen ist erlaubt.
- **Commit und Push nur auf Zuruf** („push“, „com und push“). Vor dem Push bei sichtbaren
  Änderungen eine Vorschau (Screenshot aus dem Simulator) zeigen.
- **Keine privaten Daten ins Repo** (öffentlich, GPL-3.0): keine Koordinaten, Adressen,
  Seriennummern, Tokens, IP-Adressen. Lokale Daten gehören nach `dev/data/` (ignoriert).
  Tokens trägt der Betreiber selbst ein, nie im Chat.
- **Keine erfundenen Entity-IDs oder Modbus-Register.** Vorher in HA nachsehen; was
  geprüft und was Annahme ist, kennzeichnen.
- Größere Vorhaben in Meilensteinen mit Rückfragen vorab.

## Workflow für eine Änderung

1. Ändern, dann `python -m pytest -q` – alle Tests müssen grün sein.
2. Sichtbare Änderungen im Simulator prüfen: Dev-Server `ev-pv-laden-simulation`
   (`.claude/launch.json`, `python dev/start.py --simulation`, Port 8099). Das Dashboard
   muss ohne Scrollen auf **1920 × 1080** und **1366 × 768** passen. Nach Änderungen an
   `app.js` den Browser-Cache umgehen (`fetch(..., {cache: "reload"})` + Reload).
3. **Jede Änderung, die ausgeliefert wird, bekommt eine neue Versionsnummer** (auch reine
   dev-/Doku-Änderungen, wenn der Betreiber es so will), an drei Stellen:
   - `config.yaml` → `version:`
   - `version.py` → `VERSION` und neuer Eintrag oben in `CHANGELOG` (ASCII, ae/oe/ue)
   - `CHANGELOG.md` → neuer Abschnitt oben (wird im Update-Dialog des Add-on-Stores angezeigt)
   Patch-Version für Korrekturen/kleine Änderungen, Minor-Version für neue Funktionen.
   Bereits gepushte Versionseinträge nicht mehr ändern.
4. Commit-Nachricht: `Version x.y.z: <Kurztitel>`, danach Stichpunkte.
   Commit-Identität ist repo-lokal gesetzt (GitHub-noreply-Adresse).
5. Nach dem Push startet das Add-on in HA erst, wenn der Betreiber das Update einspielt.
   Das Protokoll des Add-ons lässt sich über das HA-MCP lesen
   (`ha_get_logs`, source `supervisor`, slug `b5a2b766_ev_pv_laden`).

## Aufbau

- Regelung als zyklischer Ablauf wie in einer SPS (1 s): `laufzeit.py` (Hauptschleife,
  Tasks), `prozessabbild.py` (Eingänge aus HA, Einheiten/Vorzeichen), `regelung.py`
  (Start/Stopp, Modus, Freigabe), `strategie.py` (Lademodi, Parameter), `treiber.py`
  (go-e: Treiber ids und A), `wiederanlauf.py`, `zielzeit.py`, `tageslicht.py`.
- Bilanz/Ladevorgänge: `erfassung.py`, `ladevorgang.py`, `bilanz.py`, `tracker.py`
  (Übergabe an den EV Tracker), `meldungen.py`.
- PV-Prognose: `pvmodell.py`, `pvdaten.py`, `pvprognose.py` (eigenes Modell aus
  HA-Statistik + Open-Meteo), `prognose.py`, `morgentau.py` (Abschwächung der Morgenstunden nach Tau-Nächten).
  Doku: `docs/PV_Modell.md`.
- HA-Anbindung: `ha_client.py` (WebSocket), `mqtt_ha.py` (MQTT-Discovery, Bedien-Entitäten).
  Entitäts-IDs sind über `default_entity_id`/`unique_id` fest – Anzeigenamen dürfen
  sich ändern, IDs nicht.
- Oberfläche: `webapp/` (FastAPI, Ingress; `templates/index.html`, `static/app.js`,
  `static/style.css`, ECharts). Farben als CSS-Variablen in `style.css`.
- `dev/` (Simulator-Start, Auswerteskripte unter `dev/modell/`) und `docs/` kommen nicht
  ins Add-on-Image (`.dockerignore`).
- Doku für die Inbetriebnahme: `docs/M5_Inbetriebnahme.md`; HA-Vorlagen:
  `docs/automationen.yaml`, `docs/batterie_steuerung.yaml`.

## Stolperfallen

- `time.monotonic()` zählt ab Systemstart: Zeitgeber nie mit `0.0` vorbelegen, sondern
  mit „noch nie“ (`float("-inf")`).
- CSS-Grid: `auto` ist kein gültiger Bereichsname. Elemente mit `display:flex` brauchen
  eine eigene `[hidden]{display:none}`-Regel.
- Bash-Heredocs mit Python-Code sind unter Windows fehleranfällig – längere Änderungen
  als Python-Skript im Scratchpad ausführen.
