# EV PV-Laden

Home-Assistant-Add-on für PV-Überschussladen mit einem **go-eCharger** (lokal über die
Integration [go-e APIv2 Connect](https://github.com/marq24/ha-goecharger-api2)) und
Hausakku-Priorität. Bilanziert genau, wie viel kWh aus PV, Hausakku und Netz ins Auto
gingen, und meldet jede Ladung an den [EV Tracker](https://github.com/HasenbeinMH/ev-tracker-ha).

> **Status: in Entwicklung (0.3.0 – Strategie im Trockenlauf).** Das Add-on liest Messwerte,
> bilanziert PV/Akku/Netz, rechnet die erlaubte Ladeleistung und zeigt die Entscheidungen –
> schreibt aber noch nichts auf die Wallbox.

## Prinzip

- **Strategie im Add-on:** wie viel Leistung das Auto bekommen darf (Hausakku zuerst, Glättung,
  Hysterese, Modi *Aus / Nur PV / Min + PV / Sofort / Zielzeit*).
- **Schnelle Regelung in der go-e:** Eco-Modus mit PV-Überschuss; das Add-on schickt alle
  paar Sekunden einen *virtuellen* Netzwert (`ids`). Fallback: Strom direkt setzen.
- **Sicherheit:** harte Stromgrenzen (Zuleitung, Schieflast 20 A einphasig nach
  VDE-AR-N 4100), Alterserkennung jedes Messwerts, **Trockenlauf** als Standard.

## Installation (Entwicklungsstand)

1. Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories →
   `https://github.com/HasenbeinMH/ev-pv-laden` hinzufügen.
2. „EV PV-Laden“ installieren, unter *Konfiguration* die Sensoren prüfen, starten.
3. Oberfläche über die Seitenleiste öffnen: alle Messwerte müssen „gültig“ sein.
4. Voraussetzung für die HA-Entitäten: Add-on *Mosquitto broker* und die MQTT-Integration.
   Es erscheint das Gerät „EV PV-Laden“ mit `sensor.ev_pv_laden_kwh_pv`, `…_kwh_akku`, `…_kwh_netz`.

`trockenlauf` bleibt eingeschaltet, bis die Regelung im Trockenlauf geprüft ist.

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
