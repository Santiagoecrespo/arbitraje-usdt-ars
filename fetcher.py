"""Cliente asincronico y de solo lectura para la API publica de CriptoYa."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp

from config import CONFIG, EXCHANGES_OBJETIVO
from storage import loguear_error


API_URL = "https://criptoya.com/api/usdt/ars/{volumen_usdt}"
TIMEOUT_SEGUNDOS = 10


async def obtener_cotizaciones(
    session: aiohttp.ClientSession, volumen_usdt: int
) -> dict[str, Any]:
    """Obtiene cotizaciones para el volumen solicitado o devuelve un dict vacio.

    La API es publica; esta funcion solo realiza una solicitud GET y no usa
    credenciales ni envia ordenes.
    """
    if volumen_usdt <= 0:
        loguear_error("volumen_usdt debe ser mayor que cero", CONFIG.log_errores)
        return {}
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SEGUNDOS)
        async with session.get(API_URL.format(volumen_usdt=volumen_usdt), timeout=timeout) as respuesta:
            if respuesta.status != 200:
                loguear_error(f"CriptoYa HTTP {respuesta.status}", CONFIG.log_errores)
                return {}
            try:
                datos = await respuesta.json(content_type=None)
            except (ValueError, aiohttp.ClientError) as exc:
                loguear_error(f"CriptoYa devolvio JSON invalido: {exc}", CONFIG.log_errores)
                return {}
            if not isinstance(datos, dict):
                loguear_error("CriptoYa devolvio una respuesta que no es un objeto", CONFIG.log_errores)
                return {}
            return datos
    except TimeoutError:
        loguear_error("Timeout: CriptoYa no respondio en 10s", CONFIG.log_errores)
    except aiohttp.ClientError as exc:
        loguear_error(f"Error de red contra CriptoYa: {exc}", CONFIG.log_errores)
    except Exception as exc:  # Cubre errores inesperados sin detener el monitor.
        loguear_error(f"Error inesperado al consultar CriptoYa: {exc}", CONFIG.log_errores)
    return {}


def precio_referencia(datos: Mapping[str, Any]) -> float:
    """Devuelve el primer ask valido, o 1300 ARS/USDT si no existen datos utiles."""
    for exchange in EXCHANGES_OBJETIVO:
        info = datos.get(exchange)
        if not isinstance(info, Mapping):
            continue
        valor = info.get("totalAsk") or info.get("ask")
        try:
            precio = float(valor)
        except (TypeError, ValueError):
            continue
        if precio > 0:
            return precio
    return 1300.0
