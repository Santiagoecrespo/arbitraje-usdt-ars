"""Configuracion centralizada para el monitor de arbitraje en paper trading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv


GAS_FEE_POR_RED: Final[dict[str, float]] = {
    "trc20": 2.0,
    "polygon": 0.3,
    "bsc": 0.2,
}
EXCHANGES_OBJETIVO: Final[tuple[str, ...]] = (
    "lemon",
    "belo",
    "fiwind",
    "ripio",
    "buenbit",
    "satoshitango",
    "tiendacrypto",
    "cryptomkt",
)


class ConfigError(ValueError):
    """Indica una variable de configuracion ausente o invalida."""


@dataclass(frozen=True)
class Config:
    """Parametros del simulador; todos son importes o proporciones configurables."""

    capital_ars: float  # Capital simulado en ARS; debe ser mayor que cero.
    red_usada: str  # Red de transferencia: polygon, trc20 o bsc.
    comision_compra: float  # Comision proporcional cobrada al comprar USDT.
    comision_venta: float  # Comision proporcional cobrada al vender USDT.
    imp_cheque_debito: float  # Impuesto al cheque aplicado al ingreso de ARS.
    imp_cheque_credito: float  # Impuesto al cheque aplicado al egreso de ARS.
    iibb_entrada: float  # IIBB aplicado antes de comprar USDT.
    iibb_salida: float  # IIBB aplicado al acreditar la venta.
    margen_minimo_pct: float  # Umbral porcentual para marcar una oportunidad verde.
    intervalo_seg: int  # Segundos de espera entre consultas a la API.
    csv_salida: str  # Ruta del CSV con las mejores oportunidades por ciclo.
    log_errores: str  # Ruta del log de errores con timestamp UTC.

    @property
    def gas_fee_usdt(self) -> float:
        """Costo fijo estimado de transferir USDT por la red configurada."""
        return GAS_FEE_POR_RED[self.red_usada]


def _float_env(nombre: str, default: float) -> float:
    try:
        return float(os.getenv(nombre, str(default)))
    except ValueError as exc:
        raise ConfigError(f"{nombre} debe ser un numero valido") from exc


def _int_env(nombre: str, default: int) -> int:
    try:
        return int(os.getenv(nombre, str(default)))
    except ValueError as exc:
        raise ConfigError(f"{nombre} debe ser un entero valido") from exc


def _validar(cfg: Config) -> None:
    if cfg.capital_ars <= 0:
        raise ConfigError("CAPITAL_ARS debe ser mayor que cero")
    if cfg.red_usada not in GAS_FEE_POR_RED:
        opciones = ", ".join(GAS_FEE_POR_RED)
        raise ConfigError(f"RED_USADA invalida: {cfg.red_usada!r}. Opciones: {opciones}")
    costos = {
        "COMISION_COMPRA": cfg.comision_compra,
        "COMISION_VENTA": cfg.comision_venta,
        "IMP_CHEQUE_DEBITO": cfg.imp_cheque_debito,
        "IMP_CHEQUE_CREDITO": cfg.imp_cheque_credito,
        "IIBB_ENTRADA": cfg.iibb_entrada,
        "IIBB_SALIDA": cfg.iibb_salida,
    }
    for nombre, valor in costos.items():
        if valor < 0:
            raise ConfigError(f"{nombre} no puede ser negativo")
        if valor >= 1:
            raise ConfigError(f"{nombre} debe ser una proporcion menor que 1")
    if cfg.intervalo_seg <= 0:
        raise ConfigError("INTERVALO_SEG debe ser mayor que cero")


def cargar_configuracion() -> Config:
    """Carga ``.env`` junto a este modulo, aplica defaults y valida los valores."""
    load_dotenv(Path(__file__).with_name(".env"))
    cfg = Config(
        capital_ars=_float_env("CAPITAL_ARS", 1_000_000),
        red_usada=os.getenv("RED_USADA", "polygon").strip().lower(),
        comision_compra=_float_env("COMISION_COMPRA", 0.0035),
        comision_venta=_float_env("COMISION_VENTA", 0.0035),
        imp_cheque_debito=_float_env("IMP_CHEQUE_DEBITO", 0.006),
        imp_cheque_credito=_float_env("IMP_CHEQUE_CREDITO", 0.006),
        iibb_entrada=_float_env("IIBB_ENTRADA", 0.015),
        iibb_salida=_float_env("IIBB_SALIDA", 0.0),
        margen_minimo_pct=_float_env("MARGEN_MINIMO_PCT", 0.3),
        intervalo_seg=_int_env("INTERVALO_SEG", 5),
        csv_salida=os.getenv("CSV_SALIDA", "arbitraje_log.csv"),
        log_errores=os.getenv("LOG_ERRORES", "errores.log"),
    )
    _validar(cfg)
    return cfg


# Se valida al importar para fallar temprano antes de iniciar el monitoreo.
CONFIG: Final[Config] = cargar_configuracion()
