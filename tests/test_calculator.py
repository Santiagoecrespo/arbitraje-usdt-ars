"""Pruebas unitarias sin red para la logica de margenes."""

from dataclasses import replace

import pytest

from calculator import analizar_matriz, calcular_margen
from config import CONFIG


@pytest.fixture
def cfg():
    return CONFIG


def test_margen_negativo_sin_brecha(cfg):
    resultado = calcular_margen(1_300, 1_300, cfg)
    assert resultado is not None
    assert resultado["margen_neto_pct"] < 0


def test_margen_positivo_con_brecha_grande(cfg):
    resultado = calcular_margen(1_300, 1_430, cfg)
    assert resultado is not None
    assert resultado["margen_neto_pct"] > 0


def test_retorna_none_si_gas_destruye_capital(cfg):
    cfg_minimo = replace(cfg, capital_ars=100)
    assert calcular_margen(1_300, 1_500, cfg_minimo) is None


def test_break_even(cfg):
    precio_compra = 1_300
    pesos_reales = cfg.capital_ars * (1 - cfg.imp_cheque_debito - cfg.iibb_entrada)
    usdt_antes_venta = (
        pesos_reales / precio_compra * (1 - cfg.comision_compra) - cfg.gas_fee_usdt
    ) * (1 - cfg.comision_venta)
    precio_equilibrio = cfg.capital_ars / (
        usdt_antes_venta * (1 - cfg.imp_cheque_credito - cfg.iibb_salida)
    )
    resultado = calcular_margen(precio_compra, precio_equilibrio, cfg)
    assert resultado is not None
    assert resultado["margen_neto_pct"] == pytest.approx(0, abs=0.01)


def test_precio_cero_retorna_none(cfg):
    assert calcular_margen(0, 1_300, cfg) is None


def test_precio_negativo_retorna_none(cfg):
    assert calcular_margen(-500, 1_300, cfg) is None


def test_desglose_contiene_todas_las_claves(cfg):
    resultado = calcular_margen(1_300, 1_400, cfg)
    assert resultado is not None
    assert set(resultado) == {
        "pesos_reales",
        "usdt_brutos",
        "usdt_post_comision",
        "usdt_transferidos",
        "usdt_a_vender",
        "pesos_acreditados",
        "pesos_netos",
        "ganancia_ars",
        "margen_neto_pct",
        "brecha_bruta_pct",
        "carga_fiscal_ars",
        "gas_fee_usdt",
        "red",
    }


def test_analizar_matriz_excluye_mismo_exchange(cfg):
    datos = {
        "lemon": {"totalAsk": 1_300, "totalBid": 1_290},
        "belo": {"totalAsk": 1_310, "totalBid": 1_400},
    }
    resultados = analizar_matriz(datos, cfg)
    assert resultados
    assert all(op["ex_compra"] != op["ex_venta"] for op in resultados)


def test_analizar_matriz_ordenado_por_margen(cfg):
    datos = {
        "lemon": {"totalAsk": 1_300, "totalBid": 1_300},
        "belo": {"totalAsk": 1_320, "totalBid": 1_380},
        "fiwind": {"totalAsk": 1_340, "totalBid": 1_450},
    }
    resultados = analizar_matriz(datos, cfg)
    margenes = [op["margen_neto_pct"] for op in resultados]
    assert margenes == sorted(margenes, reverse=True)


def test_calculo_legacy_regresion(cfg):
    """La llamada historica de tres argumentos conserva su resultado exacto."""
    resultado = calcular_margen(1_300, 1_400, cfg)
    assert resultado is not None
    esperados = {
        "pesos_reales": 979000.0,
        "usdt_brutos": 753.0769230769231,
        "usdt_post_comision": 750.441153846154,
        "usdt_transferidos": 750.141153846154,
        "usdt_a_vender": 747.5156598076925,
        "pesos_acreditados": 1046521.9237307694,
        "pesos_netos": 1040242.7921883848,
        "ganancia_ars": 40242.7921883848,
        "margen_neto_pct": 4.02427921883848,
        "brecha_bruta_pct": 7.6923076923076925,
        "carga_fiscal_ars": 27279.131542384614,
        "gas_fee_usdt": 0.3,
    }
    for clave, esperado in esperados.items():
        assert resultado[clave] == pytest.approx(esperado)
    assert resultado["red"] == "polygon"


def test_perfil_keyword_only_aplica_costos_sin_alterar_legacy(cfg):
    legacy = calcular_margen(1_300, 1_400, cfg)
    teorico = calcular_margen(1_300, 1_400, cfg, perfil=cfg.perfiles["teorico"])
    assert legacy is not None and teorico is not None
    assert teorico["margen_neto_pct"] > legacy["margen_neto_pct"]
