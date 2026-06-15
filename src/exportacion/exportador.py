"""
=====================================================================
  src/exportador.py
  Módulo de Exportación de Resultados  (RF-07)
  Exporta simulaciones en JSON, CSV e imagen PNG.
  También guarda el historial de simulaciones para consulta posterior.
=====================================================================
"""

import json
import csv
import os
import logging
from datetime import datetime

import matplotlib
# backend configurado por la interfaz principal
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.collections import PatchCollection

logger = logging.getLogger("nesting.exportador")

DIR_EXPORTS    = os.path.join(os.path.dirname(__file__), "..", "..", "exports")
DIR_SIMULACIONES = os.path.join(os.path.dirname(__file__), "..", "..", "data", "simulaciones")


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _asegurar_dirs():
    os.makedirs(DIR_EXPORTS, exist_ok=True)
    os.makedirs(DIR_SIMULACIONES, exist_ok=True)


# ─────────────────────────────────────────────────────────────────
#  GUARDAR SIMULACIÓN (persistencia interna)
# ─────────────────────────────────────────────────────────────────
def guardar_simulacion(resultado: dict, nombre_sim: str = "") -> tuple[bool, str]:
    """Guarda la simulación completa en data/simulaciones/ para consulta posterior."""
    _asegurar_dirs()
    ts = _ts()
    nombre_archivo = f"{nombre_sim or 'sim'}_{ts}.json"
    ruta = os.path.join(DIR_SIMULACIONES, nombre_archivo)
    try:
        resultado["timestamp"] = ts
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        logger.info("Simulación guardada: %s", ruta)
        return True, ruta
    except OSError as exc:
        logger.error("Error guardando simulación: %s", exc)
        return False, str(exc)


def listar_simulaciones() -> list[dict]:
    """Lista simulaciones guardadas con sus métricas básicas."""
    _asegurar_dirs()
    sims = []
    for archivo in sorted(os.listdir(DIR_SIMULACIONES), reverse=True):
        if archivo.endswith(".json"):
            ruta = os.path.join(DIR_SIMULACIONES, archivo)
            try:
                with open(ruta, encoding="utf-8") as f:
                    datos = json.load(f)
                sims.append({
                    "archivo": archivo,
                    "timestamp": datos.get("timestamp", ""),
                    "metricas": datos.get("metricas", {}),
                    "parametros": datos.get("parametros", {}),
                })
            except Exception:
                pass
    return sims


