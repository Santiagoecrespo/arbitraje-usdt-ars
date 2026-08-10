# Monitor de arbitraje USDT/ARS (paper trading)

## Que es

Un MVP de observacion para contrastar precios publicos de USDT/ARS entre exchanges argentinos mediante la API de CriptoYa. Simula una vuelta de compra, transferencia y venta, aplicando los costos configurados, y guarda las tres mejores combinaciones de cada ciclo en CSV. Sirve para evaluar datos historicos antes de considerar una operacion real.

## Que no hace

No ejecuta ordenes, no mueve fondos, no solicita ni almacena credenciales, y no se conecta a cuentas de exchanges. Es una herramienta de lectura y calculo. Los precios de pantalla no garantizan liquidez, limites, disponibilidad de retiros o ejecucion al precio indicado. Verifica comisiones e impuestos con fuentes profesionales antes de usar capital real.

## Instalacion

Requiere Python 3.10 o posterior.

```powershell
cd arbitraje
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` si queres cambiar los supuestos. No hay secretos que configurar.

## Configuracion

| Parametro | Tipo | Default | Descripcion |
| --- | --- | ---: | --- |
| `CAPITAL_ARS` | decimal | 1000000 | Capital simulado en pesos argentinos. |
| `RED_USADA` | texto | `polygon` | `polygon`, `trc20` o `bsc`; determina el gas fijo. |
| `COMISION_COMPRA` | proporcion | 0.0035 | Comision al comprar USDT. |
| `COMISION_VENTA` | proporcion | 0.0035 | Comision al vender USDT. |
| `IMP_CHEQUE_DEBITO` | proporcion | 0.006 | Retencion al debitar ARS. |
| `IMP_CHEQUE_CREDITO` | proporcion | 0.006 | Retencion al acreditar ARS. |
| `IIBB_ENTRADA` | proporcion | 0.015 | IIBB previo a la compra. |
| `IIBB_SALIDA` | proporcion | 0.000 | IIBB posterior a la venta. |
| `MARGEN_MINIMO_PCT` | decimal | 0.3 | Margen neto minimo para marcar `VERDE`. |
| `INTERVALO_SEG` | entero | 2 | Pausa entre consultas. |
| `CSV_SALIDA` | ruta | `arbitraje_log.csv` | Archivo de resultados. |
| `LOG_ERRORES` | ruta | `errores.log` | Archivo de errores en UTC. |

Las proporciones se expresan como fraccion: `0.0035` significa `0.35%`.

## Ejecucion

```powershell
py main.py
```

El programa consulta `https://criptoya.com/api/usdt/ars/{volumen_usdt}` cada dos segundos. Calcula el volumen solicitado de forma dinamica y se detiene limpiamente con `Ctrl+C`.

## Tests

```powershell
py -m pytest tests/ -v
```

Las pruebas son unitarias: no realizan peticiones de red ni escriben archivos externos.

## Formula fiscal

Para cada par compra/venta, el calculador aplica el orden cronologico siguiente:

1. `pesos_reales = capital * (1 - impuesto_debito - iibb_entrada)`
2. `usdt_brutos = pesos_reales / precio_compra`
3. `usdt_post_comision = usdt_brutos * (1 - comision_compra)`
4. `usdt_transferidos = usdt_post_comision - gas_de_red`
5. `usdt_a_vender = usdt_transferidos * (1 - comision_venta)`
6. `pesos_acreditados = usdt_a_vender * precio_venta`
7. `pesos_netos = pesos_acreditados * (1 - impuesto_credito - iibb_salida)`
8. `ganancia = pesos_netos - capital`
9. `margen_neto = ganancia / capital * 100`

Ejemplo ilustrativo con los defaults, compra a $1.300 y venta a $1.400 por USDT: $1.000.000 se convierten en $979.000 tras retenciones, luego en 753,08 USDT; despues de comisiones y gas quedan 747,52 USDT para vender. El resultado neto es aproximadamente $1.040.243, una ganancia estimada de $40.243 (4,02%).

## Columnas del CSV

| Columna | Significado |
| --- | --- |
| `cycle_id` / `timestamp_utc` | Identificador y momento UTC del ciclo. |
| `duracion_calculo_ms` | Duracion de la consulta y calculo del ciclo. |
| `ex_compra` / `ex_venta` | Exchange considerado para cada extremo de la simulacion. |
| `precio_compra` / `precio_venta` | Ask y bid usados en ARS por USDT. |
| `red` / `gas_fee_usdt` | Red y costo fijo de transferencia asumido. |
| `brecha_bruta_pct` | Diferencia de precio antes de costos. |
| `margen_neto_pct` / `ganancia_ars` | Resultado despues de comisiones, gas e impuestos configurados. |
| `carga_fiscal_ars` | Estimacion de impuestos incluidos en el modelo. |

## Como interpretar resultados

Si el CSV muestra margenes `VERDE` repetidos durante distintos horarios y exchanges, revisa manualmente profundidad del libro, limites, retiros habilitados, demoras de transferencia y las tasas reales de cada cuenta. Si permanece `ROJO`, los costos del modelo ya absorben la brecha disponible: no es una senal para operar. En ambos casos, ajusta `.env` para que represente tus costos reales y trata los resultados como una simulacion, no como una recomendacion financiera.
