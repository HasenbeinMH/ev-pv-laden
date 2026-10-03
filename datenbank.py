# -*- coding: utf-8 -*-
"""
SQLite unter /data. Kurze Zugriffe, daher synchron (sqlite3) mit eigener Verbindung je
Aufruf – kein geteilter Zustand zwischen Regelschleife und Web-Anfragen.

Schema-Versionierung wie beim EV Tracker: MIGRATIONEN wird der Reihe nach angewendet,
die erreichte Version steht in meta.schema_version.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from konfig import DATA_DIR

DB_DATEI = os.environ.get("EVPV_DB", os.path.join(DATA_DIR, "ev_pv_laden.db"))

MIGRATIONEN = [
    # 1: Grundgeruest
    """
    CREATE TABLE meta (schluessel TEXT PRIMARY KEY, wert TEXT);
    -- Fortlaufende Energiezaehler (kWh). Duerfen nie zurueckspringen, siehe zaehler_erhoehen().
    CREATE TABLE zaehler (
        name TEXT PRIMARY KEY,
        kwh REAL NOT NULL DEFAULT 0,
        aktualisiert TEXT
    );
    -- Regelentscheidungen und Ereignisse fuer das Protokoll in der Oberflaeche
    CREATE TABLE ereignisse (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zeit TEXT NOT NULL,
        ebene TEXT NOT NULL,
        quelle TEXT NOT NULL,
        text TEXT NOT NULL
    );
    CREATE INDEX ereignisse_zeit ON ereignisse(zeit);
    -- Zur Laufzeit einstellbare Parameter (Modus, Hysterese ...), als JSON-Text
    CREATE TABLE einstellungen (schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL);
    """,
    # 2: Bilanz je Tag und einzelne Ladevorgaenge
    """
    CREATE TABLE bilanz_tag (
        datum TEXT PRIMARY KEY,           -- lokales Datum YYYY-MM-DD
        pv REAL NOT NULL DEFAULT 0, akku REAL NOT NULL DEFAULT 0, netz REAL NOT NULL DEFAULT 0,
        ohne REAL NOT NULL DEFAULT 0,     -- in netz enthalten: Herkunft unbekannt
        eto REAL NOT NULL DEFAULT 0,      -- Summe der gebuchten Zaehleranstiege
        trapez REAL NOT NULL DEFAULT 0    -- Plausibilitaet: Integral der Leistung
    );
    CREATE TABLE ladevorgaenge (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        start TEXT NOT NULL,              -- lokale Zeit ISO
        ende TEXT,                        -- NULL = laeuft noch
        stand_start TEXT NOT NULL,        -- JSON: Bilanz-Zaehler beim Beginn
        pv REAL, akku REAL, netz REAL, ohne REAL, eto REAL, trapez REAL,
        modus TEXT, grund TEXT,
        gesendet TEXT                     -- Zeitpunkt der Uebergabe an den EV Tracker
    );
    CREATE INDEX ladevorgaenge_start ON ladevorgaenge(start);
    """,
]

ZAEHLER_NAMEN = ("kwh_pv", "kwh_akku", "kwh_netz")


def jetzt() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def verbindung(pfad: str | None = None):
    con = sqlite3.connect(pfad or DB_DATEI, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def schema_version(con) -> int:
    try:
        zeile = con.execute("SELECT wert FROM meta WHERE schluessel='schema_version'").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(zeile["wert"]) if zeile else 0


def initialisieren(pfad: str | None = None) -> int:
    """Legt die Datenbank an bzw. bringt sie auf den neuesten Stand. Gibt die Version zurueck."""
    with verbindung(pfad) as con:
        # WAL: Lesen (Oberflaeche) blockiert nicht das Schreiben (Regelschleife)
        con.execute("PRAGMA journal_mode=WAL")
        version = schema_version(con)
        if version > len(MIGRATIONEN):
            raise RuntimeError(f"Datenbank hat Schema {version}, dieses Add-on kennt nur "
                               f"{len(MIGRATIONEN)} – bitte Add-on aktualisieren")
        for nr in range(version, len(MIGRATIONEN)):
            con.executescript(MIGRATIONEN[nr])
            con.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", (str(nr + 1),))
        return len(MIGRATIONEN)


def ereignis(ebene: str, quelle: str, text: str, pfad: str | None = None) -> None:
    with verbindung(pfad) as con:
        con.execute("INSERT INTO ereignisse (zeit, ebene, quelle, text) VALUES (?,?,?,?)",
                    (jetzt(), ebene, quelle, text))


def einstellung(schluessel: str, standard=None, pfad: str | None = None):
    with verbindung(pfad) as con:
        z = con.execute("SELECT wert FROM einstellungen WHERE schluessel=?", (schluessel,)).fetchone()
    return json.loads(z["wert"]) if z else standard


def einstellung_setzen(schluessel: str, wert, pfad: str | None = None) -> None:
    with verbindung(pfad) as con:
        con.execute("INSERT OR REPLACE INTO einstellungen VALUES (?, ?)", (schluessel, json.dumps(wert)))


# -- Bilanz ---------------------------------------------------------------------------

def bilanz_laden(pfad: str | None = None) -> dict | None:
    """Gespeicherter Bilanz-Zustand. Die Zaehler werden mit der Tabelle zaehler
    abgeglichen (jeweils der groessere Wert) – zwei unabhaengige Stellen, damit ein
    beschaedigter JSON-Zustand die Zaehler nicht zuruecksetzen kann."""
    with verbindung(pfad) as con:
        z = con.execute("SELECT wert FROM einstellungen WHERE schluessel='bilanz_zustand'").fetchone()
        zaehler = {r["name"]: r["kwh"] for r in con.execute("SELECT name, kwh FROM zaehler")}
    zustand = json.loads(z["wert"]) if z else None
    if zustand is None and not zaehler:
        return None
    zustand = zustand or {}
    kwh = zustand.setdefault("kwh", {})
    for q in ("pv", "akku", "netz"):
        kwh[q] = max(float(kwh.get(q, 0.0)), float(zaehler.get(f"kwh_{q}", 0.0)))
    return zustand


def bilanz_speichern(zustand: dict, tag: str | None = None, buchung: dict | None = None,
                     trapez_kwh: float = 0.0, pfad: str | None = None) -> None:
    """Speichert Zustand, Zaehler (nur steigend) und optional die Tagesbuchung –
    alles in einer Transaktion."""
    with verbindung(pfad) as con:
        con.execute("INSERT OR REPLACE INTO einstellungen VALUES ('bilanz_zustand', ?)",
                    (json.dumps(zustand),))
        for q in ("pv", "akku", "netz"):
            con.execute("""INSERT INTO zaehler (name, kwh, aktualisiert) VALUES (?, ?, ?)
                           ON CONFLICT(name) DO UPDATE SET
                             kwh = MAX(kwh, excluded.kwh), aktualisiert = excluded.aktualisiert""",
                        (f"kwh_{q}", zustand["kwh"][q], jetzt()))
        if tag and (buchung or trapez_kwh):
            b = buchung or {}
            con.execute("""INSERT INTO bilanz_tag (datum, pv, akku, netz, ohne, eto, trapez)
                           VALUES (?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(datum) DO UPDATE SET
                             pv = pv + excluded.pv, akku = akku + excluded.akku,
                             netz = netz + excluded.netz, ohne = ohne + excluded.ohne,
                             eto = eto + excluded.eto, trapez = trapez + excluded.trapez""",
                        (tag, b.get("pv", 0.0), b.get("akku", 0.0), b.get("netz", 0.0),
                         b.get("ohne", 0.0), b.get("eto", 0.0), trapez_kwh))


def bilanz_tage(anzahl: int = 31, pfad: str | None = None) -> list[dict]:
    with verbindung(pfad) as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM bilanz_tag ORDER BY datum DESC LIMIT ?", (anzahl,))]


# -- Ladevorgaenge ------------------------------------------------------------------------

def vorgang_anlegen(start: str, stand_start: dict, modus: str, pfad: str | None = None) -> int:
    with verbindung(pfad) as con:
        cur = con.execute("INSERT INTO ladevorgaenge (start, stand_start, modus) VALUES (?, ?, ?)",
                          (start, json.dumps(stand_start), modus))
        return cur.lastrowid


def vorgang_beenden(vid: int, ende: str, energie: dict, grund: str, pfad: str | None = None) -> None:
    with verbindung(pfad) as con:
        con.execute("""UPDATE ladevorgaenge SET ende=?, pv=?, akku=?, netz=?, ohne=?, eto=?,
                       trapez=?, grund=? WHERE id=?""",
                    (ende, energie["pv"], energie["akku"], energie["netz"], energie["ohne"],
                     energie["eto"], energie["trapez"], grund, vid))


def vorgang_offen(pfad: str | None = None) -> dict | None:
    with verbindung(pfad) as con:
        z = con.execute("SELECT * FROM ladevorgaenge WHERE ende IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    if not z:
        return None
    d = dict(z)
    d["stand_start"] = json.loads(d["stand_start"])
    return d


def vorgaenge(anzahl: int = 50, pfad: str | None = None) -> list[dict]:
    with verbindung(pfad) as con:
        return [dict(r) for r in con.execute(
            "SELECT id, start, ende, pv, akku, netz, ohne, eto, trapez, modus, grund, gesendet "
            "FROM ladevorgaenge ORDER BY id DESC LIMIT ?", (anzahl,))]


def ereignisse(anzahl: int = 100, pfad: str | None = None) -> list[dict]:
    with verbindung(pfad) as con:
        zeilen = con.execute("SELECT zeit, ebene, quelle, text FROM ereignisse "
                             "ORDER BY id DESC LIMIT ?", (anzahl,)).fetchall()
    return [dict(z) for z in zeilen]
