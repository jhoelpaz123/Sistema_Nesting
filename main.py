"""
=====================================================================
Sistema de Optimización de Corte (Nesting) para Piezas Textiles
=====================================================================

Archivo principal de ejecución del sistema.

Responsabilidades:
- Configurar las rutas necesarias para importar los módulos.
- Inicializar la aplicación principal.
- Ejecutar la interfaz del sistema.
"""

import os
import sys

# ------------------------------------------------------------------
# Configuración de rutas
# ------------------------------------------------------------------

# Ruta absoluta al directorio 'src'
SRC_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "src"
)

# Agregar la carpeta principal al PATH
sys.path.insert(0, SRC_PATH)

# Subdirectorios utilizados por el proyecto
SUBDIRECTORIOS = (
    "config",
    "validacion",
    "moldes",
    "nesting",
    "metricas",
    "exportacion",
    "utils",
    "interfaz",
)

# Agregar cada subdirectorio al PATH
for carpeta in SUBDIRECTORIOS:
    sys.path.insert(0, os.path.join(SRC_PATH, carpeta))

# ------------------------------------------------------------------
# Importación de la aplicación principal
# ------------------------------------------------------------------

from interfaz import AppNesting


# ------------------------------------------------------------------
# Punto de entrada del programa
# ------------------------------------------------------------------

if __name__ == "__main__":
    app = AppNesting()
    app.ejecutar()