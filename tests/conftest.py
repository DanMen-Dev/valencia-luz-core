import os
import sys
import tempfile

# main.py crea la base al importarse: en las pruebas, siempre en una carpeta temporal
os.environ.setdefault("VL_DB_PATH", os.path.join(tempfile.mkdtemp(), "vl_pruebas.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
