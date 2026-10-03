# -*- coding: utf-8 -*-
"""
Aufgezeichnete Verlaeufe aus der HA-Historie als CSV exportieren – fuer die Tests der
Strategie (tests/test_strategie.py spielt alle tests/daten/*.csv nach).

    set HA_URL=http://homeassistant.local:8123
    set HA_TOKEN=<Long-Lived Access Token>
    python dev/export_ha.py 2026-10-01 10:00 16:00

Entity-IDs und Vorzeichen kommen aus dev/data/options.json (wie im Add-on). Die Werte
werden auf ein 1-s-Raster gebracht (letzter Wert gilt weiter) und in die interne
Konvention umgerechnet: netz_w Bezug +, akku_w Entladung +.

Der Token wird nur fuer die Abfrage benutzt und nirgends gespeichert.
"""
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from bisect import bisect_right
from datetime import datetime, timedelta, timezone

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)


def historie(url, token, entity_ids, start, ende):
    pfad = "/api/history/period/" + urllib.parse.quote(start.isoformat())
    abfrage = urllib.parse.urlencode({
        "filter_entity_id": ",".join(entity_ids), "end_time": ende.isoformat(),
        "minimal_response": "", "significant_changes_only": "0"})
    req = urllib.request.Request(url.rstrip("/") + pfad + "?" + abfrage,
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        daten = json.load(r)
    ergebnis = {}
    for liste in daten:
        if not liste:
            continue
        eid = liste[0]["entity_id"]
        punkte = []
        for z in liste:
            try:
                wert = float(z["state"])
            except (TypeError, ValueError):
                continue
            zeit = datetime.fromisoformat(z.get("last_changed") or z["last_updated"])
            punkte.append((zeit.timestamp(), wert))
        ergebnis[eid] = punkte
    return ergebnis


def raster(punkte, start_ts, sekunden):
    """Halteglied 0. Ordnung auf 1-s-Raster; vor dem ersten Wert: None."""
    zeiten = [p[0] for p in punkte]
    werte = []
    for i in range(sekunden):
        j = bisect_right(zeiten, start_ts + i) - 1
        werte.append(punkte[j][1] if j >= 0 else None)
    return werte


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    url, token = os.environ.get("HA_URL"), os.environ.get("HA_TOKEN")
    if not url or not token:
        sys.exit("HA_URL und HA_TOKEN setzen (siehe oben)")
    with open(os.path.join(HIER, "data", "options.json"), encoding="utf-8") as fh:
        opt = json.load(fh)
    lokal = datetime.now().astimezone().tzinfo
    start = datetime.fromisoformat(f"{sys.argv[1]}T{sys.argv[2]}").replace(tzinfo=lokal)
    ende = datetime.fromisoformat(f"{sys.argv[1]}T{sys.argv[3]}").replace(tzinfo=lokal)
    if ende <= start:
        sys.exit("Ende muss nach dem Start liegen")
    g = f"goe_{opt['goe_seriennummer']}"
    spalten = {
        "netz_w": (opt["sensor_netz"], -1 if opt.get("sensor_netz_invertieren") else 1),
        "akku_w": (opt.get("sensor_akku_leistung"), -1 if opt.get("sensor_akku_leistung_invertieren") else 1),
        "akku_soc": (opt.get("sensor_akku_soc"), 1),
        "auto_w": (f"sensor.{g}_nrg_11", 1),
    }
    entities = [e for e, _ in spalten.values() if e]
    # Etwas Vorlauf, damit am Start schon ein Wert vorliegt
    daten = historie(url, token, entities, start - timedelta(minutes=30), ende)
    sekunden = int((ende - start).total_seconds())
    reihen = {}
    for name, (eid, faktor) in spalten.items():
        werte = raster(daten.get(eid, []), start.timestamp(), sekunden) if eid else [0.0] * sekunden
        reihen[name] = [None if w is None else w * faktor for w in werte]
        fehlend = sum(w is None for w in reihen[name])
        print(f"{name:9s} {eid or '-':55s} {len(daten.get(eid, []))} Werte, {fehlend} s ohne Wert")

    ziel = os.path.join(WURZEL, "tests", "daten")
    os.makedirs(ziel, exist_ok=True)
    datei = os.path.join(ziel, f"{start:%Y-%m-%d_%H%M}-{ende:%H%M}.csv")
    with open(datei, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["zeit", *spalten])
        for i in range(sekunden):
            zeile = [reihen[n][i] for n in spalten]
            if zeile[0] is None:
                continue
            w.writerow([(start + timedelta(seconds=i)).astimezone(timezone.utc).isoformat(timespec="seconds"),
                        *("" if v is None else round(v, 1) for v in zeile)])
    print("geschrieben:", datei)


if __name__ == "__main__":
    main()
