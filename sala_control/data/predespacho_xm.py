"""
data/predespacho_xm.py — Capa de datos para "Matriz de Generación Horaria".

ACTUALIZACIÓN v3: se descarta SIMEM (pydatasimem tiene un bug conocido:
`CatalogSIMEM` object has no attribute '_filters'). En su lugar, se usa
la métrica "GeneIdea" (Generación Ideal por Recurso, Entity=Recurso,
horaria) del catálogo PRINCIPAL de pydataxm — la MISMA infraestructura
`ReadDB` que ya usamos y validamos para reservas (reservas_xm.py):
sin credenciales, sin el bug de SIMEM, con el mismo patrón de resolución
dinámica de métricas + chunking de 30 días.

Fila real confirmada por el usuario en el catálogo (api.inventario_metricas):
    GeneIdea | Generación Ideal por Recurso | Recurso | 31 | HourlyEntities
    | https://servapibi.xm.com.co/hourly | Codigo Submercado Generación | kWh

NO VALIDADO EN VIVO desde este entorno (sin salida de red hacia XM en este
sandbox). Corre test_8_gene_ideal.py en tu máquina — estilo diagnóstico,
igual que con reservas: primero confirma la forma real de las columnas
horarias antes de asumir nada (pueden llamarse Values_01..Values_24,
Values_Hour01..Values_Hour24, o algo distinto).

Unidad: kWh según el catálogo (reservas venía en %, esto viene en kWh —
NO en MWh como el archivo viejo de Predespacho Ideal). Si necesitas MWh
para que los números se vean como en tu gráfico original, divide entre
1000 — ya lo dejo hecho por defecto, documentado, fácil de quitar si
prefieres kWh crudo.

OTRAS VISTAS (confirmado en vivo contra api.inventario_metricas, misma
forma que GeneIdea — Entity=Recurso, HourlyEntities, kWh): además de
"GeneIdea", el catálogo trae "Gene" (Generación REAL, neta medida en
frontera — solo existe para horas ya transcurridas) y "GeneProgDesp"
(Generación Programada, despacho esperado con la red de transporte real).
Como comparten forma cruda, se puede reusar TODO el pipeline de abajo
(resolución dinámica + chunking + adaptar_a_formato_ancho) solo cambiando
la keyword de búsqueda — ver GENE_VISTAS.
"""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd

from sala_control.utils import normalize
from sala_control.data.reservas_xm import resolve_metric_id, _date_chunks
from sala_control.data._pydataxm_patch import aplicar_parche

aplicar_parche()  # corrige bug real de ReadDB.request_data (idempotente si reservas_xm.py ya lo aplicó)

GENE_IDEAL_KEYWORDS = ["generacion ideal", "recurso"]

# Las otras 2 vistas usan la frase completa como UNA sola keyword (no
# palabras sueltas) — necesario para que el matching por substring de
# resolve_metric_id() no confunda variantes parecidas: "generacion por
# recurso" NO debe matchear "generacion IDEAL por recurso", y "generacion
# programada por recurso" NO debe matchear la variante "...REDESPACHO...".
GENE_REAL_KEYWORDS = ["generacion por recurso"]
GENE_PROGRAMADA_KEYWORDS = ["generacion programada por recurso"]

# Vistas disponibles para el selector de la UI — "Ideal" primero porque es
# el default ya validado en todo el pipeline (KPIs, clasificación, etc.).
GENE_VISTAS = {
    "Ideal": GENE_IDEAL_KEYWORDS,
    "Real": GENE_REAL_KEYWORDS,
    "Programada": GENE_PROGRAMADA_KEYWORDS,
}

MAX_DAYS_PER_CALL = 30  # misma restricción documentada de la API XM

HOUR_COLS = [f"H{i}" for i in range(1, 25)]


# ---------------------------------------------------------------------------
# Descarga cruda (reutiliza resolve_metric_id de reservas_xm.py — misma
# lógica de "nunca hardcodear el MetricId")
# ---------------------------------------------------------------------------
def fetch_generacion_raw(fecha_inicio: dt.date, fecha_fin: dt.date, keywords: list[str],
                          api=None, filtros: list[str] | None = None) -> pd.DataFrame:
    """Trae el DataFrame CRUDO de CUALQUIER métrica de generación 'por
    Recurso' (Ideal, Real, Programada — ver GENE_VISTAS) entre las dos
    fechas, troceando en ventanas de 30 días. Generalización de lo que
    antes era `fetch_generacion_ideal_raw()`: misma resolución dinámica de
    MetricId, mismo chunking — la única diferencia entre las 3 métricas es
    la keyword de búsqueda (confirmado que comparten forma cruda: Entity=
    Recurso, HourlyEntities, kWh).

    `filtros`: lista opcional de códigos de recurso (ej. ["GVIO","TBST"]).
    Algunas métricas 'por Recurso' de XM devuelven vacío sin un filtro
    explícito en vez de interpretar 'sin filtro' como 'todos los recursos'
    — si la consulta sin filtro viene vacía, prueba con un filtro conocido
    para confirmar si ese es el problema."""
    if api is None:
        from pydataxm.pydataxm import ReadDB
        api = ReadDB()

    metric_id = resolve_metric_id(api, keywords, entity="Recurso")

    frames = []
    for c_start, c_end in _date_chunks(fecha_inicio, fecha_fin, MAX_DAYS_PER_CALL):
        df = api.request_data(metric_id, "Recurso", c_start, c_end, filtros=filtros)
        if df is not None and len(df):
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def fetch_generacion_ideal_raw(fecha_inicio: dt.date, fecha_fin: dt.date, api=None,
                                filtros: list[str] | None = None) -> pd.DataFrame:
    """Caso específico de `fetch_generacion_raw()` para GeneIdea — se
    mantiene con este nombre y firma para no romper los scripts de prueba
    (test_8_gene_ideal.py, test_9_listado_recursos.py) que ya la importan
    así."""
    return fetch_generacion_raw(fecha_inicio, fecha_fin, GENE_IDEAL_KEYWORDS, api=api, filtros=filtros)


