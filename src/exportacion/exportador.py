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

# backend configurado por la interfaz principal
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Polygon as MplPolygon

logger = logging.getLogger("nesting.exportador")

# MEJORA 3: rutas resueltas en tiempo de ejecución, no en importación
def _get_dirs() -> tuple[str, str]:
    base = os.path.dirname(__file__)
    return (
        os.path.join(base, "..", "..", "exports"),
        os.path.join(base, "..", "..", "data", "simulaciones"),
    )

# MEJORA 7: constante extraída para fácil ajuste
MAX_LEYENDA = 12

COLORES = [
    "#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6",
    "#1abc9c", "#e67e22", "#34495e", "#16a085", "#c0392b",
    "#8e44ad", "#27ae60", "#d35400", "#2980b9", "#7f8c8d",
]


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _asegurar_dirs() -> tuple[str, str]:
    dir_exports, dir_sims = _get_dirs()  # MEJORA 3
    os.makedirs(dir_exports, exist_ok=True)
    os.makedirs(dir_sims, exist_ok=True)
    return dir_exports, dir_sims


# ─────────────────────────────────────────────────────────────────
#  GUARDAR SIMULACIÓN (persistencia interna)
# ─────────────────────────────────────────────────────────────────
def guardar_simulacion(resultado: dict, nombre_sim: str = "") -> tuple[bool, str]:  # MEJORA 4
    """Guarda la simulación completa en data/simulaciones/ para consulta posterior."""
    _, dir_sims = _asegurar_dirs()
    ts = _ts()
    nombre_archivo = f"{nombre_sim or 'sim'}_{ts}.json"
    ruta = os.path.join(dir_sims, nombre_archivo)
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
    _, dir_sims = _asegurar_dirs()
    sims = []
    for archivo in sorted(os.listdir(dir_sims), reverse=True):
        if archivo.endswith(".json"):
            ruta = os.path.join(dir_sims, archivo)
            try:
                with open(ruta, encoding="utf-8") as f:
                    datos = json.load(f)
                sims.append({
                    "archivo": archivo,
                    "timestamp": datos.get("timestamp", ""),
                    "metricas": datos.get("metricas", {}),
                    "parametros": datos.get("parametros", {}),
                })
            except Exception as exc:  # MEJORA 2: ya no silencioso
                logger.warning("Archivo de simulación dañado o ilegible '%s': %s", archivo, exc)
    return sims


