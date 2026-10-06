# -*- coding: utf-8 -*-
"""
Version und Aenderungslog von EV PV-Laden.

Pflege bei einer neuen Version (wie beim EV Tracker):
  1. VERSION erhoehen (major.minor.patch), config.yaml "version:" mitziehen
  2. Oben in CHANGELOG einen neuen Eintrag einfuegen – neueste Version zuerst
  3. CHANGELOG.md (Update-Dialog des Add-on-Stores) passend ergaenzen
"""

VERSION = "0.12.0"

CHANGELOG = [
    {
        "version": "0.12.0",
        "datum": "2026-10-06",
        "titel": "PV-Prognose im Energie-Dashboard",
        "aenderungen": [
            "Neue HA-Integration 'EV PV-Laden Prognose' (HACS, Ordner custom_components): bringt die Prognose des eigenen Modells ins Energie-Dashboard und liefert Sensoren heute, Rest heute, morgen, aktuelle Stunde, naechste Stunde, naechste 3 Stunden (Stundenwerte als Attribut)",
            "Add-on: Schnittstelle /api/prognose/stunden fuer die Integration",
            "Die eigene Prognose wird aus der HA-Prognose herausgerechnet (kein Kreislauf beim Vergleich)",
        ],
    },
    {
        "version": "0.11.2",
        "datum": "2026-10-06",
        "titel": "Dachflaechen im Reiter Prognose",
        "aenderungen": ["Reiter Prognose, PV-Anlage: Tabelle der Dachflaechen mit Neigung, Ausrichtung und Leistung"],
    },
    {
        "version": "0.11.1",
        "datum": "2026-10-05",
        "titel": "Schalter Nachtladen im Dashboard",
        "aenderungen": [
            "Statt der Auswahl ein Schalter 'Nachtladen' im Dashboard und in HA: an = ohne PV voll aus dem Netz, aus = Pause bis PV da ist",
            "Gilt fuer Nur PV und Min + PV; 'Mindestleistung weiter' entfaellt (gespeichert -> aus)",
        ],
    },
    {
        "version": "0.11.0",
        "datum": "2026-10-05",
        "titel": "Min + PV: Verhalten ohne PV",
        "aenderungen": [
            "Neue Einstellung fuer Min + PV, wenn keine PV da ist (Nacht): Mindestleistung weiter, voll aus dem Netz oder Pause bis PV da ist",
            "Erkennung ueber die gemessene PV-Leistung mit Hysterese: keine PV unter 50 W fuer 15 min, PV wieder da ueber 300 W fuer 5 min (einstellbar)",
            "Auch als HA-Auswahl 'Min + PV ohne PV'",
        ],
    },
    {
        "version": "0.10.5",
        "datum": "2026-10-05",
        "titel": "PV-Prognose mit gemessenem Verlauf",
        "aenderungen": [
            "Reiter Prognose: gemessene PV-Erzeugung heute als Stundenbalken neben der Prognose, dazu 'bis jetzt gemessen gegenueber Prognose' in kWh und Prozent",
            "Dashboard 'Heute': PV-Prognose als gestrichelte Linie ueber der gemessenen PV-Kurve",
        ],
    },
    {
        "version": "0.10.4",
        "datum": "2026-10-04",
        "titel": "Tageskurve nach Neustart vollstaendig",
        "aenderungen": [
            "Dashboard 'Heute': nach einem Neustart oder Update wird der Verlauf seit Mitternacht aus der HA-Historie nachgeladen",
            "y-Achse der Tageskurve mit Nachkommastelle (0,5 / 1 / 1,5 kW statt doppelter Werte)",
        ],
    },
    {
        "version": "0.10.3",
        "datum": "2026-10-04",
        "titel": "Gemeinsame Zaehler mit dem EV Tracker",
        "aenderungen": [
            "Neue HA-Zaehler 'EV Tracker: PV ins Auto' und 'EV Tracker: Netz ins Auto' (Hausakku wie bei den Einzelladungen) - im Tracker als Monatssensoren eintragen",
            "Status der Uebergabe in HA: Uebergabe, offene Ladungen, zuletzt uebergeben",
            "Ladebeginn und -ende gehen als Ortszeit ohne Zeitzone an den Tracker (wie dessen HA-Vorlage)",
        ],
    },
    {
        "version": "0.10.2",
        "datum": "2026-10-04",
        "titel": "EV Tracker: Verbindung testen",
        "aenderungen": ["Knopf 'Verbindung testen' bei den Ladevorgaengen: prueft Adresse und Token des EV Trackers mit einer leeren Testladung, die dort nicht gespeichert wird"],
    },
    {
        "version": "0.10.1",
        "datum": "2026-10-04",
        "titel": "Fuer alle Benutzer sichtbar",
        "aenderungen": ["Seitenleisten-Eintrag fuer alle HA-Benutzer sichtbar, nicht nur fuer Admins (panel_admin: false)"],
    },
    {
        "version": "0.10.0",
        "datum": "2026-10-04",
        "titel": "Uebergabe an den EV Tracker",
        "aenderungen": [
            "Beendete Ladevorgaenge gehen automatisch an den EV Tracker (POST /api/ladung mit Token): Start, Ende, kWh PV und Netz",
            "Hausakku zaehlt als PV (akku_als_netz: false) oder Netz; Kosten rechnet der Tracker mit seinem Tagestarif",
            "Sendepuffer: nicht erreichbar oder falscher Token -> spaeter erneut; vom Tracker abgelehnt -> vermerkt, kein Wiederholen",
            "Neue Option ev_tracker_fahrzeug; Spalte EV Tracker und Knopf 'jetzt senden' bei den Ladevorgaengen",
            "Energiefluss mit zentralem Netzknoten; Haus als eigene Kachel",
            "Neues Dashboard ohne Scrollen; Reiter Dashboard/Laden/Verlauf/Prognose/Einstellungen/Diagnose",
        ],
    },
    {
        "version": "0.9.0",
        "datum": "2026-10-04",
        "titel": "Bedienung aus HA, Trockenlauf-Schalter, Meldungen",
        "aenderungen": [
            "HA-Entitaeten zum Bedienen: Lademodus, Treiber, Trockenlauf, Hausakku-Schwelle, SoC Auto, Ziel-SoC, Abfahrt, Puffer",
            "Trockenlauf in zwei Stufen: Add-on-Option sperrt fest; ist sie aus, schaltet Oberflaeche oder HA (Anfangswert an)",
            "Ereignis event.ev_pv_laden_ladung: Auto fertig geladen / Ziel-SoC erreicht, mit kWh und PV-Anteil",
            "Vorlagen fuer Watchdog- und Telegram-Automation (docs/automationen.yaml)",
        ],
    },
    {
        "version": "0.8.0",
        "datum": "2026-10-04",
        "titel": "Zielzeit / Ziel-SoC",
        "aenderungen": [
            "Modus Zielzeit: bis zum spaetesten Start nur PV, danach Netzladen bis zum Ziel-SoC (selbsthaltend bis Ziel oder Abstecken)",
            "Spaetester Start = Abfahrt - benoetigte kWh / P_max - Puffer; P_max = min(Auto, Wallbox-Grenze)",
            "SoC des Autos: Eingabe in der Oberflaeche oder Sensor, Hochrechnung mit dem Wallbox-Zaehler; verfaellt beim Abstecken",
            "Ohne SoC laedt Zielzeit nur mit PV und meldet den Grund",
            "Neue Optionen ev_max_leistung_kw (22) und sensor_auto_soc; neue HA-Sensoren SoC Auto und spaetester Netzstart",
        ],
    },
    {
        "version": "0.7.0",
        "datum": "2026-10-04",
        "titel": "Treiber A und Wiederanlauf-Erkennung",
        "aenderungen": [
            "Treiber A als Ausweich: das Add-on stellt den Ladestrom selbst (Standardmodus, fest dreiphasig, Start/Stopp ueber frc); Start erst ab 3 x 6 A",
            "Treiberwahl in der Oberflaeche (ids / A), gewechselt wird nur, wenn nicht geladen wird",
            "Wiederanlauf-Erkennung (ids): Freigabe, Auto steckt, laedt aber nicht -> melden, fup kurz umschalten oder bis zum Abstecken auf Treiber A",
            "Treiber A sperrt die Ladung beim Beenden des Add-ons (kein go-e-Watchdog wie bei ids)",
            "go-e-Status aus der Klartext-Entity (modelstatus_value), neu: Fahrzeugstatus (car_value)",
        ],
    },
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