def adaptar_a_formato_ancho(df_crudo: pd.DataFrame, fecha_filtro: dt.date | None = None,
                             convertir_a_mwh: bool = True) -> pd.DataFrame:
    """Convierte la salida cruda de GeneIdea al formato ANCHO (Planta,
    H1..H24) que ya usan analytics/generacion_mix.py y charts/generacion_chart.py.

    OJO: GeneIdea NO trae el nombre descriptivo del recurso, solo su
    CÓDIGO corto (columna real confirmada: 'Values_code', ej. '2QBW') — la
    columna resultante se sigue llamando 'Planta' por compatibilidad con
    el resto del pipeline, pero contiene el CÓDIGO, no un nombre legible.
    `enriquecer_con_recursos()` cruza por código contra el listado de
    recursos y trae de vuelta el nombre legible como 'NombrePlanta'.

    Autodetecta:
      - la columna de identificador del recurso (Values_code / Values_Name
        / Name / Recurso / Planta — lo que exista primero, en ese orden)
      - las 24 columnas horarias, sin asumir un patrón fijo de nombre
        (Values_01..Values_24, Values_Hour01..Values_Hour24, HourXX, etc.)
        — busca cualquier columna cuyo nombre termine en un número de 1-2
        cifras entre 1 y 24, y exige encontrar EXACTAMENTE 24.

    Si no encuentra exactamente 24, lanza error con las columnas reales
    para que ajustes a mano — igual que hicimos con NOAA y SIMEM.
    """
    df = df_crudo.copy()
    if len(df) == 0:
        return pd.DataFrame(columns=["Planta"] + HOUR_COLS)

    date_col = next((c for c in df.columns if normalize(c) == "date"), None)
    if date_col and fecha_filtro is not None:
        df = df[pd.to_datetime(df[date_col]).dt.date == fecha_filtro]

    name_col = next(
        (c for c in df.columns
         if normalize(c) in ("values_code", "values_name", "name", "recurso", "planta")),
        None,
    )
    if name_col is None:
        raise RuntimeError(
            f"No se pudo detectar la columna identificadora del recurso. "
            f"Columnas disponibles: {df.columns.tolist()}"
        )

    hour_col_candidates = []
    for c in df.columns:
        m = re.search(r"(\d{1,2})$", c)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 24 and c != name_col:
                hour_col_candidates.append((n, c))


    if len(hour_col_candidates) != 24:
        raise RuntimeError(
            f"Se esperaban 24 columnas horarias, se detectaron {len(hour_col_candidates)}. "
            f"Columnas disponibles: {df.columns.tolist()}. Ajusta la autodetección en "
            f"adaptar_a_formato_ancho() con los nombres reales."
        )

    hour_col_candidates.sort(key=lambda t: t[0])
    ordered_cols = [c for _, c in hour_col_candidates]

    out = df[[name_col] + ordered_cols].copy()
    out.columns = ["Planta"] + HOUR_COLS
    for c in HOUR_COLS:
        out[c] = pd.to_numeric(out[c], errors="coerce")
        if convertir_a_mwh:
            out[c] = out[c] / 1000.0  # kWh -> MWh
    return out.groupby("Planta", as_index=False)[HOUR_COLS].sum()


# ---------------------------------------------------------------------------
# Listado de AGENTES (nombre completo de la empresa, no solo el código) —
# tipo 'ListsEntities' igual que ListadoRecursos.
# ---------------------------------------------------------------------------
LISTADO_AGENTES_KEYWORDS = ["listado", "agentes"]


def fetch_listado_agentes(api=None) -> pd.DataFrame:
    """Trae el listado estático de agentes del mercado (código -> nombre
    completo de la empresa). NO VALIDADO EN VIVO — la entity/keywords
    exactas no están confirmadas contra el catálogo real. Corre
    test_10_listado_agentes.py para confirmar/ajustar."""
    if api is None:
        from pydataxm.pydataxm import ReadDB
        api = ReadDB()

    metric_id = resolve_metric_id(api, LISTADO_AGENTES_KEYWORDS, entity="Sistema")
    hoy = dt.date.today()
    return api.request_data(metric_id, "Sistema", hoy, hoy)


