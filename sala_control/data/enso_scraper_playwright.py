"""
data/enso_scraper_playwright.py — Scraper con navegador real (Playwright)
para "Official NOAA CPC ENSO Strength Probabilities".

Este módulo existe como camino de respaldo con navegador real por si NOAA
algún día empieza a armar la tabla con JavaScript — CONFIRMADO EN VIVO
(2026-08-20) que hoy NO es el caso: la tabla es HTML estático normal, y
`enso_noaa.fetch_strength_probabilities_live()` (solo `requests`, sin
Playwright) ya la trae sola. La sospecha anterior de que hacía falta un
navegador real venía de `pandas.read_html()` fallando en silencio por
falta del paquete `lxml`, no de un problema real de JS/renderizado — ver
`requirements.txt`. Playwright abre un Chromium real, deja que el JS corra
(por si acaso), toma el HTML YA RENDERIZADO (page.content()) y se lo pasa
al mismo parser que usa el camino por requests (enso_noaa.parse_strength_html).

AUTO-DIAGNÓSTICO: si la extracción falla en TODAS las URLs candidatas, se
guardan automáticamente (en .cache/enso/debug/) una captura de pantalla y
el HTML renderizado de la última URL intentada, y se imprime un resumen
(cuántas <table>, <svg>, <canvas> hay, y si aparecen los códigos de
estación como texto plano en la página) — útil para diferenciar "NOAA
cambió la página de verdad" de un problema de dependencias/parseo local.

Instalación (una sola vez, además de `pip install playwright`):
    playwright install chromium
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

from sala_control.data.enso_noaa import parse_strength_html, SEASON_TO_MONTH

CACHE_DIR = Path(".cache/enso")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
STRENGTH_CACHE = CACHE_DIR / "strength_table_live.parquet"

DEBUG_DIR = Path(".cache/enso/debug")

CANDIDATE_URLS = [
    "https://cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/strengths/",
    "https://cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/strengths.php",
    "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/strengths/",
]


def _dump_diagnostics(page, url: str) -> None:
    """Guarda evidencia y la resume en consola cuando una URL no produce
    una tabla válida. No lanza excepción — un fallo del diagnóstico no debe
    tumbar el flujo principal."""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        screenshot_path = DEBUG_DIR / f"screenshot_{stamp}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception as e:
        screenshot_path = None
        print(f"    (no se pudo guardar screenshot: {e})")

    try:
        html = page.content()
        html_path = DEBUG_DIR / f"page_{stamp}.html"
        html_path.write_text(html, encoding="utf-8")
    except Exception as e:
        html = ""
        html_path = None
        print(f"    (no se pudo guardar HTML: {e})")

    n_table = page.locator("table").count() if page else 0
    n_svg = page.locator("svg").count() if page else 0
    n_canvas = page.locator("canvas").count() if page else 0

    # ¿Aparecen los códigos de estación como texto plano en algún lado de
    # la página? (útil para saber si es un gráfico SVG con texto real, en
    # vez de una <table>, en cuyo caso SÍ se podría leer con otra estrategia)
    #
    # OJO: page.get_by_text(season, exact=True) da FALSO NEGATIVO acá — la
    # marca real envuelve el código con un <span> de tooltip para lectores
    # de pantalla (ej. <abbr>JAS <span>Jul Aug Sep</span></abbr>), así que
    # el texto completo del elemento nunca es EXACTAMENTE "JAS". Se usa el
    # mismo criterio tolerante (límites de palabra) que ya usa
    # `_extract_season_code` en producción, sobre el texto plano de toda
    # la página, para no repetir este falso negativo.
    body_text = ""
    try:
        body_text = page.inner_text("body").upper()
    except Exception:
        pass
    season_hits = {season: len(re.findall(rf"\b{season}\b", body_text)) for season in SEASON_TO_MONTH}

    print(f"\n  --- Diagnóstico para {url} ---")
    print(f"  URL final tras redirecciones: {page.url if page else '(desconocida)'}")
    print(f"  <table> encontradas: {n_table}")
    print(f"  <svg> encontrados: {n_svg}  |  <canvas> encontrados: {n_canvas}")
    print(f"  Códigos de estación como texto plano en la página: {season_hits}")
    if screenshot_path:
        print(f"  Screenshot guardado en: {screenshot_path}")
    if html_path:
        print(f"  HTML renderizado guardado en: {html_path}")
    if n_table == 0 and (n_svg > 0 or n_canvas > 0) and any(v not in (0, "?") for v in season_hits.values()):
        print("  -> HIPÓTESIS: parece un gráfico SVG/Canvas con texto real, NO una <table>. "
              "pandas.read_html nunca va a encontrar esto. Envíame el screenshot y el HTML "
              "para diseñar una extracción distinta (leer directamente los elementos <text> del SVG).")
    elif n_table == 0 and n_svg == 0 and n_canvas == 0:
        print("  -> HIPÓTESIS: la página no cargó el contenido esperado (¿bloqueo, redirect a "
              "otra sección, o layout completamente distinto?). Revisa el screenshot.")


def scrape_strength_table(headless: bool = True, timeout_ms: int = 30000,
                           debug_on_failure: bool = True) -> pd.DataFrame | None:
    """Prueba las URLs candidatas en orden hasta que una produzca una tabla
    válida. Nunca lanza excepción — devuelve None si todo falla, para que
    el llamador (load_strength_table) pueda caer al fallback de semilla.

    Si `debug_on_failure` (default True) y ninguna URL funcionó, guarda
    automáticamente screenshot + HTML + un resumen de diagnóstico de la
    ÚLTIMA URL intentada, sin que tengas que volver a correr nada con
    headless=False."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[enso_scraper_playwright] Playwright no está instalado. "
              "Corre: pip install playwright && playwright install chromium")
        return None

    result = None
    last_url_tried, last_page = None, None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page()
            for url in CANDIDATE_URLS:
                last_url_tried, last_page = url, page
                try:
                    page.goto(url, timeout=timeout_ms, wait_until="networkidle")
                    page.wait_for_timeout(1500)  # margen extra por si el JS tarda en pintar
                    html = page.content()
                    result = parse_strength_html(html)
                    if result is not None:
                        break
                except Exception as e:
                    print(f"[enso_scraper_playwright] Falló {url}: {e}")
                    continue

            if result is None and debug_on_failure and last_page is not None:
                _dump_diagnostics(last_page, last_url_tried)

            browser.close()
    except Exception as e:
        print(f"[enso_scraper_playwright] Error de Playwright/Chromium: {e}")
        return None

    if result is not None:
        result["captured_on"] = dt.date.today().isoformat()
        result["fuente"] = "live_playwright"
        result.to_parquet(STRENGTH_CACHE, index=False)
    return result


def load_strength_table_cached(max_age_hours: int = 24) -> pd.DataFrame | None:
    """Caché del último scrape exitoso, para no abrir un navegador en cada
    corrida de Streamlit (Playwright es lento: ~5-15s por intento)."""
    if STRENGTH_CACHE.exists():
        age_hours = (dt.datetime.now().timestamp() - STRENGTH_CACHE.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            return pd.read_parquet(STRENGTH_CACHE)
    return None
