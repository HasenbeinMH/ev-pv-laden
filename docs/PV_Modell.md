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

## Betrieb im Add-on

- Training beim ersten Start und danach wöchentlich (bis 3 Jahre HA-Statistik + Open-Meteo).
- Sauberkeit täglich aus den letzten 14 Tagen (seit der letzten Reinigung).
- Prognose stündlich; bis zum ersten Training zeigt das Add-on die HA-Prognose
  (Energie-Dashboard, z. B. Forecast.Solar).
- HA-Sensoren: `sensor.ev_pv_laden_pv_prognose_heute`, `…_rest_heute`, `…_morgen`,
  `…_pv_sauberkeit`.
