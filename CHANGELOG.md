# Changelog

Alle nennenswerten Aenderungen des Add-ons EV PV-Laden.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [0.10.3] - 2026-10-04

Gemeinsame Zähler mit dem EV Tracker.

- Neue HA-Zähler **„EV Tracker: PV ins Auto“** (`sensor.ev_pv_laden_tracker_kwh_pv`) und **„EV Tracker: Netz ins Auto“** (`sensor.ev_pv_laden_tracker_kwh_netz`) – mit derselben Aufteilung wie die Einzelladungen (Hausakku zählt als PV, bei `akku_als_netz: true` als Netz). Im EV Tracker unter Einstellungen als „PV ins Auto“ und „Netz ins Auto“ eintragen: Dann zieht sein Monatsimport die Einzelladungen von genau diesen Zählern ab, nichts wird doppelt oder gar nicht gezählt
- Status der Übergabe in HA: „EV Tracker: Übergabe“ (alles übergeben / n offen / Fehlertext), „offene Ladungen“ und „zuletzt übergeben“
- Ladebeginn und -ende gehen als Ortszeit ohne Zeitzone an den Tracker – wie bei dessen HA-Vorlage; vorher hing die Uhrzeit von der Zeitzone im Tracker-Container ab

## [0.10.2] - 2026-10-04

- Reiter Laden → Ladevorgänge: Knopf **„Verbindung testen“** prüft Adresse und Token des EV Trackers. Gesendet wird eine leere Testladung – der Tracker lehnt sie nach der Token-Prüfung ab (422) und speichert nichts. Ergebnis: „Verbindung in Ordnung“, „Token abgelehnt“ oder „nicht erreichbar“; es steht auch im Ereignisprotokoll

## [0.10.1] - 2026-10-04

- Der Eintrag „EV PV-Laden“ in der Seitenleiste ist jetzt für alle Benutzer von Home Assistant sichtbar, nicht nur für Admins (`panel_admin: false`). Die Add-on-Optionen kann weiterhin nur ein Admin ändern; der feste Trockenlauf (`trockenlauf: true`) bleibt eine Sperre, die über die Oberfläche nicht aufgehoben werden kann

## [0.10.0] - 2026-10-04

Übergabe an den EV Tracker.

- Jeder beendete Ladevorgang geht automatisch an den EV Tracker (`POST /api/ladung` mit Bearer-Token): Start, Ende, kWh PV und kWh Netz. Den Preis des Netzanteils rechnet der Tracker mit seinem Tagestarif
- Der Hausakku zählt als PV (`akku_als_netz: false`, Standard) oder als Netz
- Sendepuffer: Ist der Tracker nicht erreichbar oder der Token falsch, bleibt der Vorgang offen und wird später erneut gesendet (Abstand wächst bis 1 h). Lehnt der Tracker die Daten ab, wird das vermerkt und nicht wiederholt. Erneutes Senden überschreibt im Tracker – nichts wird doppelt gezählt
- Neue Option `ev_tracker_fahrzeug` (Nummer oder Name, leer = Hauptfahrzeug)
- Ladevorgänge: neue Spalte „EV Tracker“ (übergeben / offen / abgelehnt) und Knopf „jetzt senden“
- **Neues Dashboard** – alles auf einen Blick ohne Scrollen (ab 1366 × 768): Kacheln PV/Haus/Hausakku/Auto, Energiefluss, Autokarte (SoC mit Ziel, Ladeleistung, Status, Zielzeit-Plan, „Laden pausieren“), Lademodus, Tageskurve „Heute“ und Tagesbilanz ins Auto mit PV-Anteil; Uhr im Kopf
- Reiter neu geordnet: Dashboard · Laden (Modus, Stellglied, Zielzeit, Entscheidung, Ladevorgänge) · Verlauf · Prognose · Einstellungen · Diagnose
- Energiefluss mit zentralem Netzknoten (Sternpunkt des Hausnetzes): PV, Netz und Hausakku speisen ein, Haus und Auto beziehen – das Haus hat jetzt eine eigene Kachel

## [0.9.0] - 2026-10-04

Bedienung aus Home Assistant, Trockenlauf-Schalter, Meldungen.

- **HA-Entitäten zum Bedienen:** Lademodus und Treiber (Auswahl), Trockenlauf (Schalter), Hausakku-Schwelle, SoC Auto, Ziel-SoC, Zielzeit-Puffer (Zahl), Abfahrt (Text HH:MM). HA zeigt immer den Wert, den das Add-on übernommen hat – ungültige Eingaben werden abgelehnt und im Ereignisprotokoll vermerkt. Der bisherige Sensor „Lademodus“ entfällt (ersetzt durch die Auswahl)
- **Trockenlauf in zwei Stufen** (wie Hauptschalter und Betriebsartenwahl): `trockenlauf: true` in den Optionen sperrt fest. Ist die Option aus, wird der Trockenlauf in der Oberfläche (Klick auf das Kennzeichen oben) oder in HA geschaltet – Anfangswert „an“, gespeichert. Beim Einschalten sperrt Treiber A vorher die Ladung
- **Meldungen:** `event.ev_pv_laden_ladung` mit „fertig“ (Fahrzeug meldet Ladung beendet) und „ziel_erreicht“ (Zielzeit), je einmal pro Ansteckvorgang, mit kWh, PV-Anteil und SoC
- **Vorlagen** in `docs/automationen.yaml`: Watchdog (sperrt die Ladung, wenn das Add-on 2 min schweigt, und meldet per Telegram) und Telegram-Nachricht „Auto fertig geladen“

