
import logging
from shapely.geometry import Polygon
from shapely.validation import explain_validity

logger = logging.getLogger("nesting.validador")


def validar_molde(coordenadas: list[tuple[float, float]]) -> tuple[bool, str]:
    """
    Valida una lista de coordenadas (x, y) como polígono textil.

    Parámetros
    ----------
    coordenadas : list[tuple[float, float]]
        Lista de al menos 3 puntos (x, y).

    Retorna
    -------
    (valido: bool, mensaje: str)
    """
    try:
        if not isinstance(coordenadas, (list, tuple)) or len(coordenadas) < 3:
            return False, "El molde debe tener al menos 3 vértices."

        for i, pt in enumerate(coordenadas):
            if len(pt) != 2:
                return False, f"Vértice {i+1}: se esperan exactamente 2 coordenadas (x, y)."
            x, y = pt
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                return False, f"Vértice {i+1}: las coordenadas deben ser numéricas."
            if x < 0 or y < 0:
                return False, f"Vértice {i+1}: las coordenadas no pueden ser negativas."

        poligono = Polygon(coordenadas)

        if poligono.area == 0:
            return False, "El molde tiene área cero (vértices colineales o duplicados)."

        if not poligono.is_valid:
            razon = explain_validity(poligono)
            return False, f"Polígono inválido: {razon}"

        if poligono.is_empty:
            return False, "El polígono resultante está vacío."

        logger.debug("Molde válido – vértices: %d, área: %.4f", len(coordenadas), poligono.area)
        return True, "Molde válido."

    except Exception as exc:
        logger.exception("Error inesperado en validación de molde")
        return False, f"Error de validación: {exc}"


def validar_parametros_tela(ancho: float, largo: float, margen: float = 0.0) -> tuple[bool, str]:
    """
    Valida los parámetros de la superficie de tela.

    Parámetros
    ----------
    ancho  : float  – Ancho de la tela en centímetros.
    largo  : float  – Largo de la tela en centímetros.
    margen : float  – Margen de seguridad entre piezas (≥ 0).

    Retorna
    -------
    (valido: bool, mensaje: str)
    """
    try:
        if not isinstance(ancho, (int, float)) or not isinstance(largo, (int, float)):
            return False, "El ancho y el largo deben ser valores numéricos."

        if ancho <= 0 or largo <= 0:
            return False, "El ancho y el largo deben ser mayores que cero."

        if ancho < 10 or largo < 10:
            return False, "Advertencia: superficie de tela muy pequeña (mínimo recomendado: 10 × 10 cm)."

        if not isinstance(margen, (int, float)) or margen < 0:
            return False, "El margen de seguridad no puede ser negativo."

        if margen >= ancho / 2 or margen >= largo / 2:
            return False, "El margen de seguridad es mayor que la mitad de la superficie de tela."

        return True, "Parámetros de tela válidos."

    except Exception as exc:
        logger.exception("Error inesperado en validación de parámetros de tela")
        return False, f"Error de validación: {exc}"