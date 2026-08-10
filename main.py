"""Punto de entrada del monitor de arbitraje USDT/ARS en paper trading."""

from __future__ import annotations

import asyncio
import signal
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


def _instalar_manejadores_detencion(evento_detencion: asyncio.Event) -> None:
    """Solicita cierre ordenado ante Ctrl+C o SIGTERM de un proveedor cloud."""
    loop = asyncio.get_running_loop()

    def solicitar_detencion() -> None:
        if not evento_detencion.is_set():
            print("\nSenal de detencion recibida; cerrando el monitor...")
            evento_detencion.set()

    for senal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(senal, solicitar_detencion)
        except (NotImplementedError, RuntimeError):
            # Windows no implementa add_signal_handler para todos los loops.
            signal.signal(senal, lambda *_: loop.call_soon_threadsafe(solicitar_detencion))


async def _obtener_hasta_detener(
    session: aiohttp.ClientSession,
    volumen_usdt: int,
    evento_detencion: asyncio.Event,
) -> dict:
    """Cancela una consulta pendiente si el proceso recibe una senal de cierre."""
    consulta = asyncio.create_task(obtener_cotizaciones(session, volumen_usdt))
    espera_detencion = asyncio.create_task(evento_detencion.wait())
    terminadas, pendientes = await asyncio.wait(
        {consulta, espera_detencion},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for tarea in pendientes:
        tarea.cancel()
    await asyncio.gather(*pendientes, return_exceptions=True)
    if espera_detencion in terminadas:
        return {}
    return consulta.result()


async def _esperar_siguiente_ciclo(evento_detencion: asyncio.Event, segundos: int) -> None:
    """Espera el intervalo configurado o termina de inmediato cuando recibe SIGTERM."""
    try:
        await asyncio.wait_for(evento_detencion.wait(), timeout=segundos)
    except asyncio.TimeoutError:
        pass


async def main(evento_detencion: asyncio.Event | None = None) -> None:
    """Consulta precios publicos, calcula margenes y persiste el paper trading."""
    historial_margenes: deque[float] = deque(maxlen=VENTANA_PROMEDIO)
    tracker = PersistenceTracker(CONFIG)
    evento_detencion = evento_detencion or asyncio.Event()
    _instalar_manejadores_detencion(evento_detencion)
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
        if evento_detencion.is_set():
            return
        async with aiohttp.ClientSession() as session:
            datos_iniciales = await _obtener_hasta_detener(session, 1_000, evento_detencion)
            if evento_detencion.is_set():
                return
            precio_ref = precio_referencia(datos_iniciales)
            print(f"Precio de referencia inicial: ${precio_ref:,.2f} ARS/USDT")

            while not evento_detencion.is_set():
                ciclo += 1
                ahora_utc = datetime.now(timezone.utc)
                timestamp_utc = ahora_utc.isoformat()
                inicio = time.time()
                volumen_usdt = max(50, int(CONFIG.capital_ars / precio_ref))
                datos = await _obtener_hasta_detener(session, volumen_usdt, evento_detencion)
                duracion_ms = int((time.time() - inicio) * 1000)

                if evento_detencion.is_set():
                    break

                if not datos:
                    mediciones = tracker.actualizar_observaciones({}, ahora_utc)
                    guardar_persistencia(mediciones, CONFIG)
                    historial_margenes.append(0.0)
                    promedio = sum(historial_margenes) / len(historial_margenes)
                    imprimir_reporte(
                        ciclo, timestamp_utc, [], 0, duracion_ms, promedio, CONFIG.margen_minimo_pct
                    )
                    await _esperar_siguiente_ciclo(evento_detencion, CONFIG.intervalo_seg)
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
                await _esperar_siguiente_ciclo(evento_detencion, CONFIG.intervalo_seg)
    finally:
        print("\nMonitor detenido.")
        imprimir_resumen(HISTORIAL_COMPLETO, CONFIG.margen_minimo_pct)
        imprimir_persistencia(tracker.estadisticas())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
