

import logging
import math
import time
from typing import Iterator

import numpy as np
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.affinity import translate, rotate as shapely_rotate

logger = logging.getLogger("nesting.motor")

# Paso de rotación por defecto (grados). Menor valor = mejor calidad pero más lento.
PASO_ROTACION_DEFAULT = 15   # 0°,15°,30°,…,345°
MARGEN_DEFAULT        = 0.5  # cm – separación mínima entre piezas


def _construir_poligono(coordenadas: list) -> Polygon:
    return Polygon([(float(x), float(y)) for x, y in coordenadas])


def _rotaciones(angulo_paso: int) -> list[int]:
    """Genera lista de ángulos de rotación según paso indicado."""
    if angulo_paso <= 0:
        return [0]
    return list(range(0, 360, angulo_paso))


def _expandir_con_margen(pieza: Polygon, margen: float) -> Polygon:
    """Expande el polígono con el margen de seguridad (buffer)."""
    if margen <= 0:
        return pieza
    return pieza.buffer(margen / 2, join_style=2)   # join_style=2 → bisel (miter)


def _posiciones_candidatas(
    ancho_tela: float,
    alto_tela: float,
    pieza: Polygon,
    paso_grid: float = 2.0
) -> Iterator[tuple[float, float]]:
    """
    Genera posiciones candidatas en orden Bottom-Left (y creciente, x creciente).
    El paso_grid determina la resolución de búsqueda (cm).
    """
    minx, miny, maxx, maxy = pieza.bounds
    w = maxx - minx
    h = maxy - miny

    y = 0.0
    while y + h <= alto_tela + 1e-6:
        x = 0.0
        while x + w <= ancho_tela + 1e-6:
            yield (x, y)
            x += paso_grid
        y += paso_grid


def colocar_pieza(
    pieza_base: Polygon,
    colocadas: list[Polygon],
    ancho_tela: float,
    alto_tela: float,
    margen: float,
    angulos: list[int],
    paso_grid: float = 2.0,
) -> tuple[Polygon | None, float, float, float]:
    """
    Intenta colocar una pieza en la primera posición Bottom-Left válida,
    probando todos los ángulos de rotación indicados.

    Retorna
    -------
    (pieza_colocada, offset_x, offset_y, angulo)
    Si no cabe, retorna (None, 0, 0, 0).
    """
    union_colocadas = None
    if colocadas:
        from shapely.ops import unary_union
        union_colocadas = unary_union(colocadas)

    superficie = box(0, 0, ancho_tela, alto_tela)

    for angulo in angulos:
        pieza_rot = shapely_rotate(pieza_base, angulo, origin="centroid", use_radians=False)
        minx, miny, _, _ = pieza_rot.bounds
        # Normaliza a origen (0,0)
        pieza_rot = translate(pieza_rot, -minx, -miny)

        pieza_con_margen = _expandir_con_margen(pieza_rot, margen)

        for (cx, cy) in _posiciones_candidatas(ancho_tela, alto_tela, pieza_con_margen, paso_grid):
            candidata     = translate(pieza_rot, cx, cy)
            cand_margen   = translate(pieza_con_margen, cx, cy)

            # ¿Cabe dentro de la tela?
            if not superficie.contains(candidata):
                continue

            # ¿Se solapa con piezas ya colocadas (incluyendo margen)?
            if union_colocadas is not None:
                if cand_margen.intersects(union_colocadas):
                    continue

            logger.debug("Pieza colocada en (%.1f, %.1f) ángulo %d°", cx, cy, angulo)
            return candidata, cx, cy, angulo

    return None, 0.0, 0.0, 0.0


