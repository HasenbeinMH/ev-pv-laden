import json
import os

import datenbank as db


def test_migration_idempotent(tmp_path):
    pfad = str(tmp_path / "t.db")
    assert db.initialisieren(pfad) == len(db.MIGRATIONEN)
    assert db.initialisieren(pfad) == len(db.MIGRATIONEN)   # zweiter Start: nichts doppelt


def test_ereignisse(tmp_path):
    pfad = str(tmp_path / "t.db")
    db.initialisieren(pfad)
    db.ereignis("info", "test", "eins", pfad)
    db.ereignis("warnung", "test", "zwei", pfad)
    e = db.ereignisse(10, pfad)
    assert [x["text"] for x in e] == ["zwei", "eins"]


def test_app_startet_ohne_ha_und_zeigt_status():
    """Ohne SUPERVISOR_TOKEN/HA_URL: App laeuft, meldet fehlende Verbindung, schreibt nichts."""
    from fastapi.testclient import TestClient
    data = os.environ["EVPV_DATA"]
    with open(os.path.join(data, "options.json"), "w", encoding="utf-8") as fh:
        json.dump({"goe_seriennummer": "325656"}, fh)
    from webapp.app import app
    with TestClient(app) as c:
        s = c.get("/api/status").json()
        assert s["konfig_ok"] is True
        assert s["trockenlauf"] is True
        assert s["ha"]["verbunden"] is False
        assert "Verbindungsdaten" in s["ha"]["fehler"]
        assert any(z["name"] == "netz_w" for z in s["signale"])
        assert c.get("/").status_code == 200
        assert c.get("/static/style.css").status_code == 200
        quellen = {e["quelle"] for e in c.get("/api/ereignisse").json()["ereignisse"]}
        assert "start" in quellen
        r = c.get("/api/regelung").json()
        assert r["treiber"] == "keiner (Trockenlauf)" and r["modus"] == "nur_pv"
        assert c.post("/api/parameter", json={"stopp_w": 5000}).status_code == 422
        assert c.post("/api/parameter", json={"modus": "min_pv"}).json()["parameter"]["modus"] == "min_pv"
        assert c.get("/api/regelung").json()["modus"] == "min_pv"
        assert "daten" in c.get("/api/verlauf").json()
