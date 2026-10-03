# -*- coding: utf-8 -*-
"""
Logging: auf stdout (erscheint im Add-on-Protokoll von HA) und in eine rotierende Datei
unter /data, damit die Oberflaeche die letzten Zeilen auch nach einem Neustart zeigen kann.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
LOG_NAME = "ev_pv_laden.log"


def einrichten(level: str = "info", data_dir: str | None = None) -> None:
    wurzel = logging.getLogger()
    wurzel.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Bei erneutem Aufruf (Konfig neu geladen) keine doppelten Handler
    for h in list(wurzel.handlers):
        wurzel.removeHandler(h)
    fmt = logging.Formatter(FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    konsole = logging.StreamHandler()
    konsole.setFormatter(fmt)
    wurzel.addHandler(konsole)

    if data_dir and os.path.isdir(data_dir):
        datei = RotatingFileHandler(os.path.join(data_dir, LOG_NAME), maxBytes=1_000_000,
                                    backupCount=3, encoding="utf-8")
        datei.setFormatter(fmt)
        wurzel.addHandler(datei)

    # Zugriffsprotokoll von uvicorn wuerde bei Live-Ansicht (Abfrage im Sekundentakt) fluten
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def letzte_zeilen(data_dir: str, anzahl: int = 200) -> list[str]:
    pfad = os.path.join(data_dir, LOG_NAME)
    try:
        with open(pfad, encoding="utf-8", errors="replace") as fh:
            return [z.rstrip("\n") for z in fh.readlines()[-anzahl:]]
    except OSError:
        return []