# ─────────────────────────────────────────────────────────────────
#  EXPORTAR JSON
# ─────────────────────────────────────────────────────────────────
def exportar_json(resultado: dict, ruta_destino: str = "") -> tuple[bool, str]:
    """Exporta el resultado completo de la simulación en JSON."""
    _asegurar_dirs()
    if not ruta_destino:
        ruta_destino = os.path.join(DIR_EXPORTS, f"nesting_{_ts()}.json")
    try:
        with open(ruta_destino, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        logger.info("Exportado JSON: %s", ruta_destino)
        return True, ruta_destino
    except OSError as exc:
        logger.error("Error exportando JSON: %s", exc)
        return False, str(exc)


# ─────────────────────────────────────────────────────────────────
#  EXPORTAR CSV
# ─────────────────────────────────────────────────────────────────
def exportar_csv(resultado: dict, ruta_destino: str = "") -> tuple[bool, str]:
    """Exporta la lista de piezas colocadas en CSV."""
    _asegurar_dirs()
    if not ruta_destino:
        ruta_destino = os.path.join(DIR_EXPORTS, f"nesting_{_ts()}.csv")

    colocadas = resultado.get("colocadas", [])
    metricas  = resultado.get("metricas", {})
    params    = resultado.get("parametros", {})

    try:
        with open(ruta_destino, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # Encabezado de parámetros
            writer.writerow(["=== PARÁMETROS DE TELA ==="])
            writer.writerow(["Ancho (cm)", params.get("ancho_tela", ""), "Largo (cm)", params.get("largo_tela", "")])
            writer.writerow(["Margen (cm)", params.get("margen", ""), "Paso rotación (°)", params.get("angulo_paso", "")])
            writer.writerow([])
            # Métricas
            writer.writerow(["=== MÉTRICAS ==="])
            writer.writerow(["Área tela (cm²)", metricas.get("area_tela_cm2", "")])
            writer.writerow(["Área utilizada (cm²)", metricas.get("area_usada_cm2", "")])
            writer.writerow(["Área residual (cm²)", metricas.get("area_residual_cm2", "")])
            writer.writerow(["% Aprovechamiento", metricas.get("porcentaje_uso", "")])
            writer.writerow(["Piezas colocadas", metricas.get("piezas_colocadas", "")])
            writer.writerow(["Piezas totales", metricas.get("piezas_totales", "")])
            writer.writerow([])
            # Detalle piezas
            writer.writerow(["=== DETALLE DE PIEZAS COLOCADAS ==="])
            writer.writerow(["Nombre", "Offset X (cm)", "Offset Y (cm)", "Ángulo (°)", "Área (cm²)"])
            for p in colocadas:
                writer.writerow([
                    p.get("nombre", ""),
                    p.get("offset_x", ""),
                    p.get("offset_y", ""),
                    p.get("angulo", ""),
                    p.get("area_cm2", ""),
                ])
            # No colocadas
            no_col = resultado.get("no_colocadas", [])
            if no_col:
                writer.writerow([])
                writer.writerow(["=== PIEZAS NO COLOCADAS (sin espacio en tela) ==="])
                for nombre in no_col:
                    writer.writerow([nombre])

        logger.info("Exportado CSV: %s", ruta_destino)
        return True, ruta_destino
    except OSError as exc:
        logger.error("Error exportando CSV: %s", exc)
        return False, str(exc)


# ─────────────────────────────────────────────────────────────────
#  EXPORTAR IMAGEN PNG
# ─────────────────────────────────────────────────────────────────
COLORES = [
    "#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6",
    "#1abc9c", "#e67e22", "#34495e", "#16a085", "#c0392b",
    "#8e44ad", "#27ae60", "#d35400", "#2980b9", "#7f8c8d",
]


def exportar_imagen(resultado: dict, ruta_destino: str = "",
                    titulo: str = "Distribución Optimizada de Piezas Textiles") -> tuple[bool, str]:
    """
    Genera y guarda una imagen PNG de la distribución de piezas sobre la tela.
    Incluye leyenda, métricas y título del proyecto.
    """
    import matplotlib
    matplotlib.use("Agg")
    _asegurar_dirs()
    if not ruta_destino:
        ruta_destino = os.path.join(DIR_EXPORTS, f"nesting_{_ts()}.png")

    params    = resultado.get("parametros", {})
    metricas  = resultado.get("metricas", {})
    colocadas = resultado.get("colocadas", [])

    ancho = params.get("ancho_tela", 150)
    largo = params.get("largo_tela", 300)

    fig, ax = plt.subplots(figsize=(10, max(6, largo / ancho * 7)))
    ax.set_xlim(0, ancho)
    ax.set_ylim(0, largo)
    ax.set_aspect("equal")
    ax.set_facecolor("#f5f5dc")   # color tela (beige)

    # Dibuja la superficie de tela
    tela_rect = plt.Rectangle((0, 0), ancho, largo, linewidth=2,
                               edgecolor="#555555", facecolor="#f5f5dc", zorder=0)
    ax.add_patch(tela_rect)

    # Dibuja cada pieza
    leyenda_handles = []
    for i, pieza in enumerate(colocadas):
        coords = pieza.get("coordenadas", [])
        if len(coords) < 3:
            continue
        color = COLORES[i % len(COLORES)]
        pts = [(x, y) for x, y in coords]
        patch = MplPolygon(pts, closed=True, facecolor=color, edgecolor="white",
                           linewidth=0.8, alpha=0.80, zorder=2)
        ax.add_patch(patch)

        # Texto centroide
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        nombre_corto = pieza["nombre"][:10]
        ax.text(cx, cy, nombre_corto, ha="center", va="center",
                fontsize=5.5, color="white", fontweight="bold", zorder=3)

        leyenda_handles.append(
            mpatches.Patch(color=color, label=f"{pieza['nombre']} ({pieza['area_cm2']:.1f} cm²)")
        )

    # Leyenda (máx. 12 elementos para no saturar)
    if leyenda_handles:
        ax.legend(handles=leyenda_handles[:12], loc="upper right",
                  fontsize=6, framealpha=0.85, title="Piezas")

    # Etiquetas de ejes
    ax.set_xlabel("Ancho de tela (cm)", fontsize=9)
    ax.set_ylabel("Largo de tela (cm)", fontsize=9)

    # Título y subtítulo con métricas
    pct  = metricas.get("porcentaje_uso", 0)
    n_ok = metricas.get("piezas_colocadas", 0)
    n_tt = metricas.get("piezas_totales", 0)
    fig.suptitle(titulo, fontsize=11, fontweight="bold", y=0.98)
    ax.set_title(
        f"Aprovechamiento: {pct:.1f}%  |  Piezas: {n_ok}/{n_tt}  |  "
        f"Tela: {ancho}×{largo} cm  |  Residuo: {metricas.get('area_residual_cm2', 0):.1f} cm²",
        fontsize=8, color="#333333"
    )

    # Grilla ligera
    ax.grid(True, which="both", linestyle="--", linewidth=0.3, color="#aaaaaa", alpha=0.5, zorder=1)
    ax.set_xticks(range(0, int(ancho) + 1, max(1, int(ancho // 10))))
    ax.set_yticks(range(0, int(largo) + 1, max(1, int(largo // 10))))

    try:
        plt.tight_layout()
        plt.savefig(ruta_destino, dpi=150, bbox_inches="tight")
        plt.close(fig)
        logger.info("Imagen exportada: %s", ruta_destino)
        return True, ruta_destino
    except Exception as exc:
        plt.close(fig)
        logger.error("Error exportando imagen: %s", exc)
        return False, str(exc)