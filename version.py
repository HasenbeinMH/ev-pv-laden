# -*- coding: utf-8 -*-
"""
Version und Aenderungslog von EV PV-Laden.

Pflege bei einer neuen Version (wie beim EV Tracker):
  1. VERSION erhoehen (major.minor.patch), config.yaml "version:" mitziehen
  2. Oben in CHANGELOG einen neuen Eintrag einfuegen – neueste Version zuerst
  3. CHANGELOG.md (Update-Dialog des Add-on-Stores) passend ergaenzen
"""

VERSION = "0.6.1"

CHANGELOG = [
    {
        "version": "0.6.1",
        "datum": "2026-10-04",
        "titel": "Hausverbrauch im Energiefluss",
        "aenderungen": ["Neuer optionaler Sensor sensor_haus fuer den Hausverbrauch im Energiefluss; misst er die Wallbox mit (sensor_haus_enthaelt_auto), wird die Ladeleistung abgezogen"],
    },
    {
        "version": "0.6.0",
        "datum": "2026-10-04",
        "titel": "Eigenes PV-Prognosemodell und Sauberkeit",
        "aenderungen": [
            "PV-Prognose aus eigenem Modell: Open-Meteo-Einstrahlung je Dachflaeche x gelerntes Kennfeld (Verschattung, Wirkungsgrad) – trainiert aus der HA-Statistik",
            "Sauberkeit der Anlage wird laufend geschaetzt, mit Reinigungshinweis und Knopf 'Anlage gereinigt'",
            "Prognose-Diagramm mit Vergleich zur HA-Prognose (Energie-Dashboard)",
            "Neue HA-Sensoren: PV-Prognose heute/Rest/morgen, PV-Sauberkeit",
            "Neue Optionen: pv_flaechen, Sensoren fuer die gemessene PV-Erzeugung",
        ],
    },
    {
        "version": "0.5.1",
        "datum": "2026-10-03",
        "titel": "Icon und Logo",
        "aenderungen": ["Icon und Logo fuer den Add-on-Store, Symbol auch in der Oberflaeche"],
    },
    {
        "version": "0.5.0",
        "datum": "2026-10-03",
        "titel": "Neue Oberflaeche im eedc-Stil, Energiefluss, PV-Prognose",
        "aenderungen": [
            "Oberflaeche im Stil von eedc: Reiter Live/Bilanz/Ladevorgaenge/Diagnose, Kennzahl-Kacheln, Hell/Dunkel",
            "Energiefluss: PV, Netz, Hausakku, Haus und Auto mit animierten Linien; Aufteilung PV/Akku/Netz unter dem Auto",
            "PV-Prognose aus HA (Energie-Dashboard): Rest heute, morgen, Stundenwerte als Diagramm",
            "Texte mit echten Umlauten",
        ],
    },
    {
        "version": "0.4.0",
        "datum": "2026-10-03",
        "titel": "Treiber ids",
        "aenderungen": [
            "Treiber ids: go-e im Eco-Modus, das Add-on sendet alle 2 s einen virtuellen Netzwert (pGrid = P_auto - P_erlaubt)",
            "Sollkonfiguration der go-e (lmo, fup, frc, psm, frm, amp) wird ueberwacht und bei Abweichung nachgestellt",
            "Sofort: fest dreiphasig mit Maximalstrom; Aus: Laden gesperrt",
            "Harte Grenzen: amp einphasig begrenzt (Schieflast/Fahrzeug), Ueberstrom -> Laden gesperrt und verriegelt",
            "Trockenlauf zeigt, was geschrieben wuerde; geschrieben wird nur mit trockenlauf: false",
        ],
    },
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
