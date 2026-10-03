# -*- coding: utf-8 -*-
"""
Version und Aenderungslog von EV PV-Laden.

Pflege bei einer neuen Version (wie beim EV Tracker):
  1. VERSION erhoehen (major.minor.patch), config.yaml "version:" mitziehen
  2. Oben in CHANGELOG einen neuen Eintrag einfuegen – neueste Version zuerst
  3. CHANGELOG.md (Update-Dialog des Add-on-Stores) passend ergaenzen
"""

VERSION = "0.3.0"

CHANGELOG = [
    {
        "version": "0.3.0",
        "datum": "2026-10-03",
        "titel": "Strategie im Trockenlauf",
        "aenderungen": [
            "Berechnet die erlaubte Ladeleistung: Hausakku zuerst bis zur SoC-Schwelle, darueber wird sein Ueberschuss zum Auto umgeleitet; Akku-Entladung zaehlt immer als Defizit",
            "Glaettung, Start-/Stopp-Hysterese, Mindestladedauer und Mindestpause; Modi Aus, Nur PV, Min + PV, Sofort",
            "Veraltete Messwerte: kein Ueberschuss, Stopp ohne Verzoegerung",
            "Oberflaeche: Moduswahl, Entscheidung mit Grund, Diagramm der letzten Stunde, Parameter",
            "HA-Entitaeten: erlaubte Ladeleistung, virtueller Netzwert, Grund, Regelzustand, Modus, Treiber",
            "Schreibt weiterhin nichts auf die Wallbox",
        ],
    },
    {
        "version": "0.2.0",
        "datum": "2026-10-03",
        "titel": "Bilanz PV/Akku/Netz",
        "aenderungen": [
            "Teilt die Ladeleistung je Sekunde in PV, Hausakku und Netz auf (Haus zuerst, Auto bekommt den Ueberschuss)",
            "Der Energiezaehler der Wallbox fuehrt: PV + Akku + Netz ergeben immer genau dessen Anstieg",
            "Zaehler als HA-Entitaeten per MQTT (Ladung PV/Hausakku/Netz, Ladeleistungen, Lebenszeichen) – springen nie zurueck",
            "Tagesbilanz mit Plausibilitaetspruefung (Integral der Leistung) und einzelne Ladevorgaenge",
            "Warnung, wenn ama der Wallbox von der konfigurierten Grenze abweicht",
            "Schreibt weiterhin nichts auf die Wallbox",
        ],
    },
    {
        "version": "0.1.0",
        "datum": "2026-10-03",
        "titel": "Geruest",
        "aenderungen": [
            "Add-on mit Ingress-Oberflaeche, Konfiguration, Protokoll und Datenbank unter /data",
            "Liest die konfigurierten Messwerte live aus Home Assistant und zeigt Wert und Alter an",
            "Schreibt noch nichts auf die Wallbox",
        ],
    },
]
