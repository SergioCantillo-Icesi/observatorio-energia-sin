"""
utils.py — utilidades compartidas del Observatorio Energético SIN.

Si tu proyecto ya tiene un módulo utils.py con `_normalize()` / `force_writable()`
(según lo documentado en memoria de proyecto), usa ESE en lugar de este archivo
para no duplicar lógica. Este archivo es autocontenido para que el módulo de
reservas hídricas funcione de forma independiente si aún no existe.
"""
from __future__ import annotations

import unicodedata
import datetime as dt

import numpy as np
import pandas as pd


def normalize(text: str) -> str:
    """Minúsculas + sin tildes/diacríticos, para matching robusto contra
    catálogos SIMEM/XM (p. ej. 'Útil' vs 'Util')."""
    if text is None:
        return ""
    text = str(text).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


def force_writable(arr: np.ndarray) -> np.ndarray:
    """Devuelve una copia escribible de un array que puede venir de un
    DataFrame cacheado por Streamlit (a veces marcado read-only)."""
    if isinstance(arr, np.ndarray) and not arr.flags.writeable:
        return arr.copy()
    return arr


# ---------------------------------------------------------------------------
# Año hidrológico: Colombia opera el SIN con una lógica de año hidrológico
# que arranca en diciembre (fin de temporada seca / inicio de llenado) y
# termina en noviembre. Esto es lo que replica el eje X del gráfico de
# referencia de SinergOX (2025-12 -> 2026-11).
# ---------------------------------------------------------------------------
HYDRO_YEAR_START_MONTH = 12  # diciembre


def hydro_year(date: dt.date) -> int:
    """Año hidrológico al que pertenece una fecha. Diciembre de un año
    calendario pertenece al MISMO año hidrológico que ene-nov del año
    calendario siguiente. Ej: 2025-12-15 y 2026-03-01 -> hydro_year = 2025."""
    if date.month >= HYDRO_YEAR_START_MONTH:
        return date.year
    return date.year - 1


def hydro_day(date: dt.date) -> int:
    """Día 0-indexado desde el 1 de diciembre del año hidrológico (0..364/365)."""
    hy = hydro_year(date)
    start = dt.date(hy, HYDRO_YEAR_START_MONTH, 1)
    return (date - start).days


def hydro_day_to_date(hy: int, day_offset: int) -> dt.date:
    start = dt.date(hy, HYDRO_YEAR_START_MONTH, 1)
    return start + dt.timedelta(days=int(day_offset))


def hydro_axis_labels(hy: int) -> pd.DataFrame:
    """Etiquetas de mes (YYYY-MM) para el eje X de un año hidrológico dado,
    en el mismo orden que el gráfico de referencia (dic -> nov)."""
    months = []
    for i in range(12):
        m = (HYDRO_YEAR_START_MONTH - 1 + i) % 12 + 1
        y = hy if m >= HYDRO_YEAR_START_MONTH else hy + 1
        months.append(dt.date(y, m, 1))
    return pd.DataFrame({"month_start": months,
                          "hydro_day": [hydro_day(d) for d in months],
                          "label": [d.strftime("%Y-%m") for d in months]})


def fmt_pct_co(value: float, decimals: int = 2) -> str:
    """Formatea un porcentaje con coma decimal, estilo colombiano: 78,19 %"""
    if pd.isna(value):
        return "—"
    s = f"{value:.{decimals}f}".replace(".", ",")
    return f"{s} %"
