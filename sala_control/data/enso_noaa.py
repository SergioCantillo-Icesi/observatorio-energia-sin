"""
data/enso_noaa.py — Capa de datos ENSO (NOAA CPC).

Fuente confirmada y machine-readable: RONI.ascii.txt (texto plano, sin JS ni
imágenes, histórico 1950-presente):
  https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt

CONFIRMADO EN VIVO (2026-08-20): la página "Official NOAA CPC ENSO Strength
Probabilities" (".../roni/strengths/") SÍ sirve una <table> HTML estática
normal, con los códigos de estación (JAS, ASO, ...) en <abbr> dentro de la
primera columna. La falla que llevó a sospechar "gráfico/JS/redirect" era en
realidad `pandas.read_html()` sin backend de parseo instalado (falta lxml) —
`parse_strength_html()` la enmascaraba como "tabla no encontrada" en vez de
avisar del problema de dependencia. Ver `requirements.txt` (lxml). Si el
fetch en vivo falla por otro motivo, el pipeline cae a un método de
persistencia estimado con datos reales (ver más abajo), nunca a números
inventados.

Convención de estaciones NOAA (letras solapadas de 3 meses, centradas en el
mes de la letra del medio): DJF, JFM, FMA, MAM, AMJ, MJJ, JJA, JAS, ASO,
SON, OND, NDJ. El campo "YR" del archivo corresponde siempre al año
calendario del MES CENTRAL de cada estación (verificado contra el archivo
real: NDJ 1950 = nov1950-dic1950-ene1951, YR=1950=año de "D", el mes
central).
"""
from __future__ import annotations

import datetime as dt
import re
from io import StringIO
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(".cache/enso")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
RONI_CACHE = CACHE_DIR / "roni_historico.parquet"
RONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt"

# Estación (3 letras) -> mes central (1-12)
SEASON_TO_MONTH = {
    "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
    "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
}
MONTH_TO_SEASON = {v: k for k, v in SEASON_TO_MONTH.items()}

# Umbrales estándar NOAA (aplicados sobre RONI, igual que se aplican sobre ONI)
def classify_category(anom: float) -> str:
    if anom >= 1.5:
        return "El Niño Fuerte"
    if anom >= 1.0:
        return "El Niño Moderado"
    if anom >= 0.5:
        return "El Niño Débil"
    if anom > -0.5:
        return "Neutral"
    if anom > -1.0:
        return "La Niña Débil"
    if anom > -1.5:
        return "La Niña Moderada"
    return "La Niña Fuerte"


def _parse_roni_text(text: str) -> pd.DataFrame:
    df = pd.read_csv(StringIO(text), sep=r"\s+", engine="python")
    df.columns = [c.strip().upper() for c in df.columns]
    df = df.rename(columns={"SEAS": "Season", "YR": "Year", "ANOM": "Anom"})
    df["Season"] = df["Season"].str.strip()
    df["Year"] = df["Year"].astype(int)
    df["Anom"] = pd.to_numeric(df["Anom"], errors="coerce")
    df["CenterMonth"] = df["Season"].map(SEASON_TO_MONTH)
    df = df.dropna(subset=["Anom", "CenterMonth"]).reset_index(drop=True)
    df["CenterMonth"] = df["CenterMonth"].astype(int)
    df["Category"] = df["Anom"].map(classify_category)
    return df.sort_values(["Year", "CenterMonth"]).reset_index(drop=True)


def fetch_roni_historical(force_refresh: bool = False) -> pd.DataFrame:
    """Descarga (o lee de caché) el histórico completo de RONI.
    El archivo se actualiza ~mensualmente (2º jueves, junto al ENSO
    Diagnostic Discussion), así que una caché de 1 día es más que suficiente
    y evita golpear el servidor de NOAA en cada corrida de Streamlit."""
    if not force_refresh and RONI_CACHE.exists():
        age_hours = (dt.datetime.now().timestamp() - RONI_CACHE.stat().st_mtime) / 3600
        if age_hours < 24:
            return pd.read_parquet(RONI_CACHE)

    import requests
    resp = requests.get(RONI_URL, timeout=30)
    resp.raise_for_status()
    df = _parse_roni_text(resp.text)
    df.to_parquet(RONI_CACHE, index=False)
    return df


