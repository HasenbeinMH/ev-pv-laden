# M5 – Inbetriebnahme Treiber „ids“

Reihenfolge wie bei einer SPS-Inbetriebnahme: erst Signale prüfen (Trockenlauf), dann
Stellglied ohne Last (ohne Auto), dann mit Last. Jeder Schritt erst nach OK.

## Voraussetzungen

- [ ] evcc-Add-on gestoppt, Boot „manuell“ (erledigt 2026-10-03)
- [ ] go-e online, marq24-Integration „geladen“ (nicht `setup_retry`)
- [ ] `ama` in der go-e-App auf 24 A (Warnung im Ereignisprotokoll prüfen)
- [ ] Add-on ≥ 0.4.0 installiert, `trockenlauf: true`

## Schritt 0 – Trockenlauf mit echten Werten

- [ ] Alle Pflicht-Signale „gültig“, Vorzeichen plausibel (Einspeisung → Netz negativ,
      Akku lädt → Akku negativ)
- [ ] Spalte „Intervall (max)“: Lebenszeichen Wallbox (`rbt`) deutlich unter `max_alter_s`
      (15 s). Sonst anderes Lebenszeichen wählen.
- [ ] Stellglied-Tabelle zeigt „würde schreiben“: `lmo=4`, `fup=an`, `frc=0`, `psm=0`,
      `frm=2`, `amp=16`, dazu `ids pGrid=…` alle 2–3 s
- [ ] Regelentscheidungen im Ereignisprotokoll plausibel (einige Tage mitlaufen lassen,
      sonnige und wechselhafte Tage als CSV exportieren → `pytest`)

## Schritt 1 – Stellglied ohne Auto (schreibt erstmals!)

Die Wallbox lädt nicht, weil kein Auto steckt – geprüft wird nur der Schreibweg.

1. `trockenlauf: false`, Add-on neu starten, Modus **Nur PV**.
   - [ ] Sollkonfiguration kommt an (Stellglied-Tabelle „ok“, Entitäten in HA)
   - [ ] `sensor.goe_325656_pgrid` zeigt den gesendeten virtuellen Netzwert,
         `…_inva_delta` < 3 s
2. Modus **Aus** → [ ] `frc=1` geschrieben. Zurück auf **Nur PV** → [ ] `frc=0`.
3. In der go-e-App `lmo` von Hand ändern → [ ] Add-on stellt nach ≤ 30 s zurück.
4. **Watchdog-Zeit messen:** Add-on stoppen, `…_pgrid` beobachten.
   - [ ] Zeit bis `unknown`/null: ____ s (Doku: ~5 s)
5. Add-on wieder starten → [ ] Werte kommen wieder an.

## Schritt 2 – mit Auto (EV3)

1. **Nur PV** bei Sonne: [ ] go-e startet, folgt `P_erlaubt` (Diagramm: Auto ≈ P_erlaubt),
   [ ] Netz ≈ 0, [ ] Akku lädt nicht unter Schwelle für das Auto um.
2. Wolke: [ ] Mindestleistung während Stopp-Verzögerung, [ ] Stopp nach Verzögerung.
3. **Min + PV** abends: [ ] lädt mit 6 A, nimmt sie die go-e über ids an? (Annahme!)
   Falls nicht → Fallback Treiber A (M6).
4. **Sofort**: [ ] dreiphasig, 24 A, [ ] kein ids.
5. **Schieflast**: einphasig laden lassen (kleiner Überschuss) → [ ] `amp` = 16 A (bzw.
   EV3-Grenze), [ ] Strom einphasig nie über 20 A.
6. **pPv real vs. 0** (`ids_ppv_senden`): [ ] Unterschied im Verhalten? ____
7. **Wiederanlauf nach Wolkenpause** (Discussion #126): [ ] lädt nach der Pause wieder an.

## Zusammenspiel mit den Einstellungen der go-e selbst

Die go-e hat im Eco-Modus eigene Start-/Stopp-Logik. Sie wirkt *zusätzlich* zur Strategie
des Add-ons und verzögert ggf. nur. Werte notieren und bei Bedarf angleichen:

| go-e | Bedeutung | Stand 2026-10-03 | Empfehlung |
|---|---|---|---|
| `pgt` | Netz-Leistung Ziel | 0 W | 0 W (das Ziel steckt im virtuellen Netzwert) |
| `fmt` | Mindestladezeit | 5 min | ≤ Mindestladedauer Add-on (10 min) |
| `fst` | Startleistung | (Entity deaktiviert) | ≤ Start-Schwelle Add-on (1,4 kW) |
| `spl3` | Umschaltung auf 3-phasig | 4200 W | so lassen |
| `acp` | Ladepausen zulassen | an | an (marq24-Empfehlung) |
| `po` | Prioritäts-Offset | −300 W | prüfen, ggf. 0 |
