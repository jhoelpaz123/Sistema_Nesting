
import logging

logger = logging.getLogger("nesting.metricas")


def calcular_metricas(resultado_nesting: dict) -> dict:
    """
    Extrae y enriquece las métricas de un resultado de nesting.

    Parámetros
    ----------
    resultado_nesting : dict retornado por motor_nesting.ejecutar_nesting()

    Retorna
    -------
    dict con métricas completas y etiquetas de calidad.
    """
    m = resultado_nesting.get("metricas", {})

    porcentaje = m.get("porcentaje_uso", 0.0)

    if porcentaje >= 90:
        nivel = "Excelente"
        color_nivel = "#27ae60"
    elif porcentaje >= 75:
        nivel = "Bueno"
        color_nivel = "#2980b9"
    elif porcentaje >= 60:
        nivel = "Regular"
        color_nivel = "#f39c12"
    else:
        nivel = "Bajo"
        color_nivel = "#e74c3c"

    return {
        **m,
        "nivel_aprovechamiento": nivel,
        "color_nivel": color_nivel,
        "tiempo_s": resultado_nesting.get("tiempo_s", 0.0),
    }


def comparar_manual_vs_optimizado(
    porcentaje_manual: float,
    porcentaje_optimizado: float,
    area_tela: float,
) -> dict:
    """
    Compara la distribución manual ingresada por el operario con la
    distribución generada por el algoritmo.

    Parámetros
    ----------
    porcentaje_manual      : % de aprovechamiento manual (0–100).
    porcentaje_optimizado  : % de aprovechamiento del algoritmo.
    area_tela              : Área total de la tela en cm².

    Retorna
    -------
    dict con diferencial, ahorro estimado y recomendación.
    """
    try:
        diferencial = round(porcentaje_optimizado - porcentaje_manual, 2)
        area_manual_usada     = area_tela * (porcentaje_manual / 100)
        area_optim_usada      = area_tela * (porcentaje_optimizado / 100)
        ahorro_area_cm2       = round(area_optim_usada - area_manual_usada, 2)

        if diferencial > 0:
            recomendacion = (
                f"El sistema mejora el aprovechamiento en {diferencial:.1f}%. "
                f"Se recuperan {ahorro_area_cm2:.1f} cm² de tela por simulación."
            )
        elif diferencial == 0:
            recomendacion = "El sistema obtiene el mismo aprovechamiento que la distribución manual."
        else:
            recomendacion = (
                f"La distribución manual supera al algoritmo en {abs(diferencial):.1f}%. "
                "Considere reducir el margen de seguridad o el paso de rotación."
            )

        logger.info(
            "Comparación: manual=%.1f%% | optimizado=%.1f%% | diferencial=%.1f%%",
            porcentaje_manual, porcentaje_optimizado, diferencial
        )

        return {
            "porcentaje_manual":     round(porcentaje_manual, 2),
            "porcentaje_optimizado": round(porcentaje_optimizado, 2),
            "diferencial_pct":       diferencial,
            "area_tela_cm2":         round(area_tela, 2),
            "area_manual_usada_cm2": round(area_manual_usada, 2),
            "area_optim_usada_cm2":  round(area_optim_usada, 2),
            "ahorro_area_cm2":       ahorro_area_cm2,
            "recomendacion":         recomendacion,
        }

    except Exception as exc:
        logger.exception("Error en comparación manual vs optimizado")
        return {"error": str(exc)}