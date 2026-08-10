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
    version_supuestos: str  # Version identificable de los supuestos de persistencia.
    demoras_minutos: tuple[int, ...]  # Intervalos de medicion temporal en minutos.
    brecha_minima_registro_pct: float  # Brecha bruta minima para abrir una observacion.
    persistencia_csv: str  # Ruta del CSV exclusivo del tracker temporal.
    historial_persistencia_max: int  # Maximo de mediciones retenidas en RAM.

    @property
    def gas_fee_usdt(self) -> float:
        """Costo fijo estimado de transferir USDT por la red configurada."""
        return GAS_FEE_POR_RED[self.red_usada]

    @property
    def perfiles(self) -> dict[str, dict[str, float | str]]:
        """Perfiles de friccion aplicables sin duplicar el capital simulado."""
        return crear_perfiles(self)


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


def _demoras_env() -> tuple[int, ...]:
    """Lee intervalos separados por coma y rechaza configuraciones ambiguas."""
    texto = os.getenv("DEMORAS_MINUTOS", "1,3,5,10,15,30")
    try:
        demoras = tuple(int(valor.strip()) for valor in texto.split(","))
    except ValueError as exc:
        raise ConfigError("DEMORAS_MINUTOS debe contener enteros separados por coma") from exc
    if not demoras or any(demora <= 0 for demora in demoras):
        raise ConfigError("DEMORAS_MINUTOS debe contener enteros positivos")
    if len(set(demoras)) != len(demoras):
        raise ConfigError("DEMORAS_MINUTOS no puede contener valores repetidos")
    if tuple(sorted(demoras)) != demoras:
        raise ConfigError("DEMORAS_MINUTOS debe estar ordenado de menor a mayor")
    return demoras


def crear_perfiles(cfg: Config) -> dict[str, dict[str, float | str]]:
    """Construye perfiles de costos, manteniendo el capital en ``cfg``."""
    return {
        "teorico": {
            "nombre": "teorico",
            "comision_origen": 0.0,
            "comision_destino": 0.0,
            "gas_fee_usdt": 0.0,
            "imp_cheque_deb": 0.0,
            "imp_cheque_cred": 0.0,
            "iibb_entrada": 0.0,
            "iibb_salida": 0.0,
            "estado": "hipotesis_sin_friccion",
        },
        "estimado": {
            "nombre": "estimado",
            "comision_origen": cfg.comision_compra,
            "comision_destino": cfg.comision_venta,
            "gas_fee_usdt": cfg.gas_fee_usdt,
            "imp_cheque_deb": 0.0,
            "imp_cheque_cred": 0.0,
            "iibb_entrada": 0.0,
            "iibb_salida": 0.0,
            "estado": "estimado_plataforma",
        },
        "conservador": {
            "nombre": "conservador",
            "comision_origen": cfg.comision_compra,
            "comision_destino": cfg.comision_venta,
            "gas_fee_usdt": cfg.gas_fee_usdt,
            "imp_cheque_deb": cfg.imp_cheque_debito,
            "imp_cheque_cred": cfg.imp_cheque_credito,
            "iibb_entrada": cfg.iibb_entrada,
            "iibb_salida": cfg.iibb_salida,
            "estado": "hipotesis_conservadora",
        },
    }


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
    if cfg.brecha_minima_registro_pct < 0:
        raise ConfigError("BRECHA_MINIMA_REGISTRO_PCT no puede ser negativa")
    if cfg.historial_persistencia_max <= 0:
        raise ConfigError("HISTORIAL_PERSISTENCIA_MAX debe ser mayor que cero")


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
        version_supuestos=os.getenv("VERSION_SUPUESTOS", "2026.1-persistencia"),
        demoras_minutos=_demoras_env(),
        brecha_minima_registro_pct=_float_env("BRECHA_MINIMA_REGISTRO_PCT", 0.5),
        persistencia_csv=os.getenv("PERSISTENCIA_CSV", "persistencia_log.csv"),
        historial_persistencia_max=_int_env("HISTORIAL_PERSISTENCIA_MAX", 2_000),
    )
    _validar(cfg)
    return cfg


# Se valida al importar para fallar temprano antes de iniciar el monitoreo.
CONFIG: Final[Config] = cargar_configuracion()

# Alias explicitos para configuracion y tests; los perfiles se resuelven con la
# red validada al importar, sin fallbacks silenciosos.
VERSION_SUPUESTOS: Final[str] = CONFIG.version_supuestos
DEMORAS_MINUTOS: Final[tuple[int, ...]] = CONFIG.demoras_minutos
BRECHA_MINIMA_REGISTRO_PCT: Final[float] = CONFIG.brecha_minima_registro_pct
PERFILES: Final[dict[str, dict[str, float | str]]] = crear_perfiles(CONFIG)
PERFIL_TEORICO: Final[dict[str, float | str]] = PERFILES["teorico"]
PERFIL_ESTIMADO: Final[dict[str, float | str]] = PERFILES["estimado"]
PERFIL_CONSERVADOR: Final[dict[str, float | str]] = PERFILES["conservador"]
