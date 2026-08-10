"""Punto de entrada del monitor de arbitraje USDT/ARS en paper trading."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime, timezone

import aiohttp

from calculator import analizar_matriz
from config import CONFIG, EXCHANGES_OBJETIVO
from display import imprimir_desglose, imprimir_persistencia, imprimir_reporte, imprimir_resumen
from fetcher import obtener_cotizaciones, precio_referencia
from storage import guardar_ciclo, guardar_persistencia
from tracker import PersistenceTracker


VENTANA_PROMEDIO = 20
RESUMEN_CADA = 10
HISTORIAL_COMPLETO: deque[dict[str, object]] = deque(maxlen=2000)


async def main() -> None:
    """Consulta precios publicos, calcula margenes y persiste el paper trading."""
    historial_margenes: deque[float] = deque(maxlen=VENTANA_PROMEDIO)
    tracker = PersistenceTracker(CONFIG)
    ciclo = 0

    print("=" * 76)
    print("MONITOR DE ARBITRAJE USDT/ARS - PAPER TRADING")
    print(f"Capital simulado: ${CONFIG.capital_ars:,.0f} ARS | Red: {CONFIG.red_usada.upper()}")
    print(
        "Fiscal: "
        f"cheque {CONFIG.imp_cheque_debito * 100:.1f}% deb / {CONFIG.imp_cheque_credito * 100:.1f}% cred | "
        f"IIBB {CONFIG.iibb_entrada * 100:.1f}% ent / {CONFIG.iibb_salida * 100:.1f}% sal"
    )
    print(
        f"Intervalo: {CONFIG.intervalo_seg}s | CSV: {CONFIG.csv_salida} | "
        f"Persistencia: {CONFIG.persistencia_csv} | Log: {CONFIG.log_errores}"
    )
    print("Solo consulta precios publicos. No ejecuta operaciones ni usa credenciales.")
    print("=" * 76)

    try:
        async with aiohttp.ClientSession() as session:
            datos_iniciales = await obtener_cotizaciones(session, 1_000)
            precio_ref = precio_referencia(datos_iniciales)
            print(f"Precio de referencia inicial: ${precio_ref:,.2f} ARS/USDT")

            while True:
                ciclo += 1
                ahora_utc = datetime.now(timezone.utc)
                timestamp_utc = ahora_utc.isoformat()
                inicio = time.time()
                volumen_usdt = max(50, int(CONFIG.capital_ars / precio_ref))
                datos = await obtener_cotizaciones(session, volumen_usdt)
                duracion_ms = int((time.time() - inicio) * 1000)

                if not datos:
                    mediciones = tracker.actualizar_observaciones({}, ahora_utc)
                    guardar_persistencia(mediciones, CONFIG)
                    historial_margenes.append(0.0)
                    promedio = sum(historial_margenes) / len(historial_margenes)
                    imprimir_reporte(
                        ciclo, timestamp_utc, [], 0, duracion_ms, promedio, CONFIG.margen_minimo_pct
                    )
                    await asyncio.sleep(CONFIG.intervalo_seg)
                    continue

                precio_ref = precio_referencia(datos)
                activos = sum(1 for exchange in EXCHANGES_OBJETIVO if exchange in datos)
                oportunidades = analizar_matriz(datos, CONFIG)
                mediciones = tracker.actualizar_observaciones(datos, ahora_utc)
                guardar_persistencia(mediciones, CONFIG)
                for evaluacion in oportunidades:
                    tracker.registrar_si_nueva(evaluacion, ahora_utc)
                mejor_margen = float(oportunidades[0]["margen_neto_pct"]) if oportunidades else 0.0
                historial_margenes.append(mejor_margen)
                promedio = sum(historial_margenes) / len(historial_margenes)

                imprimir_reporte(
                    ciclo,
                    timestamp_utc,
                    oportunidades,
                    activos,
                    duracion_ms,
                    promedio,
                    CONFIG.margen_minimo_pct,
                )
                guardar_ciclo(ciclo, timestamp_utc, duracion_ms, oportunidades, CONFIG)

                if oportunidades:
                    imprimir_desglose(oportunidades[0], CONFIG.capital_ars)
                    HISTORIAL_COMPLETO.append(
                        {
                            "margen_neto_pct": oportunidades[0]["margen_neto_pct"],
                            "ex_compra": oportunidades[0]["ex_compra"],
                            "ex_venta": oportunidades[0]["ex_venta"],
                        }
                    )
                if ciclo % RESUMEN_CADA == 0:
                    imprimir_resumen(HISTORIAL_COMPLETO, CONFIG.margen_minimo_pct)
                    imprimir_persistencia(tracker.estadisticas())
                await asyncio.sleep(CONFIG.intervalo_seg)
    finally:
        print("\nMonitor detenido.")
        imprimir_resumen(HISTORIAL_COMPLETO, CONFIG.margen_minimo_pct)
        imprimir_persistencia(tracker.estadisticas())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
