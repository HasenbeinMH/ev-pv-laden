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

1. `trockenlauf: false` in den Optionen, Add-on neu starten, dann den Trockenlauf in der
   Oberfläche (Kennzeichen oben) oder in HA (`switch.ev_pv_laden_trockenlauf`) ausschalten
   – zwei Stufen wie Hauptschalter + Betriebsart. Modus **Nur PV**.
   - [ ] Sollkonfiguration kommt an (Stellglied-Tabelle „ok“, Entitäten in HA)
   - [ ] `sensor.goe_325656_pgrid` zeigt den gesendeten virtuellen Netzwert,
         `…_inva_delta` < 3 s
2. Modus **Aus** → [ ] `frc=1` geschrieben. Zurück auf **Nur PV** → [ ] `frc=0`.
3. In der go-e-App `lmo` von Hand ändern → [ ] Add-on stellt nach ≤ 30 s zurück.
4. **Watchdog-Zeit messen:** Add-on stoppen, `…_pgrid` beobachten.
   - [ ] Zeit bis `unknown`/null: ____ s (Doku: ~5 s)
5. Add-on wieder starten → [ ] Werte kommen wieder an.

## Schritt 2 – mit Auto (EV3)

0. Ab 0.13.0: Modus wählen, Einstellungen prüfen, **Start** drücken (gestoppt = Wallbox gesperrt).
   [ ] Abstecken stoppt. [ ] Ladung über die go-e-App bei gestopptem HA wird nach dem Neustart
   als „von außen“ erkannt und nicht abgebrochen.
1. **Nur PV** bei Sonne: [ ] go-e startet, folgt `P_erlaubt` (Diagramm: Auto ≈ P_erlaubt),
   [ ] Netz ≈ 0, [ ] Akku lädt nicht unter Schwelle für das Auto um.
2. Wolke: [ ] Mindestleistung während Stopp-Verzögerung, [ ] Stopp nach Verzögerung.
3. **Min + PV** abends: [ ] lädt mit 6 A, nimmt sie die go-e über ids an? (Annahme!)
   Falls nicht → Treiber A (Schritt 3).
4. **Sofort**: [ ] dreiphasig, 24 A, [ ] kein ids.
5. **Schieflast**: einphasig laden lassen (kleiner Überschuss) → [ ] `amp` = 16 A (bzw.
   EV3-Grenze), [ ] Strom einphasig nie über 20 A.
6. **pPv real vs. 0** (`ids_ppv_senden`): [ ] Unterschied im Verhalten? ____
7. **Wiederanlauf nach Wolkenpause** (Discussion #126): [ ] lädt nach der Pause wieder an.
   Falls nicht: Ereignis „wiederanlauf“ prüfen – [ ] hat `fup` umschalten geholfen?
   [ ] Texte des Fahrzeugstatus (`sensor.goe_325656_car_value`) notieren: lädt ____,
   wartet ____, beendet ____ (die Erkennung nimmt „beendet/warte/fehler“ aus – Annahme).

## Schritt 3 – Treiber A (M6, Ausweich)

Treiber A stellt den Strom selbst: `lmo=3`, `psm=2` (fest dreiphasig), `fup` aus,
Start/Stopp über `frc` (0 = laden, 1 = gesperrt), `amp` = P_erlaubt ÷ 690 V, abgerundet.
Start erst ab 3 × 6 A = 4,1 kW, Stopp unter 3,8 kW (gleiche Hysterese wie eingestellt).

1. Ohne Auto: Lademodus → Stellglied **A**.
   - [ ] Sollkonfiguration kommt an (`lmo=3`, `psm=2`, `fup` aus, `frc=1`)
2. Mit Auto bei > 4,5 kW Überschuss:
   - [ ] Start: `frc=0`, go-e lädt **mit `frc=0` im Standardmodus** (Annahme! Falls nicht,
         braucht A `frc=2` – melden)
   - [ ] `amp` folgt P_erlaubt in 1-A-Stufen, höchstens alle 10 s; Ströme L1–L3 gleich
   - [ ] Stopp bei Wolke: `frc=1` nach Stopp-Verzögerung
3. Add-on stoppen während der Ladung → [ ] `frc=1` geschrieben, Ladung endet.
   Bei einem Absturz bleibt die go-e auf dem letzten Strom – dagegen hilft die
   Watchdog-Automation (M8).
4. Zurück auf **ids** (während Pause) → [ ] Sollkonfiguration ids kommt an.

## Schritt 4 – Zielzeit (M7)

1. Auto anstecken, SoC in der Oberfläche eintragen, Modus **Zielzeit**, Abfahrt so wählen,
   dass der späteste Start in ~10 min liegt.
   - [ ] vorher: „nur PV bis HH:MM“, danach: Netzladen mit voller Leistung (Sofort)
   - [ ] SoC steigt mit dem Wallbox-Zähler (Vergleich mit der Anzeige im Auto: ____ %
         bei Add-on ____ % → Ladewirkungsgrad ggf. anpassen)
2. Ziel erreicht → [ ] weiter wie Nur PV. Abstecken → [ ] SoC verfällt.
3. **Hausakku beobachten:** Bei Netzladen deckt der SolarEdge-Akku den Bezug mit – er
   entlädt sich ins Auto (bis zu seiner Maximalleistung). [ ] Wie viel? ____ kW.
   Entscheidung, ob das gewollt ist (sonst: Akku-Entladesperre über SolarEdge, eigener Punkt).

## Schritt 5 – Bedienung, Watchdog, Meldungen (M8)

1. Automationen aus `docs/automationen.yaml` anlegen.
2. In HA Lademodus, Ladestand, Abfahrt ändern → [ ] Oberfläche übernimmt, ungültige Eingabe
   (z. B. Abfahrt 25:00) wird abgelehnt und HA zeigt wieder den alten Wert.
3. **Watchdog** (Treiber A, Auto lädt): Add-on stoppen →
   [ ] nach ≤ 3 min `frc=1`, Ladung endet, [ ] Telegram kommt.
   [ ] Optionswerte von `select.goe_325656_frc` sind „0/1/2“ (Annahme – sonst Vorlage anpassen).
4. Auto voll laden lassen → [ ] Telegram „Auto fertig geladen“ mit kWh und PV-Anteil.
   [ ] Text des Fahrzeugstatus bei voller Batterie: ____ (Erkennung: „beendet“/„complete“).

## Schritt 6 – EV Tracker (M9)

1. Im EV Tracker: Einstellungen → „Ladungen aus Home Assistant empfangen“ → Token erzeugen;
   dort steht auch die Adresse (`http://<Add-on-Host>:8099/api/ladung`).
2. Add-on-Optionen: `ev_tracker_url` (Adresse, `/api/ladung` darf fehlen), `ev_tracker_token`,
   ggf. `ev_tracker_fahrzeug` (z. B. „EV3“) – Add-on neu starten.
3. [ ] Reiter Ladevorgänge zeigt „EV Tracker: alles übergeben“ bzw. offene Vorgänge.
4. Nach der ersten echten Ladung: [ ] im Tracker erscheint sie mit PV- und Netzanteil,
   [ ] kWh stimmen mit dem Add-on überein, [ ] Netzpreis = Tagestarif des Trackers.

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
