# -*- coding: utf-8 -*-
"""
SQLite unter /data. Kurze Zugriffe, daher synchron (sqlite3) mit eigener Verbindung je
Aufruf – kein geteilter Zustand zwischen Regelschleife und Web-Anfragen.

Schema-Versionierung wie beim EV Tracker: MIGRATIONEN wird der Reihe nach angewendet,
die erreichte Version steht in meta.schema_version.
"""
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
]


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


def ereignisse(anzahl: int = 100, pfad: str | None = None) -> list[dict]:
    with verbindung(pfad) as con:
        zeilen = con.execute("SELECT zeit, ebene, quelle, text FROM ereignisse "
                             "ORDER BY id DESC LIMIT ?", (anzahl,)).fetchall()
    return [dict(z) for z in zeilen]
