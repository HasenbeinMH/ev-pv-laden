# -*- coding: utf-8 -*-
"""
Lokal starten (Entwicklung, ohne Supervisor):
    python dev/start.py
Daten liegen in dev/data (options.json, Datenbank, Log – nicht im Repo).
Mit HA verbinden: vorher HA_URL (z.B. http://homeassistant.local:8123) und HA_TOKEN
(Long-Lived Access Token) als Umgebungsvariablen setzen. Ohne Token laeuft die
Oberflaeche trotzdem und meldet "getrennt".

    python dev/start.py --simulation
startet mit dem Anlagenmodell (Sonne, Wolken, Akku, Auto) statt Home Assistant.
"""
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("EVPV_DATA", os.path.join(HIER, "data"))
sys.path.insert(0, os.path.dirname(HIER))
if "--simulation" in sys.argv:
    os.environ["EVPV_SIMULATION"] = "1"

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("webapp.app:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8099")))
