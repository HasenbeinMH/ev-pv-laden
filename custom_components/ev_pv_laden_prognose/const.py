"""Konstanten der Integration EV PV-Laden Prognose."""
from datetime import timedelta

DOMAIN = "ev_pv_laden_prognose"
CONF_URL = "url"
# Interne Adresse des Add-ons im HA-Netz (Hostname wie im Supervisor angezeigt, Port 8099)
DEFAULT_URL = "http://b5a2b766-ev-pv-laden:8099"
PFAD = "/api/prognose/stunden"
INTERVALL = timedelta(minutes=15)
