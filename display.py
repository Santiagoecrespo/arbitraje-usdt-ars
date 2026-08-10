"""Funciones de presentacion para la consola; no consultan ni guardan datos."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def imprimir_reporte(
    cycle_id: int,
    timestamp: str,
    oportunidades: Sequence[dict[str, Any]],
    activos: int,
    latencia_ms: int,
    promedio_movil: float,
    margen_minimo_pct: float,
) -> None:
    """Imprime el resumen del ciclo y sus cinco mejores combinaciones."""
    mejor = float(oportunidades[0]["margen_neto_pct"]) if oportunidades else 0.0
    print(f"\n{'=' * 76}")
    print(
        f"[{timestamp}] Ciclo #{cycle_id} | Duracion: {latencia_ms} ms | "
        f"Exchanges activos: {activos}/8"
    )
    print(f"Promedio movil: {promedio_movil:.3f}% | Mejor: {mejor:.3f}%")
    print(f"{'=' * 76}")
    if not oportunidades:
        print("Sin oportunidades evaluables en este ciclo.")
        return

    print(f"{'ESTADO':<10} {'COMPRA':<14} {'VENTA':<14} {'BRUTA':>8} {'NETO':>8} {'GANANCIA ARS':>16}")
    print("-" * 76)
    for op in oportunidades[:5]:
        margen = float(op["margen_neto_pct"])
        estado = "VERDE" if margen >= margen_minimo_pct else "ROJO"
        print(
            f"{estado:<10} {str(op['ex_compra']).upper():<14} {str(op['ex_venta']).upper():<14} "
            f"{float(op['brecha_bruta_pct']):>7.2f}% {margen:>7.2f}% "
            f"${float(op['ganancia_ars']):>14,.0f}"
        )


def imprimir_desglose(resultado: dict[str, Any], capital_ars: float) -> None:
    """Muestra el recorrido fiscal y operativo de una oportunidad calculada."""
    ganancia = float(resultado["ganancia_ars"])
    etiqueta = "Ganancia" if ganancia >= 0 else "Perdida"
    print("\nDesglose de la mejor oportunidad")
    print(
        f"Capital: ${capital_ars:,.0f} "
        f"-> tras retenciones: ${float(resultado['pesos_reales']):,.0f} "
        f"-> USDT comprados: {float(resultado['usdt_brutos']):,.2f} "
        f"-> tras comision y gas: {float(resultado['usdt_transferidos']):,.2f} "
        f"-> Pesos recuperados: ${float(resultado['pesos_netos']):,.0f} "
        f"-> {etiqueta}: ${ganancia:,.0f} ({float(resultado['margen_neto_pct']):.2f}%)"
    )


def imprimir_resumen(historial: Sequence[dict[str, Any]], margen_minimo_pct: float) -> None:
    """Imprime estadisticas agregadas del historial de mejores oportunidades."""
    if not historial:
        print("\nSin ciclos con oportunidades para resumir.")
        return
    margenes = [float(item["margen_neto_pct"]) for item in historial]
    verdes = [margen for margen in margenes if margen >= margen_minimo_pct]
    mejor = max(historial, key=lambda item: float(item["margen_neto_pct"]))
    print(f"\n{'#' * 76}")
    print(f"RESUMEN - ultimos {len(historial)} ciclos con oportunidades")
    print(f"Promedio: {sum(margenes) / len(margenes):.3f}% | Max: {max(margenes):.3f}% | Min: {min(margenes):.3f}%")
    print(f"Ciclos VERDE: {len(verdes)}/{len(margenes)} ({len(verdes) / len(margenes) * 100:.1f}%)")
    print(f"Mejor par: {str(mejor['ex_compra']).upper()} -> {str(mejor['ex_venta']).upper()} ({float(mejor['margen_neto_pct']):.3f}%)")
    print("#" * 76)


def imprimir_persistencia(estadisticas: dict[str, Any]) -> None:
    """Presenta la persistencia temporal de diferencias de cotizaciones."""
    print(f"\n{'-' * 76}")
    print("PERSISTENCIA DE COTIZACIONES")
    print(
        f"Observaciones evaluadas: {estadisticas['total_observaciones']} | "
        f"Sin dato: {estadisticas['total_sin_dato']} | "
        f"Abiertas: {estadisticas['observaciones_abiertas']}"
    )
    print(f"{'Demora':<12} {'Teorico':>12} {'Estimado':>12} {'Conservador':>14}")
    for demora, perfiles in estadisticas["por_demora"].items():
        def porcentaje(nombre: str) -> str:
            valor = perfiles[nombre]["pct_persistencia"]
            return "-" if valor is None else f"{float(valor):.0f}%"

        print(
            f"{str(demora) + ' min':<12} {porcentaje('teorico'):>12} "
            f"{porcentaje('estimado'):>12} {porcentaje('conservador'):>14}"
        )

    deterioros = estadisticas["deterioro_promedio_por_demora"]
    demora_referencia = 5 if 5 in deterioros else next(iter(deterioros), None)
    if demora_referencia is not None and deterioros[demora_referencia] is not None:
        print(
            f"Deterioro promedio a {demora_referencia} min: "
            f"{float(deterioros[demora_referencia]):.2f}%"
        )
    mejor_par = estadisticas["par_mayor_persistencia"]
    if mejor_par is not None:
        print(
            "Par con mayor persistencia: "
            f"{str(mejor_par['ex_origen']).upper()} -> {str(mejor_par['ex_destino']).upper()} "
            f"({float(mejor_par['pct_persistencia']):.0f}% a {mejor_par['demora_minutos']} min, "
            f"perfil {mejor_par['perfil']})"
        )
    print("-" * 76)
