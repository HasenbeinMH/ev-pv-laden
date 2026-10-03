import os
import sys
import tempfile

# Projektwurzel importierbar machen und /data auf ein Temp-Verzeichnis umbiegen,
# bevor irgendein Modul DATA_DIR ausliest
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)
_TMP = tempfile.mkdtemp(prefix="evpv_test_")
os.environ["EVPV_DATA"] = _TMP
os.environ.pop("SUPERVISOR_TOKEN", None)
os.environ.pop("HA_URL", None)
os.environ.pop("HA_TOKEN", None)
