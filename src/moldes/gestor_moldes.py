
import json
import os
import shutil
import logging
from datetime import datetime
from shapely.geometry import Polygon

from validador import validar_molde

logger = logging.getLogger("nesting.gestor_moldes")

DIR_MOLDES  = os.path.join(os.path.dirname(__file__), "..", "..", "data", "moldes")
DIR_BACKUP  = os.path.join(os.path.dirname(__file__), "..", "..", "data", "backups")


def _asegurar_dirs():
    os.makedirs(DIR_MOLDES, exist_ok=True)
    os.makedirs(DIR_BACKUP, exist_ok=True)


def _ruta_molde(nombre: str) -> str:
    return os.path.join(DIR_MOLDES, f"{nombre}.json")


def _respaldar(nombre: str):
    """Crea copia de respaldo antes de modificar o eliminar."""
    ruta = _ruta_molde(nombre)
    if os.path.exists(ruta):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = os.path.join(DIR_BACKUP, f"{nombre}_{ts}.json")
        shutil.copy2(ruta, destino)
        logger.debug("Respaldo creado: %s", destino)


# ─────────────────────────────────────────────────────────────────
#  REGISTRAR
# ─────────────────────────────────────────────────────────────────
def registrar_molde(nombre: str, coordenadas: list, cantidad: int = 1,
                    descripcion: str = "") -> tuple[bool, str]:
    """
    Registra un nuevo molde. Valida geometría antes de guardar.

    Parámetros
    ----------
    nombre      : Identificador único del molde (ej. "manga_izquierda").
    coordenadas : Lista de tuplas (x, y) en centímetros.
    cantidad    : Número de piezas de este molde por prenda.
    descripcion : Descripción opcional (ej. "Manga izquierda caporal").

    Retorna
    -------
    (exito: bool, mensaje: str)
    """
    _asegurar_dirs()

    nombre = nombre.strip()
    if not nombre:
        return False, "El nombre del molde no puede estar vacío."

    if os.path.exists(_ruta_molde(nombre)):
        return False, f"Ya existe un molde con el nombre '{nombre}'."

    valido, msg = validar_molde(coordenadas)
    if not valido:
        return False, msg

    poligono = Polygon(coordenadas)
    datos = {
        "nombre":       nombre,
        "descripcion":  descripcion,
        "cantidad":     max(1, int(cantidad)),
        "coordenadas":  [list(pt) for pt in coordenadas],
        "area_cm2":     round(poligono.area, 4),
        "fecha_creacion": datetime.now().isoformat(),
        "fecha_modificacion": datetime.now().isoformat(),
    }

    try:
        with open(_ruta_molde(nombre), "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        logger.info("Molde '%s' registrado. Área: %.4f cm²", nombre, poligono.area)
        return True, f"Molde '{nombre}' registrado correctamente."
    except OSError as exc:
        logger.error("Error al guardar molde '%s': %s", nombre, exc)
        return False, f"Error al guardar: {exc}"


# ─────────────────────────────────────────────────────────────────
#  LISTAR
# ─────────────────────────────────────────────────────────────────
def listar_moldes() -> list[dict]:
    """Retorna lista de todos los moldes registrados."""
    _asegurar_dirs()
    moldes = []
    for archivo in sorted(os.listdir(DIR_MOLDES)):
        if archivo.endswith(".json"):
            ruta = os.path.join(DIR_MOLDES, archivo)
            try:
                with open(ruta, encoding="utf-8") as f:
                    datos = json.load(f)
                moldes.append(datos)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("No se pudo leer '%s': %s", archivo, exc)
    return moldes


# ─────────────────────────────────────────────────────────────────
#  OBTENER
# ─────────────────────────────────────────────────────────────────
def obtener_molde(nombre: str) -> dict | None:
    """Retorna los datos de un molde por nombre, o None si no existe."""
    ruta = _ruta_molde(nombre)
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Error al leer molde '%s': %s", nombre, exc)
        return None


# ─────────────────────────────────────────────────────────────────
#  EDITAR
# ─────────────────────────────────────────────────────────────────
def editar_molde(nombre: str, nuevas_coordenadas: list | None = None,
                 nueva_cantidad: int | None = None,
                 nueva_descripcion: str | None = None) -> tuple[bool, str]:
    """
    Modifica un molde existente. Respalda antes de editar.
    Solo actualiza los campos que no sean None.
    """
    datos = obtener_molde(nombre)
    if datos is None:
        return False, f"No se encontró el molde '{nombre}'."

    if nuevas_coordenadas is not None:
        valido, msg = validar_molde(nuevas_coordenadas)
        if not valido:
            return False, msg
        poligono = Polygon(nuevas_coordenadas)
        datos["coordenadas"] = [list(pt) for pt in nuevas_coordenadas]
        datos["area_cm2"] = round(poligono.area, 4)

    if nueva_cantidad is not None:
        datos["cantidad"] = max(1, int(nueva_cantidad))

    if nueva_descripcion is not None:
        datos["descripcion"] = nueva_descripcion

    datos["fecha_modificacion"] = datetime.now().isoformat()

    _respaldar(nombre)
    try:
        with open(_ruta_molde(nombre), "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        logger.info("Molde '%s' actualizado.", nombre)
        return True, f"Molde '{nombre}' actualizado correctamente."
    except OSError as exc:
        logger.error("Error al guardar edición de '%s': %s", nombre, exc)
        return False, f"Error al guardar: {exc}"


# ─────────────────────────────────────────────────────────────────
#  ELIMINAR
# ─────────────────────────────────────────────────────────────────
def eliminar_molde(nombre: str) -> tuple[bool, str]:
    """Elimina un molde. Respalda antes de eliminar."""
    ruta = _ruta_molde(nombre)
    if not os.path.exists(ruta):
        return False, f"No se encontró el molde '{nombre}'."

    _respaldar(nombre)
    try:
        os.remove(ruta)
        logger.info("Molde '%s' eliminado.", nombre)
        return True, f"Molde '{nombre}' eliminado correctamente."
    except OSError as exc:
        logger.error("Error al eliminar molde '%s': %s", nombre, exc)
        return False, f"Error al eliminar: {exc}"