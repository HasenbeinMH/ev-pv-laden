# -*- coding: utf-8 -*-
"""
Fuehrt die stuendliche HA-Langzeitstatistik (Exporte als JSON) zu einer Zeitreihe
zusammen und rekonstruiert die PV-Erzeugung.

DC-Zwischenkreis des SolarEdge-Hybrid-Wechselrichters:
    PV = DC-Leistung (Eingang Wechselrichter) + Akku-Ladung - Akku-Entladung
(geprueft am 03.10.2026 gegen sensor.pv_erzeugung_kwh: Abweichung < 5 % je Stunde)

    python dev/modell/daten_zusammenfuehren.py <ordner-mit-json> <ziel.csv>
"""
import csv
import glob
import json
import os
import sys
from datetime import datetime, timezone

DC, LADEN, ENTLADEN = ("sensor.se_modbus_daten_dc_power", "sensor.se_modbus_daten_battery1_charged",
                       "sensor.se_modbus_daten_battery1_discharged")


def lesen(ordner: str) -> dict:
    werte: dict[int, dict] = {}
    dateien = 0
    for pfad in glob.glob(os.path.join(ordner, "*.txt")):
        text = open(pfad, encoding="utf-8").read()
        if DC not in text or '"period":"hour"' not in text.replace(" ", ""):
            continue
        start = text.find("{")
        try:
            daten = json.loads(text[start:])
        except json.JSONDecodeError:
            continue
        dateien += 1
        for ent in daten.get("data", {}).get("entities", []):
            eid = ent["entity_id"]
            for z in ent.get("statistics", []):
                zeile = werte.setdefault(z["start"] // 1000, {})
                if eid == DC and z.get("mean") is not None:
                    zeile["dc_w"] = z["mean"]
                elif eid == LADEN and z.get("change") is not None:
                    zeile["laden_kwh"] = z["change"]
                elif eid == ENTLADEN and z.get("change") is not None:
                    zeile["entladen_kwh"] = z["change"]
    print(f"{dateien} Dateien gelesen, {len(werte)} Stunden")
    return werte


def main():
    ordner, ziel = sys.argv[1], sys.argv[2]
    werte = lesen(ordner)
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    ohne_dc = 0
    with open(ziel, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["zeit_utc", "pv_kwh", "dc_kwh", "laden_kwh", "entladen_kwh"])
        for ts in sorted(werte):
            z = werte[ts]
            if "dc_w" not in z:
                ohne_dc += 1
                continue
            dc = z["dc_w"] / 1000
            laden, entladen = z.get("laden_kwh", 0.0), z.get("entladen_kwh", 0.0)
            pv = max(dc + laden - entladen, 0.0)
            w.writerow([datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        round(pv, 4), round(dc, 4), round(laden, 4), round(entladen, 4)])
    print(f"geschrieben: {ziel} ({len(werte) - ohne_dc} Stunden, {ohne_dc} ohne DC-Wert verworfen)")


if __name__ == "__main__":
    main()
