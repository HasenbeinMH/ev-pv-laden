# Eigenes PV-Prognosemodell

Stand 2026-10-04. Code: `pvmodell.py` (Logik), `pvdaten.py` (Daten), `pvprognose.py` (Laufzeit).
Herleitung und Prüfung: `dev/modell/` (Daten unter `dev/data/modell/`, nicht im Repo).

## Idee

Wetter kann ein Anlagenmodell nicht vorhersagen – dafür bleibt Open-Meteo zuständig. Gelernt
wird alles, was **an dieser Anlage** systematisch anders ist: Verschattung je Sonnenstand
(Nachbarhaus im Süden, Bäume im Westen), Wirkungsgrad, mittlere Verschmutzung und die
typischen Fehler der Wetterprognose.

    PV(Stunde) = Einstrahlung je Dachfläche × kWp × Kennfeld(Sonnenstand, Halbjahr) × Reinigungszuschlag

- **Einstrahlung:** Open-Meteo, Strahlung auf die geneigte Fläche (GTI), je Fläche.
- **Kennfeld:** Faktor je Feld aus Sonnenazimut (15°) × Sonnenhöhe (5°), getrennt nach
  Apr–Sep und Okt–Mär (Laub). Wie ein Kennfeld in der Steuerungstechnik.
- **Reinigungszuschlag:** nur nach dem Knopf „Anlage gereinigt“, 90 Tage lang:
  Sauberkeit jetzt ÷ Sauberkeit im Mittel (im Mittel steckt die übliche Verschmutzung schon
  im Kennfeld).

## Messung

PV-Erzeugung aus der HA-Langzeitstatistik, stündlich. SolarEdge-Hybrid:

    PV = DC-Leistung + Akku geladen − Akku entladen

Geprüft gegen `sensor.pv_erzeugung_kwh` (Mai–Sep 2026): +2 bis +3 % je Monat.

## Ergebnis (Training 2024–2025, Test 2026 – Testdaten nie gesehen)

| Verfahren | Fehler je Stunde | Fehler je Tag | Fehler je Tag (Tage > 3 kWh) |
|---|---|---|---|
| Standard (Einstrahlung × kWp × fester Faktor) | 0,52 kWh | 3,8 kWh | 23 % |
| **Kennfeld (im Add-on)** | 0,47 kWh | **2,76 kWh** | **18 %** |
| Machine Learning (Gradient Boosting) | 0,40 kWh | 2,7 kWh | 17 % |

Mit den gemessenen Flächen (Süd 6°/179°, Nord 14°/359°, Ost 34°/86° statt 8°/180°, 12°/0°,
25°/90°): 2,73 kWh bzw. 18,0 % – das Kennfeld hatte die falsche Geometrie schon weitgehend
ausgeglichen, mit der richtigen muss es weniger korrigieren.

Das Kennfeld ist fast so gut wie Machine Learning, aber nachvollziehbar und ohne
scikit-learn im Container. Beispiel 03.10.2026: gemessen 14,4 kWh, Standard 18,1 kWh,
Kennfeld 14,0 kWh.

## Verschmutzung

Zerlegung mit nachträglich **gemessener** Einstrahlung (Open-Meteo-Archiv, ohne Wetterfehler):

    Messung ≈ Einstrahlung × Kennfeld_Archiv(Sonnenstand) × Sauberkeit(Woche)

- Sauberkeit 1 = die saubersten Wochen der Historie. Mittel 2024–2025: 0,83 (≈ 17 % Verlust).
- Reinigung im Mai 2025 deutlich sichtbar (Sprung auf ~1,0), danach langsamer Abfall.
- Herbst 2026: ~0,78 → Reinigung bringt ~+25 %, passt zu Daniels Erfahrung (+30 %).
- Nov–Feb nicht ausgewertet (Schnee, tiefe Sonne).

**Warum nicht in jede Prognose?** Getestet: Die laufende Schätzung schwankt um einige Prozent
und machte die Tagesprognose schlechter (2,77 → 3,04 kWh). Deshalb dient sie als Anzeige und
Reinigungshinweis; nur nach einer gemeldeten Reinigung wirkt sie auf die Prognose.

## Morgentau

Das Kennfeld kennt den Morgentau nur als Mittelwert. Nach klaren, feuchten, windstillen
Nächten liegt im Winterhalbjahr (Okt–März) morgens Tau auf den Modulen, und die ersten
Sonnenstunden bringen deutlich weniger. Auswertung 2024–2026 (`dev/modell/tau.py`): nach
Tau-Nächten am Morgen etwa 0,7–0,8 der Prognose, im Sommer kein Effekt.

Seit 0.14.0 (`morgentau.py`): Aus der Open-Meteo-Prognose der Nacht (9 h vor Sonnenaufgang)
wird die Nacht eingestuft:

| Klasse | Bedingung |
|---|---|
| nass (Regen) | mehr als 0,2 mm Regen in der Nacht |
| Tau wahrscheinlich | Temperatur – Taupunkt ≤ 1,5 K (letzte 3 h vor Sonnenaufgang), Wolken < 50 %, Wind < 12 km/h |
| Tau möglich | Temperatur – Taupunkt ≤ 3 K, Wolken < 70 % |
| trocken | sonst |

Bei „Tau wahrscheinlich“ und „Tau möglich“ werden im Winterhalbjahr die ersten 4
Sonnenstunden mit dem Faktor 0,7 gerechnet (Startwert, am 18.10.2026 mit echten
Herbstmorgen nachjustieren). Je Tag werden Klasse, Merkmale und Morgenprognose ohne/mit
Korrektur im Protokoll, in den Ereignissen und in der Datenbank (`morgentau_protokoll`,
120 Tage) festgehalten. Ohne Wetterdaten bleibt die Prognose unkorrigiert.

## 7-Tage-Vorschau

Seit 0.15.0 (`wochenprognose.py`): Die eigene Prognose rechnet 8 Tage (heute + 7). Je Stunde:
Überschuss = PV – typischer Hausverbrauch dieser Uhrzeit (Mittel der letzten 4 Wochen aus
der HA-Statistik, Auto herausgerechnet). Davon bekommt zuerst der Hausakku seinen typischen
Tagesbedarf (mittlere Entladung je Tag der letzten 14 Tage), der Rest zählt fürs Auto – aber
nur Stunden mit mindestens 1,4 kW (kleinste Ladeleistung, 6 A einphasig). Ampel: ab 6 kWh
„lohnt sich“, ab 2 kWh „mäßig“, sonst „kaum“. Anzeige im Reiter Prognose und als HA-Sensor
`sensor.ev_pv_laden_pv_woche_auto` (Zustand = kWh fürs Auto in 7 Tagen, Attribut `tage`).
Ab Tag 4 wird die Wetterprognose spürbar unsicherer.

## Betrieb im Add-on

- Training beim ersten Start und danach wöchentlich (bis 3 Jahre HA-Statistik + Open-Meteo).
- Sauberkeit täglich aus den letzten 14 Tagen (seit der letzten Reinigung).
- Prognose stündlich; bis zum ersten Training zeigt das Add-on die HA-Prognose
  (Energie-Dashboard, z. B. Forecast.Solar).
- HA-Sensoren: `sensor.ev_pv_laden_pv_prognose_heute`, `…_rest_heute`, `…_morgen`,
  `…_pv_sauberkeit`.