# ─────────────────────────────────────────────────────────────────
#  EXPORTAR JSON
# ─────────────────────────────────────────────────────────────────
def exportar_json(resultado: dict, ruta_destino: str = "") -> tuple[bool, str]:  # MEJORA 4
    """Exporta el resultado completo de la simulación en JSON."""
    dir_exports, _ = _asegurar_dirs()
    if not ruta_destino:
        ruta_destino = os.path.join(dir_exports, f"nesting_{_ts()}.json")
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
def exportar_csv(resultado: dict, ruta_destino: str = "") -> tuple[bool, str]:  # MEJORA 4
    """Exporta la lista de piezas colocadas en CSV."""
    dir_exports, _ = _asegurar_dirs()
    if not ruta_destino:
        ruta_destino = os.path.join(dir_exports, f"nesting_{_ts()}.csv")

    colocadas = resultado.get("colocadas", [])
    metricas  = resultado.get("metricas", {})
    params    = resultado.get("parametros", {})

    try:
        with open(ruta_destino, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["=== PARÁMETROS DE TELA ==="])
            writer.writerow(["Ancho (cm)", params.get("ancho_tela", ""), "Largo (cm)", params.get("largo_tela", "")])
            writer.writerow(["Margen (cm)", params.get("margen", ""), "Paso rotación (°)", params.get("angulo_paso", "")])
            writer.writerow([])
            writer.writerow(["=== MÉTRICAS ==="])
            writer.writerow(["Área tela (cm²)", metricas.get("area_tela_cm2", "")])
            writer.writerow(["Área utilizada (cm²)", metricas.get("area_usada_cm2", "")])
            writer.writerow(["Área residual (cm²)", metricas.get("area_residual_cm2", "")])
            writer.writerow(["% Aprovechamiento", metricas.get("porcentaje_uso", "")])
            writer.writerow(["Piezas colocadas", metricas.get("piezas_colocadas", "")])
            writer.writerow(["Piezas totales", metricas.get("piezas_totales", "")])
            writer.writerow([])
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
def exportar_imagen(resultado: dict, ruta_destino: str = "",
                    titulo: str = "Distribución Optimizada de Piezas Textiles") -> tuple[bool, str]:  # MEJORA 4
    """
    Genera y guarda una imagen PNG de la distribución de piezas sobre la tela.
    Incluye leyenda, métricas y título del proyecto.
    """
    # MEJORA 1: se eliminó matplotlib.use("Agg") de aquí; lo controla la interfaz principal
    dir_exports, _ = _asegurar_dirs()
    if not ruta_destino:
        ruta_destino = os.path.join(dir_exports, f"nesting_{_ts()}.png")

    params    = resultado.get("parametros", {})
    metricas  = resultado.get("metricas", {})
    colocadas = resultado.get("colocadas", [])

    ancho = params.get("ancho_tela", 150)
    largo = params.get("largo_tela", 300)

    fig = None  
    # MEJORA 5: evita NameError en el except si subplots falla
    try:
        fig, ax = plt.subplots(figsize=(10, max(6, largo / ancho * 7)))
        ax.set_xlim(0, ancho)
        ax.set_ylim(0, largo)
        ax.set_aspect("equal")
        ax.set_facecolor("#f5f5dc")

        tela_rect = plt.Rectangle((0, 0), ancho, largo, linewidth=2,
                                   edgecolor="#555555", facecolor="#f5f5dc", zorder=0)
        ax.add_patch(tela_rect)

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

            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            # MEJORA 6: indicador visual de truncado
            nombre_raw = pieza["nombre"]
            nombre_corto = nombre_raw[:10] + ("…" if len(nombre_raw) > 10 else "")
            ax.text(cx, cy, nombre_corto, ha="center", va="center",
                    fontsize=5.5, color="white", fontweight="bold", zorder=3)

            leyenda_handles.append(
                mpatches.Patch(color=color, label=f"{pieza['nombre']} ({pieza['area_cm2']:.1f} cm²)")
            )

        if leyenda_handles:
            ax.legend(handles=leyenda_handles[:MAX_LEYENDA], loc="upper right",  # MEJORA 7
                      fontsize=6, framealpha=0.85, title="Piezas")

        ax.set_xlabel("Ancho de tela (cm)", fontsize=9)
        ax.set_ylabel("Largo de tela (cm)", fontsize=9)

        pct  = metricas.get("porcentaje_uso", 0)
        n_ok = metricas.get("piezas_colocadas", 0)
        n_tt = metricas.get("piezas_totales", 0)
        fig.suptitle(titulo, fontsize=11, fontweight="bold", y=0.98)
        ax.set_title(
            f"Aprovechamiento: {pct:.1f}%  |  Piezas: {n_ok}/{n_tt}  |  "
            f"Tela: {ancho}×{largo} cm  |  Residuo: {metricas.get('area_residual_cm2', 0):.1f} cm²",
            fontsize=8, color="#333333"
        )

        ax.grid(True, which="both", linestyle="--", linewidth=0.3, color="#aaaaaa", alpha=0.5, zorder=1)
        ax.set_xticks(range(0, int(ancho) + 1, max(1, int(ancho // 10))))
        ax.set_yticks(range(0, int(largo) + 1, max(1, int(largo // 10))))

        plt.tight_layout()
        plt.savefig(ruta_destino, dpi=150, bbox_inches="tight")
        plt.close(fig)
        logger.info("Imagen exportada: %s", ruta_destino)
        return True, ruta_destino

    except Exception as exc:
        if fig is not None:  # MEJORA 5
            plt.close(fig)
        logger.error("Error exportando imagen: %s", exc)
        return False, str(exc)