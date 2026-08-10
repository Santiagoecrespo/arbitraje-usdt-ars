"""Calculos puros para el arbitraje USDT/ARS simulado."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from config import Config, EXCHANGES_OBJETIVO


def _numero_positivo(valor: object) -> float | None:
    """Convierte un precio a float positivo y finito, o devuelve ``None``."""
    try:
        numero = float(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return numero if isfinite(numero) and numero > 0 else None


def calcular_margen(
    precio_compra: float,
    precio_venta: float,
    cfg: Config,
) -> dict[str, float | str] | None:
    """Calcula el resultado neto de una vuelta compra-transferencia-venta.

    No realiza IO ni modifica estado. Los costos se aplican en el orden en que
    ocurririan en la operacion simulada.
    """
    compra = _numero_positivo(precio_compra)
    venta = _numero_positivo(precio_venta)
    if compra is None or venta is None or cfg.capital_ars <= 0:
        return None

    pesos_reales = cfg.capital_ars * (1 - cfg.imp_cheque_debito - cfg.iibb_entrada)
    usdt_brutos = pesos_reales / compra
    usdt_post_comision = usdt_brutos * (1 - cfg.comision_compra)
    usdt_transferidos = usdt_post_comision - cfg.gas_fee_usdt
    if usdt_transferidos <= 0:
        return None

    usdt_a_vender = usdt_transferidos * (1 - cfg.comision_venta)
    pesos_acreditados = usdt_a_vender * venta
    pesos_netos = pesos_acreditados * (1 - cfg.imp_cheque_credito - cfg.iibb_salida)
    ganancia_ars = pesos_netos - cfg.capital_ars
    margen_neto_pct = ganancia_ars / cfg.capital_ars * 100
    brecha_bruta_pct = (venta - compra) / compra * 100
    carga_fiscal_ars = (
        cfg.capital_ars * (cfg.imp_cheque_debito + cfg.iibb_entrada)
        + pesos_acreditados * (cfg.imp_cheque_credito + cfg.iibb_salida)
    )

    return {
        "pesos_reales": pesos_reales,
        "usdt_brutos": usdt_brutos,
        "usdt_post_comision": usdt_post_comision,
        "usdt_transferidos": usdt_transferidos,
        "usdt_a_vender": usdt_a_vender,
        "pesos_acreditados": pesos_acreditados,
        "pesos_netos": pesos_netos,
        "ganancia_ars": ganancia_ars,
        "margen_neto_pct": margen_neto_pct,
        "brecha_bruta_pct": brecha_bruta_pct,
        "carga_fiscal_ars": carga_fiscal_ars,
        "gas_fee_usdt": cfg.gas_fee_usdt,
        "red": cfg.red_usada,
    }


def _precio(info: Mapping[str, Any], campo_preferido: str, alternativo: str) -> float | None:
    return _numero_positivo(info.get(campo_preferido) or info.get(alternativo))


def analizar_matriz(datos: Mapping[str, Any], cfg: Config) -> list[dict[str, Any]]:
    """Evalua cada compra y venta entre exchanges distintos, ordenada por margen."""
    oportunidades: list[dict[str, Any]] = []
    for ex_compra in EXCHANGES_OBJETIVO:
        info_compra = datos.get(ex_compra)
        if not isinstance(info_compra, Mapping):
            continue
        precio_compra = _precio(info_compra, "totalAsk", "ask")
        if precio_compra is None:
            continue

        for ex_venta in EXCHANGES_OBJETIVO:
            if ex_venta == ex_compra:
                continue
            info_venta = datos.get(ex_venta)
            if not isinstance(info_venta, Mapping):
                continue
            precio_venta = _precio(info_venta, "totalBid", "bid")
            if precio_venta is None:
                continue

            margen = calcular_margen(precio_compra, precio_venta, cfg)
            if margen is not None:
                oportunidades.append(
                    {
                        "ex_compra": ex_compra,
                        "ex_venta": ex_venta,
                        "precio_compra": precio_compra,
                        "precio_venta": precio_venta,
                        **margen,
                    }
                )
    return sorted(oportunidades, key=lambda op: float(op["margen_neto_pct"]), reverse=True)
