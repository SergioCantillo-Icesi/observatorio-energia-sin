"""
data/_pydataxm_patch.py — Parche quirúrgico a DOS bugs reales de la
librería `pydataxm` (ninguno relacionado con versiones de NumPy/pandas
específicas, aunque el primer síntoma se vea así).

BUG 1 — mutación de un Index inmutable: en `ReadDB.request_data()`, la
librería construye `start_periods` como un `pandas.DatetimeIndex`
(resultado de `.map()` sobre otro Index) y luego intenta mutar su array
interno directamente:

    start_periods.values[0] = pd.Timestamp(start_date)

Los objetos `Index` de pandas son inmutables por diseño — `.values` puede
devolver una vista de solo lectura de su array interno. Mutarla en el
sitio nunca fue realmente seguro; simplemente pandas se ha vuelto más
estricto verificándolo. Por eso NI actualizar pydataxm NI bajar NumPy
arregla esto — el problema es de lógica, no de versión.
FIX: se construye un array de NumPy escribible (`.copy()`) antes de mutar
el primer elemento, y se reconstruye el Index a partir de ese array.

BUG 2 — nest_asyncio pisa el event loop del servidor: pydataxm hace
`loop = asyncio.get_event_loop(); loop.run_until_complete(...)` (con
nest_asyncio parchando el loop para permitir anidarlo). Funciona en un
script/notebook local, pero confirmado roto en Streamlit Community Cloud
(servidor ASGI/Uvicorn, que YA tiene un loop corriendo): pisa el
seguimiento interno de tasks que usa aiohttp y tira `RuntimeError: Timeout
context manager should be used inside a task`.
FIX: `_run_coro_aislado()` corre esa misma llamada en un hilo nuevo con su
propio event loop (`asyncio.run()`), sin tocar ni depender del loop del
servidor — ver su docstring para más detalle.

PARCHE: se reemplaza `ReadDB.request_data` completo por una copia idéntica
del original (confirmado contra el código fuente real en
https://raw.githubusercontent.com/EquipoAnaliticaXM/API_XM/master/pydataxm/pydataxm.py)
con SOLO esas dos partes corregidas.

USO: importar y llamar `aplicar_parche()` UNA VEZ, antes de crear
cualquier instancia de `ReadDB()` — tanto en reservas_xm.py como en
predespacho_xm.py ya lo hacen automáticamente al importar sus funciones
de fetch, así que normalmente no necesitas llamarlo a mano.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading

import pandas as pd
import requests

_PARCHE_APLICADO = False


def _run_coro_aislado(coro):
    """Corre una corutina en un HILO NUEVO con su propio event loop
    aislado (vía asyncio.run()), en vez de reusar `asyncio.get_event_loop()`
    + nest_asyncio (lo que hacía pydataxm originalmente).

    Por qué hace falta: en un script/notebook local no hay drama en
    reusar/anidar el loop "actual". Pero quien llama a este código desde
    un servidor ASGI (como el que usa Streamlit, Uvicorn por debajo) YA
    tiene un event loop corriendo, y nest_asyncio pisa su seguimiento
    interno de tasks — confirmado en Streamlit Community Cloud:
    `RuntimeError: Timeout context manager should be used inside a task`
    dentro de aiohttp, al anidar el loop así.

    OJO con `concurrent.futures.ThreadPoolExecutor`: su `.submit()` copia
    el `contextvars.Context` del hilo que llama (vía `copy_context()`) y
    lo "entra" en el hilo nuevo — pero en el runtime de Streamlit ese
    contexto YA está entrado (el propio `anyio` corre el script ahí
    dentro), así que entrar una copia desde otro hilo choca: confirmado
    en vivo `RuntimeError: cannot enter context: ... is already entered`,
    con una cascada de errores de bookkeeping interno de asyncio detrás.
    `threading.Thread` NO copia/hereda contexto del hilo llamador (el
    hilo nuevo arranca con uno propio, vacío) — por eso se usa acá en vez
    de ThreadPoolExecutor, para no repetir el mismo problema por otro
    lado."""
    result: queue.Queue = queue.Queue(maxsize=1)

    def _worker() -> None:
        try:
            result.put(("ok", asyncio.run(coro)))
        except BaseException as exc:  # noqa: BLE001 — se re-lanza tal cual abajo
            result.put(("error", exc))

    hilo = threading.Thread(target=_worker, daemon=True)
    hilo.start()
    hilo.join()

    status, value = result.get()
    if status == "error":
        raise value
    return value


def _request_data_parcheado(self, coleccion, metrica, start_date, end_date, filtros=None):
    """Copia exacta de ReadDB.request_data original, con la única línea
    problemática corregida (ver docstring del módulo)."""
    if type(filtros) == list:
        self.filtros = filtros
    elif filtros is None:
        self.filtros = []
    else:
        print('Los filtros deben ingresarse como una lista de valores')
        self.filtros = list

    if coleccion not in self.inventario_metricas.MetricId.values:
        print('No existe la métrica {}'.format(coleccion))
        return pd.DataFrame()

    if metrica not in self.inventario_metricas.Entity.values:
        print('No existe la entidad {}'.format(metrica))
        return pd.DataFrame()

    end_periods = pd.date_range(start_date, end_date, freq='ME', inclusive='both')
    if not pd.Timestamp(end_date).is_month_end:
        end_periods = end_periods.append(pd.DatetimeIndex([end_date]))

    start_periods = end_periods.map(lambda x: x - pd.offsets.MonthBegin(1))

    # --- FIX: construir un array escribible ANTES de mutar el primer
    # elemento, en vez de mutar el array interno (de solo lectura) del Index ---
    if (not pd.Timestamp(start_date).is_month_start) or (start_date == end_date):
        arr = start_periods.to_numpy().copy()
        arr[0] = pd.Timestamp(start_date)
        start_periods = pd.DatetimeIndex(arr)
    # --- fin del fix ---

    list_periods = list(zip(start_periods.astype(str), end_periods.astype(str)))

    period_dict = {
        'HourlyEntities': {'period_base': 'hourly', 'delta': 30, 'endpoint': 'HourlyEntities'},
        'DailyEntities': {'period_base': 'daily', 'delta': 30, 'endpoint': 'DailyEntities'},
        'MonthlyEntities': {'period_base': 'monthly', 'delta': 732, 'endpoint': 'MonthlyEntities'},
        'AnnualEntities': {'period_base': 'annual', 'delta': 366, 'endpoint': 'AnnualEntities'}
    }

    entity_type = self.inventario_metricas.query(
        "MetricId == @coleccion and Entity == @metrica").Type.values[0]

    if entity_type in period_dict:
        period_base = period_dict[entity_type]['period_base']
        endpoint = period_dict[entity_type]['endpoint']
        self.url = f'https://servapibi.xm.com.co/{period_base}'

        body_request = {
            "MetricId": coleccion,
            "StartDate": None,
            "EndDate": None,
            'Entity': metrica,
            "Filter": self.filtros,
        }

        list_bodies = []
        for _start, _end in list_periods:
            temp_body = body_request.copy()
            temp_body['StartDate'] = _start
            temp_body['EndDate'] = _end
            list_bodies.append(temp_body)

        data = _run_coro_aislado(self.run_async(list_bodies, endpoint))

    elif self.inventario_metricas.query(
            "MetricId == @coleccion and Entity == @metrica").Type.values == 'ListsEntities':
        period_base = 'lists'
        self.url = f'https://servapibi.xm.com.co/{period_base}'
        self.request = {'MetricId': coleccion, 'Entity': metrica}
        self.connection = requests.post(self.url, json=self.request)
        data_json = json.loads(self.connection.content)
        data = pd.json_normalize(data_json['Items'], 'ListEntities', 'Date', sep='_')

    cols = data.columns
    for col in cols:
        if pd.api.types.is_integer(data[col]):
            data[col] = pd.to_numeric(data[col])
    if ('Date' or 'date') in cols:
        data['Date'] = pd.to_datetime(data['Date'], errors='coerce', format='%Y-%m-%d')

    return data


def aplicar_parche() -> None:
    """Reemplaza ReadDB.request_data con la versión parcheada. Seguro de
    llamar más de una vez (no vuelve a parchear si ya está aplicado)."""
    global _PARCHE_APLICADO
    if _PARCHE_APLICADO:
        return
    from pydataxm.pydataxm import ReadDB
    ReadDB.request_data = _request_data_parcheado
    _PARCHE_APLICADO = True
    print("[pydataxm_patch] Parche aplicado a ReadDB.request_data "
          "(bug de mutación de Index inmutable corregido).")