def nombres_de_agentes(listado_agentes: pd.DataFrame) -> pd.DataFrame:
    """Reduce el listado de agentes a [CodigoAgente, NombreAgente],
    autodetectando las columnas (no confirmado en vivo). Si falla, lanza
    error con las columnas reales disponibles para ajustar a mano."""
    code_col = next(
        (c for c in listado_agentes.columns
         if normalize(c) in ("values_code", "values_companycode", "code")),
        None,
    )
    name_col = next(
        (c for c in listado_agentes.columns
         if normalize(c) in ("values_name", "values_companyname", "name")),
        None,
    )
    if code_col is None or name_col is None:
        raise RuntimeError(
            f"No se pudo detectar columnas de código/nombre en el listado de agentes. "
            f"Columnas disponibles: {listado_agentes.columns.tolist()}"
        )
    out = listado_agentes[[code_col, name_col]].rename(
        columns={code_col: "CodigoAgente", name_col: "NombreAgente"}
    ).drop_duplicates(subset="CodigoAgente")
    out["CodigoAgente"] = out["CodigoAgente"].astype(str).str.strip().str.upper()
    return out


def parse_predespacho_file(source) -> pd.DataFrame:
    """Respaldo manual: parsea un archivo local en el formato viejo
    (sin encabezado, Planta + H1..H24), por si la API falla para alguna
    fecha específica o quieres comparar contra un archivo ya descargado."""
    df = pd.read_csv(source, header=None)
    df.columns = ["Planta"] + HOUR_COLS
    for c in HOUR_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=HOUR_COLS, how="all").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Listado de recursos (metadatos estáticos: Agente Generador, Tipo oficial,
# Capacidad Efectiva Neta, etc.) — tipo 'ListsEntities' en el catálogo de
# pydataxm, no es una serie de tiempo, así que las fechas no importan.
# ---------------------------------------------------------------------------
LISTADO_RECURSOS_KEYWORDS = ["listado", "recursos"]


def fetch_listado_recursos(api=None) -> pd.DataFrame:
    """Trae el listado estático de recursos de generación con sus
    atributos (Agente Generador, Tipo, Capacidad Efectiva Neta, etc.).
    Es tipo 'ListsEntities' — no es serie de tiempo, así que cualquier
    fecha sirve como placeholder. Entity=Sistema (confirmado contra el
    catálogo real — no Entity=Recurso como asumí al principio)."""
    if api is None:
        from pydataxm.pydataxm import ReadDB
        api = ReadDB()

    metric_id = resolve_metric_id(api, LISTADO_RECURSOS_KEYWORDS, entity="Sistema")
    hoy = dt.date.today()
    return api.request_data(metric_id, "Sistema", hoy, hoy)


def enriquecer_con_recursos(df_ancho: pd.DataFrame, listado_recursos: pd.DataFrame) -> pd.DataFrame:
    """Cruza el formato ancho (Planta = CÓDIGO del recurso, no nombre —
    ver adaptar_a_formato_ancho()) con el listado de recursos para agregar
    los atributos OFICIALES de XM:
        NombrePlanta   <- Values_Name (nombre legible, ej. 'EL POPAL')
        Agente         <- Values_CompanyCode (código del agente generador)
        TipoOficial    <- Values_Type (HIDRAULICA / TERMICA / ... )
        RecTypeOficial <- Values_RecType (NORMAL / FILO DE AGUA /
                          GEN. DISTRIBUIDA / AUTOGENERADOR)
        FuenteOficial  <- Values_EnerSource (AGUA / CARBON / BIOGAS / ...)

    Columnas reales confirmadas contra el catálogo en vivo:
      - ListadoRecursos: ['Id', 'Values_Code', 'Values_Name', 'Values_Type',
        'Values_Disp', 'Values_RecType', 'Values_CompanyCode',
        'Values_EnerSource', 'Values_OperStartdate', 'Values_State', 'Date']
      - GeneIdea (crudo): trae 'Values_code' (minúscula, SIN nombre) — por
        eso el cruce es por CÓDIGO, no por nombre (confirmado que GeneIdea
        no incluye el nombre descriptivo del recurso)."""
    listado = listado_recursos.copy()
    listado["_join_key"] = listado["Values_Code"].astype(str).str.strip().str.upper()
    listado_reducido = listado[[
        "_join_key", "Values_Name", "Values_CompanyCode", "Values_Type",
        "Values_RecType", "Values_EnerSource",
    ]].rename(columns={
        "Values_Name": "NombrePlanta",
        "Values_CompanyCode": "Agente",
        "Values_Type": "TipoOficial",
        "Values_RecType": "RecTypeOficial",
        "Values_EnerSource": "FuenteOficial",
    }).drop_duplicates(subset="_join_key")

    out = df_ancho.copy()
    out["_join_key"] = out["Planta"].astype(str).str.strip().str.upper()
    out = out.merge(listado_reducido, on="_join_key", how="left").drop(columns="_join_key")
    return out
