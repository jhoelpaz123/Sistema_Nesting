"""
=====================================================================
  src/logger_config.py
  Configuración del sistema de logging del proyecto.
  Escribe en logs/nesting.log y también en consola.
  Cumple: trazabilidad de operaciones (ISO/IEC 27001:2022)
=====================================================================
"""

import logging
import logging.handlers
import os
from datetime import datetime

# Directorio donde se guardarán los archivos de log
DIR_LOGS = os.path.join(os.path.dirname(__file__), "..", "..", "logs")


def configurar_logging(nivel: str = "INFO") -> None:
    # Crea el directorio de logs si no existe
    os.makedirs(DIR_LOGS, exist_ok=True)

    # Convierte el nivel de texto a constante numérica de logging
    nivel_num = getattr(logging, nivel.upper(), logging.INFO)

    # Formato estándar: fecha | nivel | módulo | mensaje
    formato = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler rotativo: 1 MB por archivo, máx. 5 archivos de respaldo
    ruta_log = os.path.join(DIR_LOGS, "nesting.log")
    file_handler = logging.handlers.RotatingFileHandler(
        ruta_log, maxBytes=1_048_576, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formato)
    file_handler.setLevel(nivel_num)

    # Handler consola: solo muestra warnings y errores
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formato)
    console_handler.setLevel(logging.WARNING)

    # Obtiene el logger raíz y establece el nivel mínimo global
    root_logger = logging.getLogger()
    root_logger.setLevel(nivel_num)

    # Evita duplicar handlers si la función se llama más de una vez
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

    # Registro inicial para confirmar que el sistema arrancó correctamente
    logging.getLogger("nesting").info(
        "Sistema de logging iniciado. Log: %s", ruta_log
    )