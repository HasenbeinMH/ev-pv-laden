# EV PV-Laden

Home-Assistant-Add-on für PV-Überschussladen mit einem **go-eCharger** (lokal über die
Integration [go-e APIv2 Connect](https://github.com/marq24/ha-goecharger-api2)) und
Hausakku-Priorität. Bilanziert genau, wie viel kWh aus PV, Hausakku und Netz ins Auto
gingen, und übergibt jede Ladung an den [EV Tracker](https://github.com/HasenbeinMH/ev-tracker-ha).

> **Status: 0.10 – funktionsvollständig, Live-Inbetriebnahme steht aus.** Messung, Bilanz,
> Strategie, PV-Prognose, Bedienung aus HA und die Übergabe an den EV Tracker laufen.
> Auf die Wallbox geschrieben wurde noch nicht: Standard ist der **Trockenlauf** – das
> Add-on zeigt nur, was es schreiben würde. Scharfschalten erst nach
> [docs/M5_Inbetriebnahme.md](docs/M5_Inbetriebnahme.md).

## Funktionen

- **Start/Stopp:** jede Ladung bewusst starten; während der Ladung sind Modus und Einstellungen
  gesperrt, Abstecken stoppt. Ladungen über die go-e-App (HA nicht verfügbar) bleiben unangetastet.
- **Lademodi:** *Nur PV · Min + PV · Sofort · Zielzeit*. Hausakku zuerst bis zu einer
  einstellbaren SoC-Schwelle, darüber geht sein Überschuss ins Auto; Glättung, Start-/Stopp-
  Hysterese, Mindestladedauer und -pause.
- **Zielzeit / Ladestand:** bis zum spätesten Start nur PV, danach Netzladen bis zum Ziel.
  SoC des Autos per Eingabe oder Sensor, dazwischen über den Zähler der Wallbox hochgerechnet.
- **Zwei Stellglieder:**
  - *ids* (Standard): die go-e regelt selbst im Eco-Modus, das Add-on schickt alle 2 s einen
    virtuellen Netzwert. Kommt nichts mehr, stoppt die go-e nach ~5 s von selbst.
  - *A* (Ausweich): das Add-on stellt Strom und Start/Stopp direkt, fest dreiphasig.
  - Erkennung „lädt nach einer Pause nicht wieder an“ (FW 59.4) mit Gegenmaßnahme.
- **Bilanz:** jede Sekunde aufgeteilt in PV, Hausakku und Netz; der Energiezähler der Wallbox
  führt. Tagesbilanz, Ladevorgänge, Zähler als HA-Sensoren.
- **EV Tracker:** jeder beendete Ladevorgang geht automatisch an den Tracker (mit Sendepuffer),
  dazu gemeinsame Monatszähler und ein Verbindungstest.
- **PV-Prognose:** eigenes Modell aus der HA-Statistik und Open-Meteo-Einstrahlung je Dachfläche
  (Verschattung, Verschmutzung) – [docs/PV_Modell.md](docs/PV_Modell.md). Vergleich mit der
  gemessenen Erzeugung im Diagramm.
- **Oberfläche:** Dashboard ohne Scrollen (Kennzahlen, Energiefluss mit Netzknoten, Auto,
  Lademodus, Tageskurve mit Prognose), dazu Laden, Verlauf, Prognose, Einstellungen, Diagnose.

## Sicherheit

- **Harte Stromgrenzen** im Code, unabhängig von der Strategie: höchstens 24 A (Zuleitung),
  einphasig höchstens 20 A (Schieflast nach VDE-AR-N 4100) bzw. die Grenze des Autos.
  Gemessener Überstrom → Laden gesperrt und verriegelt.
- **Alterserkennung** jedes Messwerts: veraltet = kein Überschuss.
- **Trockenlauf in zwei Stufen:** `trockenlauf: true` in den Optionen sperrt fest. Erst wenn die
  Option aus ist, lässt er sich in der Oberfläche oder in HA umschalten (Anfangswert: an).
- Watchdog-Automation für HA als Vorlage: [docs/automationen.yaml](docs/automationen.yaml).

## Voraussetzungen

- Home Assistant OS oder Supervised (Add-ons)
- go-eCharger mit der Integration *go-e APIv2 Connect* (marq24)
- Add-on *Mosquitto broker* und die MQTT-Integration (für die HA-Entitäten)
- ein Sensor für die Netzleistung; optional Hausakku (Leistung, SoC), PV-Leistung, Hausverbrauch

## Installation

1. Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories →
   `https://github.com/HasenbeinMH/ev-pv-laden` hinzufügen.
2. „EV PV-Laden“ installieren und unter *Konfiguration* einstellen:
   - **Sensoren** für Netz, Hausakku, PV, Hausverbrauch – die Vorzeichen lassen sich je
     Sensor umdrehen (intern: Netzbezug +, Akku-Entladung +)
   - **go-e-Seriennummer** (aus den Entity-IDs `goe_XXXXXX_…`)
   - **Stromgrenzen** passend zur eigenen Zuleitung und zum Auto
   - **Auto:** Akkukapazität, Ladewirkungsgrad, höchste AC-Ladeleistung
   - **Dachflächen** (`pv_flaechen`: Neigung, Azimut, kWp) für die PV-Prognose
   - optional **EV Tracker**: Adresse, Token, Fahrzeug
3. Starten und die Oberfläche über die Seitenleiste öffnen (sichtbar für alle HA-Benutzer).
   Unter *Diagnose* müssen alle Messwerte „gültig“ sein.
4. Einige Tage im Trockenlauf mitlaufen lassen, dann nach
   [docs/M5_Inbetriebnahme.md](docs/M5_Inbetriebnahme.md) in Betrieb nehmen.

Die Voreinstellungen in `config.yaml` sind die der Entwickler-Anlage (SolarEdge, go-e) und
müssen für andere Anlagen angepasst werden.

## Bedienung aus Home Assistant

Das Gerät „EV PV-Laden“ (MQTT) bringt u. a. mit:

| Art | Entitäten |
|---|---|
| Bedienen | Laden gestartet (Start/Stopp), Lademodus, Nachtladen, Treiber, Trockenlauf, Hausakku-Schwelle, Batterie-Auto, Ladestand, Abfahrt, Puffer |
| Bilanz | `sensor.ev_pv_laden_kwh_pv`, `…_kwh_akku`, `…_kwh_netz` |
| EV Tracker | `sensor.ev_pv_laden_tracker_kwh_pv`, `…_tracker_kwh_netz`, Übergabe-Status |
| Regelung | erlaubte Ladeleistung, Grund, Regelzustand, aktiver Treiber, Lebenszeichen |
| Prognose | PV-Prognose heute / Rest / morgen, Sauberkeit der Anlage |
| Meldungen | `event.ev_pv_laden_ladung` (fertig geladen, Ladestand erreicht) – z. B. für Telegram |

Vorlagen für HA-Automationen:
- [docs/automationen.yaml](docs/automationen.yaml) – Watchdog und Telegram „fertig geladen“
- [docs/batterie_steuerung.yaml](docs/batterie_steuerung.yaml) – SolarEdge-Hausakku: keine
  Entladung beim Autoladen, Winterreserve 25/30 % (am Wechselrichter getestet)

## PV-Prognose im Energie-Dashboard (Integration)

Im Repository steckt zusätzlich eine kleine HA-Integration **„EV PV-Laden Prognose“**
(`custom_components/ev_pv_laden_prognose`). Sie holt die Stundenprognose vom Add-on und
stellt sie dem Energie-Dashboard bereit, dazu Sensoren (heute, Rest heute, morgen, aktuelle
Stunde, nächste Stunde, nächste 3 Stunden; Stundenwerte als Attribut `wh_hours`).

1. HACS → ⋮ → Benutzerdefinierte Repositories → `https://github.com/HasenbeinMH/ev-pv-laden`,
   Typ **Integration** → „EV PV-Laden Prognose“ herunterladen → HA neu starten.
2. Einstellungen → Geräte & Dienste → Integration hinzufügen → „EV PV-Laden Prognose“.
   Vorgeschlagen ist die interne Adresse des Add-ons (`http://<Hostname des Add-ons>:8099`,
   der Hostname steht in den Add-on-Infos).
3. Einstellungen → Dashboards → Energie → Solarmodule → bearbeiten →
   „Prognose der Solarproduktion“ → „EV PV-Laden Prognose“ auswählen.

## Dokumentation

| Datei | Inhalt |
|---|---|
| [docs/M1_Discovery.md](docs/M1_Discovery.md) | Bestandsaufnahme go-e, Integration, Messwerte |
| [docs/M5_Inbetriebnahme.md](docs/M5_Inbetriebnahme.md) | Schritt für Schritt scharfschalten |
| [docs/PV_Modell.md](docs/PV_Modell.md) | Eigenes PV-Prognosemodell |
| [docs/Anlage.md](docs/Anlage.md) | Stammdaten der Entwickler-Anlage |
| [CHANGELOG.md](CHANGELOG.md) | Änderungen je Version |

## Entwicklung

```bash
pip install -r requirements-dev.txt
python -m pytest
python dev/start.py
```

`dev/start.py` startet die Oberfläche auf http://127.0.0.1:8099 mit Daten in `dev/data`.
Für echte Messwerte vorher `HA_URL` und `HA_TOKEN` (Long-Lived Access Token) setzen.
`python dev/start.py --simulation` läuft ohne HA mit einem Anlagenmodell (Sonne, Wolken,
Hausakku, Auto).

Aufgezeichnete Tage als Testdaten: `python dev/export_ha.py 2026-10-01 10:00 16:00`
(braucht `HA_URL`/`HA_TOKEN`) legt eine CSV in `tests/daten/` ab; `pytest` spielt sie mit
der Strategie und dem Anlagenmodell nach.

Die Oberfläche ist optisch an [eedc](https://github.com/supernova1963/eedc-homeassistant)
angelehnt (Farben, Kacheln).

## Lizenz

EV PV-Laden steht unter der **GNU General Public License v3.0** (GPL-3.0) – siehe [LICENSE](LICENSE).
Nutzen, ändern und weitergeben ist erlaubt; geänderte Fassungen müssen ebenfalls unter der
GPL-3.0 und mit Quelltext weitergegeben werden. Keine Gewährleistung – insbesondere für das
Schreiben auf Wallbox und Wechselrichter gilt: Betrieb auf eigene Verantwortung, zuerst im
Trockenlauf prüfen.

Enthaltene Fremdkomponenten (mit der GPL-3.0 vereinbar):
- [Apache ECharts](https://echarts.apache.org) – `webapp/static/echarts.min.js`, Apache License 2.0
- Icons von [Lucide](https://lucide.dev) – ISC-Lizenz
