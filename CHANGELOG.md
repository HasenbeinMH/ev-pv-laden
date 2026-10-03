# Changelog

Alle nennenswerten Aenderungen des Add-ons EV PV-Laden.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [0.4.0] - 2026-10-03

Treiber „ids“ – **kann jetzt auf die Wallbox schreiben, aber nur mit `trockenlauf: false`.**
Standard bleibt der Trockenlauf; die Oberfläche zeigt unter „Stellglied“, was geschrieben würde.
Vor dem Scharfschalten: `docs/M5_Inbetriebnahme.md`.

- Treiber ids: go-e im Eco-Modus, das Add-on sendet alle 2 s einen virtuellen Netzwert (pGrid = P_auto − P_erlaubt)
- Sollkonfiguration der go-e (lmo, fup, frc, psm, frm, amp) wird überwacht und bei Abweichung nachgestellt
- Sofort: fest dreiphasig mit Maximalstrom; Aus: Laden gesperrt
- Harte Grenzen: amp einphasig begrenzt (Schieflast/Fahrzeug), Überstrom → Laden gesperrt und verriegelt
- Neue Option `ids_ppv_senden` (echte PV-Leistung als pPv oder 0)

## [0.3.0] - 2026-10-03

Strategie im Trockenlauf – rechnet und zeigt, schreibt aber nichts auf die Wallbox.

- Berechnet die erlaubte Ladeleistung: Hausakku zuerst bis zur SoC-Schwelle, darüber wird sein Überschuss zum Auto umgeleitet; Akku-Entladung zählt immer als Defizit
- Glättung, Start-/Stopp-Hysterese, Mindestladedauer und Mindestpause; Modi Aus, Nur PV, Min + PV, Sofort
- Veraltete Messwerte: kein Überschuss, Stopp ohne Verzögerung
- Oberfläche: Moduswahl, Entscheidung mit Grund, Diagramm der letzten Stunde, Parameter
- HA-Entitäten: erlaubte Ladeleistung, virtueller Netzwert, Grund, Regelzustand, Modus, Treiber

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
