# -*- coding: utf-8 -*-
"""
Version und Aenderungslog von EV PV-Laden.

Pflege bei einer neuen Version (wie beim EV Tracker):
  1. VERSION erhoehen (major.minor.patch), config.yaml "version:" mitziehen
  2. Oben in CHANGELOG einen neuen Eintrag einfuegen – neueste Version zuerst
  3. CHANGELOG.md (Update-Dialog des Add-on-Stores) passend ergaenzen
"""

VERSION = "0.1.0"

CHANGELOG = [
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
