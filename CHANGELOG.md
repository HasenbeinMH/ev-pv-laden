# Changelog

Alle nennenswerten Aenderungen des Add-ons EV PV-Laden.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [0.2.0] - 2026-10-03

Bilanz PV/Akku/Netz – noch ohne Regelung. **Braucht den Mosquitto-Broker** (für die HA-Entitäten).

- Teilt die Ladeleistung je Sekunde in PV, Hausakku und Netz auf (Haus zuerst, Auto bekommt den Überschuss)
- Der Energiezähler der Wallbox führt: PV + Akku + Netz ergeben immer genau dessen Anstieg
- Zähler als HA-Entitäten per MQTT (Ladung PV/Hausakku/Netz, Ladeleistungen, Lebenszeichen) – springen nie zurück
- Tagesbilanz mit Plausibilitätsprüfung (Integral der Leistung) und einzelne Ladevorgänge
- Warnung, wenn `ama` der Wallbox von der konfigurierten Grenze abweicht
- Schreibt weiterhin nichts auf die Wallbox

## [0.1.0] - 2026-10-03

Geruest – noch ohne Regelung.

- Add-on mit Ingress-Oberflaeche, Konfiguration, Protokoll und Datenbank unter /data
- Liest die konfigurierten Messwerte live aus Home Assistant und zeigt Wert und Alter an
- Schreibt noch nichts auf die Wallbox