## [0.8.0] - 2026-10-04

Zielzeit / Ziel-SoC.

- **Modus Zielzeit:** Bis zum spätesten Start lädt das Add-on nur mit PV, danach mit voller Leistung aus dem Netz bis zum Ziel-SoC. Die Netzphase hält sich selbst, bis das Ziel erreicht oder das Auto abgesteckt ist – auch über die Abfahrtszeit hinaus. Danach weiter wie „Nur PV“
- Spätester Start = Abfahrt − benötigte kWh ÷ P_max − Puffer, neu gerechnet in jedem Zyklus (was die Sonne vorher lädt, schiebt ihn nach hinten). P_max = kleinerer Wert aus Auto (`ev_max_leistung_kw`, Standard 22) und Wallbox-Grenze (24 A dreiphasig = 16,6 kW)
- **SoC des Autos:** in der Oberfläche eintragen oder per Sensor (`sensor_auto_soc`); dazwischen rechnet der Zähler der Wallbox hoch (× Ladewirkungsgrad ÷ Akkukapazität). Beim Abstecken verfällt der Wert
- Ohne SoC lädt die Zielzeit nur mit PV und sagt warum – nie blind aus dem Netz
- PV-Prognose bis zur Abfahrt als Hinweis (noch nicht in der Planung)
- Neue HA-Sensoren: SoC Auto (geschätzt), Zielzeit: spätester Netzstart

## [0.7.0] - 2026-10-04

Treiber A als Ausweich und Erkennung, wenn die Ladung nach einer Pause nicht wieder anläuft.

- **Treiber A:** Das Add-on stellt den Ladestrom selbst – Standardmodus, fest dreiphasig, Start/Stopp über `frc`, Strom in 1-A-Stufen höchstens alle 10 s. Start erst ab 3 × 6 A (4,1 kW), die Stopp-Schwelle wandert mit derselben Hysterese mit
- Treiberwahl in der Oberfläche (Lademodus → Stellglied); gewechselt wird nur, wenn gerade nicht geladen wird
- **Wiederanlauf-Erkennung** (Treiber ids, bekanntes Problem FW 59.4): Freigabe da, Auto steckt, lädt aber nicht seit 5 min → nur melden, `fup` kurz umschalten oder nach 2 erfolglosen Versuchen bis zum Abstecken auf Treiber A (Standard). Einstellbar in den Strategie-Parametern
- Treiber A sperrt die Ladung beim Beenden des Add-ons – er hat keinen go-e-Watchdog wie ids
- go-e-Grund aus `sensor.goe_…_modelstatus_value` (die Code-Entity ist ab Werk deaktiviert), neu: Fahrzeugstatus `…_car_value`

## [0.6.1] - 2026-10-04

- Hausverbrauch im Energiefluss aus eigenem Sensor (`sensor_haus`). Misst er hinter dem Netzzähler und damit die Wallbox mit (`sensor_haus_enthaelt_auto: true`), zieht das Add-on die Ladeleistung ab. Ohne Sensor wird der Hausverbrauch wie bisher aus PV, Netz, Akku und Auto berechnet.

## [0.6.0] - 2026-10-04

Eigenes PV-Prognosemodell, auf die Anlage zugeschnitten (Details: `docs/PV_Modell.md`).

- PV-Prognose = Open-Meteo-Einstrahlung je Dachfläche × gelerntes Kennfeld (Verschattung je Sonnenstand, Wirkungsgrad, Laub im Sommer). Das Add-on trainiert es selbst aus der HA-Statistik (bis 3 Jahre) – im Test rund ein Viertel genauer als die Standardrechnung
- Sauberkeit der Anlage wird laufend geschätzt: Anzeige, Verlauf, Reinigungshinweis und Knopf „Anlage gereinigt“ (hebt die Prognose an)
- Prognose-Diagramm mit Vergleich zur HA-Prognose (Energie-Dashboard)
- Neue HA-Sensoren: PV-Prognose heute / Rest heute / morgen, PV-Sauberkeit
- Neue Optionen: `pv_flaechen` (Neigung, Azimut, kWp je Fläche) und die Sensoren der gemessenen PV-Erzeugung

## [0.5.1] - 2026-10-03

- Icon und Logo für den Add-on-Store, Symbol auch oben links in der Oberfläche

## [0.5.0] - 2026-10-03

Neue Oberfläche im Stil von [eedc](https://github.com/supernova1963/eedc-homeassistant).

- Reiter Live / Bilanz / Ladevorgänge / Diagnose, Kennzahl-Kacheln, Hell/Dunkel-Umschalter
- Energiefluss: PV, Netz, Hausakku, Haus und Auto mit animierten Linien; unter dem Auto die Aufteilung PV/Akku/Netz
- PV-Prognose aus Home Assistant: Rest heute, morgen, Stundenwerte als Diagramm.
  Voraussetzung: Prognose im Energie-Dashboard der PV-Quelle zugeordnet
- Texte mit echten Umlauten

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
