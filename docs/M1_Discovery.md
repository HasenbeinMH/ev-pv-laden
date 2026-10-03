# M1 – Recherche & Discovery (2026-10-03)

Legende: **[V]** verifiziert (HA live, offizielle Doku, Quellcode) · **[A]** Annahme / noch zu testen

## Anlage in Home Assistant

| Rolle | Entity | Rohes Vorzeichen | Invertieren | Aktualisierung |
|---|---|---|---|---|
| Netz | `sensor.se_modbus_daten_m1_ac_power` | + = Einspeisung [V] | ja | ~2 s [V] |
| Akku-Leistung | `sensor.se_modbus_daten_battery1_power` | + = Laden [V] | ja | ~2 s, nur bei Änderung [V] |
| Akku-SoC | `sensor.se_modbus_daten_battery1_state_of_charge` | % | – | nur bei Änderung [V] |
| PV | `sensor.nodered_338b35fcb1bd7ed8_2` (PC_DC_Leistung) | + | – | Node-RED |
| Auto-Leistung | `sensor.goe_325656_nrg_11` | W | – | WebSocket-Push |
| Wallbox-Zähler | `sensor.goe_325656_eto` | kWh | – | Push |

Nicht geeignet: BYD-Integration (alle ~10 min) [V]. Strompreis: berechnet der EV Tracker
selbst, wenn `kosten: null` gesendet wird [V]. Kia-Integration kennt den EV3 noch nicht.

HA meldet über `subscribe_entities` nur `state_changed`, nicht `state_reported` [V, HA-Core
`websocket_api/messages.py`]. Konstante Werte kommen also nicht erneut → Lebenszeichen je Gerät.

## go-eCharger (FW 59.4, Keys aus `API_KEYS_FIRMWARE/apikeys_Firmware_59.4_sorted.md`)

- `ids` (W): `{"pGrid","pPv","pAkku"}`; pGrid < 0 = Einspeisung, pAkku < 0 = Akku lädt [V]
- Muss alle 5 s kommen, bis 10 s rücklesbar (go-e) bzw. nach 5 s verworfen (marq24) [V] → Takt 2–3 s
- `lmo`: 3 Default, 4 Eco/Awattar, 5 NextTrip [V] · `fup` PV-Überschuss [V] · `frc` 0/1/2 [V]
- `ama` Obergrenze, `amp` angeforderter Strom [V] · `pnp` Phasenanzahl [V]
- `psm`: 1 = 1-phasig, 2 = 3-phasig (evcc `charger/go-e.go`) [V]; 0 = Automatik [A]
- `modelStatus` 0–39 als Grund für Laden/Nicht-Laden [V]

## marq24 goecharger_api2 (v2026.9.5, WebSocket)

- Service `goecharger_api2.set_pv_data(pgrid, ppv, pakku)` schreibt `ids` [V]; keine eigene
  automatische PV-Weiterleitung [V]; keine Automation ruft den Service auf [V]
- **„[16A limited]“**: `limit_to16a` wird gesetzt bei `var==11`, Option `limit_to_11kw` oder
  `cll.cableCurrentLimit ≤ 16`. Bei Typ-2-Dose ohne Kabel fehlt der Wert → `-1` → limitiert.
  15 s nach jedem Start schreibt der „16A checker“ alle Strom-Entities mit max=16 (u. a. `ama`)
  auf 16 A herunter. `number.goe_*_ama` erlaubt in HA nur bis 16 → `ama=24` nur über die go-e-App [V]
- Discussion #126 („lädt nach Pause nicht wieder an“): Ursache war ein 1-h-Backoff nach
  Kommunikationsfehler im HTTP-Modus, behoben ab v2026.8.0 + WebSocket [V]. Mehrere Clients
  auf derselben Schnittstelle stören die go-e-Firmware (Aussage marq24).

## Normen

- VDE-AR-N 4100: Schieflast höchstens 4,6 kVA je Außenleiter ≈ 20 A bei 230 V [V]

## Entscheidungen (Daniel, 2026-10-03)

1. Netz direkt aus `M1 AC Power` · 2. evcc läuft bis M4, vor M5 aus · 3. Typ-2-Dose, 22-kW-Gerät,
   Grenze 24 A · 4. Preis rechnet der EV Tracker · 5. EV3 noch nicht geliefert → manueller SoC ·
   6. Repo `HasenbeinMH/ev-pv-laden` · 7. go-e-Zähler führt, Trapez als Plausibilität ·
   8. Schreiben über marq24-Service/Entities · Akku zählt beim Tracker als PV