def roni_value_for(roni_df: pd.DataFrame, year: int, month: int) -> float | None:
    """RONI del trimestre centrado en `month` de `year`. Devuelve None si esa
    estación aún no ha sido publicada (p. ej. mes futuro sin dato observado)."""
    season = MONTH_TO_SEASON[month]
    row = roni_df[(roni_df["Season"] == season) & (roni_df["Year"] == year)]
    return float(row["Anom"].iloc[0]) if len(row) else None


def latest_observed(roni_df: pd.DataFrame) -> pd.Series:
    """Última estación observada (la fila más reciente cronológicamente)."""
    return roni_df.sort_values(["Year", "CenterMonth"]).iloc[-1]


def estimate_persistence_forecast(roni_df: pd.DataFrame, n_seasons: int = 9) -> pd.DataFrame:
    """Fallback cuando no hay pronóstico oficial disponible: proyecta el
    RONI de las próximas `n_seasons` estaciones por persistencia amortiguada,
    usando la autocorrelación lag-1 REAL calculada sobre el histórico (no un
    número inventado) como factor de decaimiento hacia neutral (0.0).

    anom_{t+1} = anom_t * rho   (rho = autocorrelación lag-1 histórica)
    """
    ordered = roni_df.sort_values(["Year", "CenterMonth"]).reset_index(drop=True)
    rho = ordered["Anom"].autocorr(lag=1)
    rho = 0.0 if pd.isna(rho) else float(rho)

    last = latest_observed(ordered)
    rows = []
    val = float(last["Anom"])
    year, month = int(last["Year"]), int(last["CenterMonth"])
    for _ in range(n_seasons):
        month += 1
        if month > 12:
            month = 1
            year += 1
        val = val * rho
        rows.append({
            "Season": MONTH_TO_SEASON[month], "Year": year,
            "AnomEstimado": round(val, 2), "Category": classify_category(val),
            "Metodo": "persistencia_amortiguada (rho lag-1 histórico)",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tabla "Official NOAA CPC ENSO Strength Probabilities" (9 estaciones
# solapadas, distribución de probabilidad por bin de intensidad).
# Confirmado en https://cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/strengths/
# ---------------------------------------------------------------------------
STRENGTH_BIN_COLS = [
    "idx_le_m2.0", "idx_m2.0_m1.5", "idx_m1.5_m1.0", "idx_m1.0_m0.5",
    "idx_m0.5_0.5", "idx_0.5_1.0", "idx_1.0_1.5", "idx_1.5_2.0", "idx_ge_2.0",
]
# (low, high) en °C para cada bin, en el mismo orden que STRENGTH_BIN_COLS.
# Los dos extremos son abiertos (-inf / +inf); se usan solo para clasificar
# en qué bin cae un valor, NO para el ancho de densidad (ver density_at()).
STRENGTH_BIN_EDGES = [
    (float("-inf"), -2.0), (-2.0, -1.5), (-1.5, -1.0), (-1.0, -0.5),
    (-0.5, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, float("inf")),
]
# La tabla de NOAA muestra 9 estaciones solapadas, pero es una VENTANA
# RODANTE: se corre un mes cada vez que NOAA publica (confirmado en vivo —
# el 2026-08-20 empezaba en JAS y terminaba en MAM; el 2026-09-15 empieza
# en ASO y termina en AMJ, JAS ya quedó atrás). Por eso NO hay un set fijo
# de 9 códigos "esperados": lo único fijo es el universo completo de los
# 12 códigos posibles (ya está en SEASON_TO_MONTH) y que la tabla siempre
# trae 9 de esos 12, consecutivos, en orden cronológico.
N_SEASONS_IN_TABLE = 9
_SEASON_CODE_PATTERN = re.compile(r"\b(" + "|".join(SEASON_TO_MONTH) + r")\b")

SEED_STRENGTH_TABLE = Path(__file__).parent / "enso_strength_table_seed.csv"


def _validate_strength_table(df: pd.DataFrame) -> bool:
    """Chequeo estructural: N_SEASONS_IN_TABLE filas con códigos de estación
    válidos y distintos (sin exigir un set fijo — ver nota de la ventana
    rodante arriba), columnas de bin presentes, y cada fila debe sumar
    ~100. Si algo no cuadra, se rechaza la tabla en vez de usarla a medias
    (mejor caer al fallback que operar con datos parcialmente corruptos)."""
    if "season" not in df.columns:
        return False
    seasons = df["season"]
    if len(seasons) != N_SEASONS_IN_TABLE or seasons.nunique() != N_SEASONS_IN_TABLE:
        return False
    if not set(seasons).issubset(SEASON_TO_MONTH.keys()):
        return False
    if not all(c in df.columns for c in STRENGTH_BIN_COLS):
        return False
    sums = df[STRENGTH_BIN_COLS].sum(axis=1)
    return bool(((sums - 100).abs() <= 2).all())  # tolerancia de redondeo


def _extract_season_code(text: str) -> str | None:
    """Busca un código de estación (JAS, ASO, ...) DENTRO del texto como
    PALABRA COMPLETA (límites \\b), no una igualdad exacta ni un `in`
    ingenuo. Existe porque sitios accesibles a veces envuelven el código
    con texto adicional para lectores de pantalla (ej. 'Season: JAS' en vez
    de 'JAS' limpio) — pero un `in` sin límites de palabra tiene una trampa
    real: la palabra 'SEASON' misma contiene 'ASO' como substring
    (SE-ASO-N), así que 'Season: SON' se detectaría mal como 'ASO' sin
    límites de palabra. Confirmado con un test antes de este fix."""
    t = str(text).strip().upper()
    m = _SEASON_CODE_PATTERN.search(t)
    return m.group(1) if m else None


def parse_strength_html(html: str) -> pd.DataFrame | None:
    """Parsea CUALQUIER HTML (ya renderizado o estático) buscando una tabla
    cuya primera columna contenga las 9 etiquetas de estación. Compartido
    entre el fetch por requests (`fetch_strength_probabilities_live`) y el
    scraper con Playwright (`data/enso_scraper_playwright.py`) — así la
    lógica de parseo se puede probar con un HTML sintético sin necesitar
    red ni navegador."""
    try:
        tables = pd.read_html(StringIO(html))
    except ImportError as e:
        # Esto NO significa "la tabla no está en el HTML" — significa que
        # pandas.read_html no tiene backend de parseo instalado (lxml /
        # html5lib+bs4). Confirmado en la práctica: esto se enmascaraba
        # como "NOAA cambió la página" durante semanas, cuando en realidad
        # la tabla siempre estuvo ahí, servida como HTML estático normal.
        print(f"[enso_noaa] pandas.read_html no tiene backend de parseo HTML instalado "
              f"(falta lxml/html5lib) — instala 'lxml' (ver requirements.txt). Detalle: {e}")
        return None
    except ValueError:
        return None

    for t in tables:
        t = t.copy()
        t.columns = [str(c).strip().lower() for c in t.columns]
        first_col = t.columns[0]
        season_extracted = t[first_col].map(_extract_season_code)
        if season_extracted.notna().sum() < N_SEASONS_IN_TABLE:
            continue

        t = t.rename(columns={first_col: "season"})
        t["season"] = season_extracted
        t = t[t["season"].notna()].drop_duplicates(subset="season")

        data_cols = [c for c in t.columns if c != "season"][: len(STRENGTH_BIN_COLS)]
        if len(data_cols) < len(STRENGTH_BIN_COLS):
            continue
        t = t.rename(columns=dict(zip(data_cols, STRENGTH_BIN_COLS)))
        for c in STRENGTH_BIN_COLS:
            t[c] = pd.to_numeric(t[c], errors="coerce")

        # Sin reordenar por un set fijo: el orden de filas de la tabla YA es
        # el orden cronológico que NOAA publica (ventana rodante), así que
        # basta con reindexar tras el filtrado de arriba.
        t = t.reset_index(drop=True)

        if _validate_strength_table(t):
            return t
    return None


def fetch_strength_probabilities_live(url: str = "https://cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/strengths/"):
    """Intento de traer la tabla EN VIVO con `requests` + `pandas.read_html`.
    Esto SOLO funciona si el HTML estático (sin ejecutar JS) ya contiene la
    tabla — confirmado en vivo (2026-08-20) que SÍ es el caso para esta
    página: la tabla es HTML estático normal, no requiere JS. Se prueba
    primero por ser más rápido y liviano que Playwright; si algún día NOAA
    la vuelve a renderizar por JS, `data/enso_scraper_playwright.py` sigue
    ahí como camino de respaldo con un navegador real.
    """
    import requests
    for candidate in (url, url.rstrip("/") + ".php", url.replace("cpc.", "www.cpc.")):
        try:
            resp = requests.get(candidate, timeout=20)
            resp.raise_for_status()
        except Exception:
            continue
        result = parse_strength_html(resp.text)
        if result is not None:
            result["captured_on"] = dt.date.today().isoformat()
            result["fuente"] = "live_requests"
            return result
    return None


def load_strength_table(prefer_live: bool = True, use_playwright: bool = False,
                         seed_path: Path = SEED_STRENGTH_TABLE) -> pd.DataFrame:
    """Punto de entrada único. Orden de intento (default `use_playwright=False`):
      1. Fetch rápido por requests + pandas.read_html — confirmado en vivo
         (2026-08-20) que la tabla es HTML estático normal, sin JS, así
         que esto solo ya trae el dato real.
      2. Semilla manual (enso_strength_table_seed.csv) — última red de
         seguridad; nunca deja al pipeline sin datos.

    Playwright (`use_playwright=True`) queda disponible pero DESACTIVADO
    por default: confirmado que en Streamlit Community Cloud nadie corre
    `playwright install chromium`, así que el navegador no está — el
    intento tarda hasta ~90s en fallar (3 URLs × 30s de timeout) antes de
    caer al fetch liviano, y eso fue justo lo que causaba que la página
    de Riesgo Climático-Hidrológico se quedara "cargando y cargando" hasta
    que Streamlit Cloud cortaba la conexión. Como el fetch liviano ya trae
    el mismo dato real, Playwright pasó a ser solo una herramienta de
    diagnóstico manual (`scripts/test_6_playwright_noaa.py`) para cuando
    NOAA cambie la página y haga falta investigar con un navegador real.

    LA SEMILLA SE DESACTUALIZA. NOAA publica esta tabla junto con el ENSO
    Diagnostic Discussion, el 2º jueves de cada mes. Si el fetch liviano
    deja de funcionar (NOAA cambia la página), el proceso mantenible de
    emergencia es: entrar a la página una vez al mes, copiar la tabla a
    mano a enso_strength_table_seed.csv (mismo formato), y listo.
    """
    if prefer_live and use_playwright:
        from sala_control.data.enso_scraper_playwright import (
            load_strength_table_cached, scrape_strength_table,
        )
        cached = load_strength_table_cached()
        if cached is not None:
            return cached

        live = scrape_strength_table()
        if live is not None:
            return live
        print("[enso_noaa] Playwright no logró extraer la tabla; probando fetch por requests...")

    if prefer_live:
        live = fetch_strength_probabilities_live()
        if live is not None:
            return live
        print("[enso_noaa] Fetch en vivo de la tabla de fuerza ENSO falló o no validó; "
              "usando semilla manual (revisa su fecha de captura).")

    seed = pd.read_csv(seed_path)
    seed["fuente"] = f"semilla_manual ({seed['captured_on'].iloc[0]})"
    return seed