# ─────────────────────────────────────────────────────────────────
#  FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────────────────────────
def ejecutar_nesting(
    moldes: list[dict],
    ancho_tela: float,
    largo_tela: float,
    margen: float = MARGEN_DEFAULT,
    angulo_paso: int = PASO_ROTACION_DEFAULT,
    paso_grid: float = 2.0,
) -> dict:
    """
    Ejecuta el algoritmo heurístico Bottom-Left Fill sobre la lista
    de moldes, respetando las dimensiones de la tela y el margen de
    seguridad entre piezas.

    Parámetros
    ----------
    moldes       : Lista de dict con claves 'nombre', 'coordenadas', 'cantidad'.
    ancho_tela   : Ancho de la tela en cm.
    largo_tela   : Largo de la tela en cm.
    margen       : Separación mínima entre piezas en cm.
    angulo_paso  : Paso de rotación en grados (0 = sin rotación).
    paso_grid    : Resolución de la cuadrícula de búsqueda en cm.

    Retorna
    -------
    dict con claves:
      'colocadas'   – lista de resultados por pieza colocada
      'no_colocadas'– lista de nombres de piezas que no cupieron
      'metricas'    – dict con porcentaje, área_usada, área_residual
      'tiempo_s'    – tiempo de ejecución en segundos
    """
    t0 = time.perf_counter()
    angulos = _rotaciones(angulo_paso)

    # Expande 'cantidad' de cada molde
    piezas_a_colocar: list[dict] = []
    for molde in moldes:
        cant = int(molde.get("cantidad", 1))
        for i in range(cant):
            piezas_a_colocar.append({
                "nombre":      molde["nombre"] + (f"_{i+1}" if cant > 1 else ""),
                "coordenadas": molde["coordenadas"],
            })

    # Ordena de mayor a menor área (heurística: piezas grandes primero)
    def area_pieza(p):
        try:
            return Polygon(p["coordenadas"]).area
        except Exception:
            return 0.0

    piezas_a_colocar.sort(key=area_pieza, reverse=True)

    colocadas_pol: list[Polygon] = []   # polígonos con margen (para detección)
    resultados: list[dict] = []
    no_colocadas: list[str] = []

    area_tela = ancho_tela * largo_tela

    for pieza_info in piezas_a_colocar:
        try:
            pieza_base = _construir_poligono(pieza_info["coordenadas"])
        except Exception as exc:
            logger.error("Error construyendo polígono '%s': %s", pieza_info["nombre"], exc)
            no_colocadas.append(pieza_info["nombre"])
            continue

        pieza_col, ox, oy, ang = colocar_pieza(
            pieza_base, colocadas_pol, ancho_tela, largo_tela,
            margen, angulos, paso_grid
        )

        if pieza_col is None:
            logger.warning("Pieza '%s' no pudo colocarse.", pieza_info["nombre"])
            no_colocadas.append(pieza_info["nombre"])
            continue

        # Guarda el polígono con margen para las siguientes iteraciones
        colocadas_pol.append(_expandir_con_margen(pieza_col, margen))

        # Extrae coordenadas finales
        coords_finales = list(pieza_col.exterior.coords)

        resultados.append({
            "nombre":      pieza_info["nombre"],
            "angulo":      ang,
            "offset_x":   round(ox, 4),
            "offset_y":   round(oy, 4),
            "coordenadas": [[round(x, 4), round(y, 4)] for x, y in coords_finales],
            "area_cm2":    round(pieza_col.area, 4),
        })

    # ── Métricas ──────────────────────────────────────────────────
    area_usada = sum(r["area_cm2"] for r in resultados)
    porcentaje = round((area_usada / area_tela) * 100, 2) if area_tela > 0 else 0.0
    area_residual = round(area_tela - area_usada, 4)

    tiempo = round(time.perf_counter() - t0, 3)
    logger.info(
        "Nesting completado: %d colocadas, %d no colocadas, %.1f%% aprovechamiento, %.2f s",
        len(resultados), len(no_colocadas), porcentaje, tiempo
    )

    return {
        "colocadas":    resultados,
        "no_colocadas": no_colocadas,
        "metricas": {
            "area_tela_cm2":     round(area_tela, 4),
            "area_usada_cm2":    round(area_usada, 4),
            "area_residual_cm2": area_residual,
            "porcentaje_uso":    porcentaje,
            "piezas_colocadas":  len(resultados),
            "piezas_totales":    len(piezas_a_colocar),
        },
        "parametros": {
            "ancho_tela":   ancho_tela,
            "largo_tela":   largo_tela,
            "margen":       margen,
            "angulo_paso":  angulo_paso,
            "paso_grid":    paso_grid,
        },
        "tiempo_s": tiempo,
    }