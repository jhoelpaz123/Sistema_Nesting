"""
=====================================================================
  Sistema de Optimización de Corte (Nesting) para Piezas Textiles
=====================================================================
"""

import sys
import os

# Agrega src/ y todos sus subdirectorios al path
_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.insert(0, _src)
for _sub in ("config", "validacion", "moldes", "nesting", "metricas", "exportacion", "utils", "interfaz"):
    sys.path.insert(0, os.path.join(_src, _sub))

from interfaz import AppNesting

if __name__ == "__main__":
    app = AppNesting()
    app.ejecutar()
