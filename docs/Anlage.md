# PV-Anlage – Stammdaten

Quelle: SolarEdge-Monitoring (Layout „Physisch“), Angaben Daniel, 2026-10-04.

- Inbetriebnahme: 06.11.2020
- Wechselrichter: SolarEdge (1 Gerät) mit Leistungsoptimierern je Modul
- 27 Module à 370 Wp = **9,99 kWp**
- Hausakku: BYD HVS (über SolarEdge, Modbus)

## Flächen

| Fläche | Neigung | Azimut (0° N, 90° O, 180° S) | Module | Leistung |
|---|---|---|---|---|
| Süd | 6° | 179° | 9 | 3.330 Wp |
| Nord | 14° | 359° | 9 | 3.330 Wp |
| Ost | 34° | 86° | 9 | 3.330 Wp |

Gemessen 2026-10-04: Neigung mit Wasserwaagen-App am Modulrahmen (Daniel), Azimut aus dem
Luftbild (GEOportal.NRW, Richtung der Modulkanten per Strukturtensor, UTM-Meridiankonvergenz
−1,7° berücksichtigt; Süd/Nord ±1°, Ost ±2°). Vorher eingetragen: 8°/180°, 12°/0°, 25°/90°.
Im SolarEdge-Portal sind Neigung/Ausrichtung falsch hinterlegt (0°/180°) – betrifft nur dessen
eigene Prognose, nicht die Messwerte.

Langzeit je Modul (Optimierer-Gesamtenergie seit 11/2020, Summe 41.035 kWh):
Süd 15.297 kWh (100 %), Nord 14.146 kWh (92 %), Ost 11.592 kWh (76 %).
1.1.10 nur 577 kWh = 37 % des besten Ost-Moduls 1.1.21 (1.562 kWh).
Süd und Nord sind ein aufgeständertes Feld mit abwechselnden Reihen.

## Module je Fläche (Optimierer-Nummer)

- **Nord:** 1.1.15 · 1.1.18, 1.1.14, 1.1.1, 1.1.7, 1.1.16 · 1.1.24, 1.1.13, 1.1.22
- **Süd:** 1.1.20 · 1.1.3, 1.1.6, 1.1.8, 1.1.4, 1.1.12 · 1.1.9, 1.1.17, 1.1.26
- **Ost:** 1.1.21, 1.1.19, 1.1.23, 1.1.25, 1.1.11, 1.1.5, 1.1.10, 1.1.27, 1.1.2

Reihenfolge innerhalb einer Fläche: Reihen von oben nach unten wie im Layout.

## Beobachtungen

- 04.10.2026, ~10 Uhr: 1.1.10 (18 Wh) und 1.1.5 (27 Wh) deutlich unter den übrigen
  Ost-Modulen (30–48 Wh) → vermutlich Verschattung am unteren Ende der Ost-Fläche.
- 1.1.17/1.1.26 (Süd, unterste Reihe) mit 27/28 Wh unter den anderen Süd-Modulen
  (30–39 Wh) → evtl. Eigenverschattung durch die Reihe davor.
- **1.1.10 bekommt viel Schatten – durch einen Baum und das Nachbarhaus** (Daniel).
  Ost-Spalte fällt von oben nach unten ab. Modell: Korrektur nach Sonnenstand **und**
  Jahreszeit (Laub), nicht nur nach Sonnenstand.

| Zeitraum | Süd | Nord | Ost | Ost/Süd | 1.1.10 / 1.1.21 |
|---|---|---|---|---|---|
| 12.08.–01.09.2026 | 188 kWh | 178 kWh | 131 kWh | 70 % | 6 / 19 kWh = 32 % |
| 03.10.2026 | 7,03 kWh | 5,42 kWh | 3,14 kWh | 45 % | 135 / 517 Wh = 26 % |

→ Verschattung der Ost-Fläche nimmt bei tiefer Sonne (Herbst) deutlich zu.
