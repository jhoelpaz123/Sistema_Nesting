import json
import os
import shutil
import logging
from datetime import datetime
from shapely.geometry import Polygon

from validador import validar_molde

# Logger específico para este módulo; los mensajes se propagan al logger raíz de la app
logger = logging.getLogger("nesting.gestor_moldes")

# Rutas base resueltas relativas a la ubicación de este archivo
DIR_MOLDES  = os.path.join(os.path.dirname(__file__), "..", "..", "data", "moldes")
DIR_BACKUP  = os.path.join(os.path.dirname(__file__), "..", "..", "data", "backups")


def _asegurar_dirs():
    # Crea los directorios si no existen; exist_ok evita error si ya están creados
    os.makedirs(DIR_MOLDES, exist_ok=True)
    os.makedirs(DIR_BACKUP, exist_ok=True)


def _ruta_molde(nombre: str) -> str:
    # Construye la ruta completa al archivo JSON de un molde dado su nombre
    return os.path.join(DIR_MOLDES, f"{nombre}.json")


def _respaldar(nombre: str):
    """Crea copia de respaldo antes de modificar o eliminar."""
    ruta = _ruta_molde(nombre)
    if os.path.exists(ruta):
        # Timestamp en el nombre del backup para evitar colisiones entre versiones
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = os.path.join(DIR_BACKUP, f"{nombre}_{ts}.json")
        # shutil.copy2 preserva metadatos del archivo original (fechas, permisos)
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

    # Sanear el nombre: eliminar espacios al inicio/fin y verificar que no esté vacío
    nombre = nombre.strip()
    if not nombre:
        return False, "El nombre del molde no puede estar vacío."

    # Evitar duplicados: un molde con el mismo nombre ya existe en disco
    if os.path.exists(_ruta_molde(nombre)):
        return False, f"Ya existe un molde con el nombre '{nombre}'."

    # Delegar la validación geométrica al módulo validador (mínimo de puntos, self-intersections, etc.)
    valido, msg = validar_molde(coordenadas)
    if not valido:
        return False, msg

    # Calcular el área real del polígono usando Shapely para persistirla junto al molde
    poligono = Polygon(coordenadas)
    datos = {
        "nombre":       nombre,
        "descripcion":  descripcion,
        # Garantizar que la cantidad sea al menos 1 aunque se pase un valor menor
        "cantidad":     max(1, int(cantidad)),
        # Convertir cada punto a lista para que sea serializable en JSON
        "coordenadas":  [list(pt) for pt in coordenadas],
        "area_cm2":     round(poligono.area, 4),
        # Guardar ambas fechas por separado; fecha_modificacion se actualiza en cada edición
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
    # Iterar en orden alfabético sobre los archivos del directorio de moldes
    for archivo in sorted(os.listdir(DIR_MOLDES)):
        if archivo.endswith(".json"):
            ruta = os.path.join(DIR_MOLDES, archivo)
            try:
                with open(ruta, encoding="utf-8") as f:
                    datos = json.load(f)
                moldes.append(datos)
            except (json.JSONDecodeError, OSError) as exc:
                # Archivo corrupto o sin permisos: se registra advertencia y se omite
                logger.warning("No se pudo leer '%s': %s", archivo, exc)
    return moldes

# ─────────────────────────────────────────────────────────────────
#  OBTENER
# ─────────────────────────────────────────────────────────────────
def obtener_molde(nombre: str) -> dict | None:
    """Retorna los datos de un molde por nombre, o None si no existe."""
    ruta = _ruta_molde(nombre)
    # Verificar existencia antes de intentar abrir para distinguir "no existe" de error de lectura
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
    # Reutilizar obtener_molde para centralizar la lectura y el manejo de errores
    datos = obtener_molde(nombre)
    if datos is None:
        return False, f"No se encontró el molde '{nombre}'."

    # Actualización parcial: solo se modifica lo que el llamador envió explícitamente
    if nuevas_coordenadas is not None:
        # Re-validar geometría si se cambian las coordenadas
        valido, msg = validar_molde(nuevas_coordenadas)
        if not valido:
            return False, msg
        poligono = Polygon(nuevas_coordenadas)
        datos["coordenadas"] = [list(pt) for pt in nuevas_coordenadas]
        # Recalcular el área porque la forma del polígono cambió
        datos["area_cm2"] = round(poligono.area, 4)

    if nueva_cantidad is not None:
        # Forzar mínimo de 1 pieza aunque el usuario pase 0 o negativo
        datos["cantidad"] = max(1, int(nueva_cantidad))

    if nueva_descripcion is not None:
        datos["descripcion"] = nueva_descripcion

    # Actualizar la marca de tiempo de modificación antes de persistir
    datos["fecha_modificacion"] = datetime.now().isoformat()

    # Respaldar el estado actual en disco ANTES de sobreescribirlo
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

    # Guardar copia de seguridad antes de la eliminación; permite recuperación manual si es necesario
    _respaldar(nombre)
    try:
        os.remove(ruta)
        logger.info("Molde '%s' eliminado.", nombre)
        return True, f"Molde '{nombre}' eliminado correctamente."
    except OSError as exc:
        logger.error("Error al eliminar molde '%s': %s", nombre, exc)
        return False, f"Error al eliminar: {exc}"