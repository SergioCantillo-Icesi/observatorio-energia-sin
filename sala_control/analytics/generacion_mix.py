"""
analytics/generacion_mix.py — Clasificación de recursos de generación por
tecnología y agregación horaria, para la "Matriz de Generación Horaria".

Dos caminos de clasificación:
  1. `clasificar_tecnologia_oficial()` — PREFERIDO. Usa los atributos
     oficiales de XM del listado de recursos
     (data/predespacho_xm.enriquecer_con_recursos()):
       - Values_RecType (RecTypeOficial) para distinguir AUTOGENERADOR /
         GEN. DISTRIBUIDA de lo demás.
       - Values_EnerSource (FuenteOficial) — AGUA / VIENTO / SOLAR /
         BIOMASA / BIOGAS / BAGAZO / CARBON / GAS / ACPM / etc. — más
         preciso que Values_Type para clasificar correctamente.
  2. `clasificar_tecnologia()` — respaldo por patrones de texto en el
     nombre del recurso, SOLO para cuando no se tiene el listado de
     recursos (ej. archivo manual de respaldo). Menos preciso.

FNCER = Fuentes No Convencionales de Energía Renovable (Ley 1715 de 2014).
Agrupa Solar, Eólica, Biomasa, Biogás, Bagazo y similares — NO incluye
Hidráulica grande (que es renovable pero NO es "no convencional" según la
regulación) ni combustibles fósiles. Antes bagazo/biogás/biomasa caían mal
clasificados como "Térmica" (combustión fósil) — corregido aquí.
"""
from __future__ import annotations

import re

import pandas as pd

from sala_control.data.predespacho_xm import HOUR_COLS

ORDEN_TIPOS = [
    "Hidráulica", "Térmica", "FNCER",
    "Otra centralizada", "Gen. Distribuida (GD)", "Autogeneración (AUTOG)",
]

# Fuentes que cuentan como FNCER (Values_EnerSource, ya normalizado a
# mayúsculas). Cualquier fuente NO listada aquí y que tampoco sea AGUA se
# trata como Térmica (combustible fósil) por descarte.
_FUENTES_FNCER = {
    "VIENTO", "SOLAR", "RAD SOLAR", "RADIACION SOLAR", "RADIACION",
    "BIOMASA", "BIOGAS", "BAGAZO", "RESIDUOS", "GEOTERMIA",
}

_PATRON_SOLAR = re.compile(
    r"SOLAR|FOTOVOLT| FV|BSB|TRINA|GRANJA SOLAR|BOSQUES SOLARES"
    r"|PARQUE SOLAR|ECOPARQUE SOLAR"
)
_PATRON_EOLICA = re.compile(r"EOLIC")
_PATRON_BIOMASA = re.compile(r"BIOMASA|BIOGAS|BAGAZO|INGENIO|COGENERAD")
_PATRON_TERMICA = re.compile(
    r"TERMO|GECELCA|TASAJERO|PAIPA|ZIPAEMG|FLORES|MERILECTRICA"
    r"|PROELECTRICA|GUAJIRA|FUNDACION|TEBSA|BARRANQUILLA \d"
    r"|CARTAGENA \d|CANDELARIA"
)


def clasificar_tecnologia(nombre_planta: str) -> str:
    """Respaldo por texto (ver docstring del módulo) — solo se usa cuando
    no está disponible el listado oficial de recursos. Menos preciso que
    `clasificar_tecnologia_oficial()`."""
    nombre = str(nombre_planta).upper()
    if nombre.startswith("AUTOG"):
        return "Autogeneración (AUTOG)"
    if nombre.startswith("GD"):
        return "Gen. Distribuida (GD)"
    if _PATRON_SOLAR.search(nombre) or _PATRON_EOLICA.search(nombre) or _PATRON_BIOMASA.search(nombre):
        return "FNCER"
    if _PATRON_TERMICA.search(nombre):
        return "Térmica"
    return "Hidráulica"


def clasificar_tecnologia_oficial(tipo_oficial: str, rectype_oficial: str,
                                   fuente_oficial: str) -> str:
    """Clasificación PREFERIDA. Prioridad de señales:
      1. Values_RecType -> AUTOGENERADOR / GEN. DISTRIBUIDA (esto manda
         primero, sin importar la fuente — un autogenerador a biogás sigue
         siendo 'Autogeneración', no 'FNCER').
      2. Values_EnerSource -> AGUA es Hidráulica; VIENTO/SOLAR/BIOMASA/
         BIOGAS/BAGAZO/etc. son FNCER; cualquier otro combustible (CARBON,
         GAS, ACPM, COMBUSTOLEO, JET-A1...) es Térmica por descarte.
      3. Values_Type como respaldo, solo si Values_EnerSource viene vacío.
      4. Si nada calza, 'Otra centralizada' (catch-all explícito)."""
    rectype = str(rectype_oficial).upper().strip()
    fuente = str(fuente_oficial).upper().strip()
    tipo = str(tipo_oficial).upper().strip()

    if rectype == "AUTOGENERADOR":
        return "Autogeneración (AUTOG)"
    if "DISTRIBUIDA" in rectype:
        return "Gen. Distribuida (GD)"

    if fuente and fuente not in ("NAN", "NONE", ""):
        if "AGUA" in fuente:
            return "Hidráulica"
        if fuente in _FUENTES_FNCER or any(k in fuente for k in _FUENTES_FNCER):
            return "FNCER"
        return "Térmica"  # combustible fósil por descarte: carbón, gas, ACPM, etc.

    # Respaldo si no hay Values_EnerSource
    if "HIDRAULICA" in tipo:
        return "Hidráulica"
    if "TERMICA" in tipo:
        return "Térmica"
    if "SOLAR" in tipo or "EOLIC" in tipo:
        return "FNCER"
    return "Otra centralizada"


def compute_gen_por_tipo(df: pd.DataFrame, planta_col: str = "Planta") -> pd.DataFrame:
    """Suma la generación horaria (H1..H24) agrupada por tecnología.
    Devuelve un DataFrame indexado por 'Tipo', columnas H1..H24.

    Si `df` ya viene enriquecido con 'TipoOficial'/'RecTypeOficial'/
    'FuenteOficial' (salida de predespacho_xm.enriquecer_con_recursos()),
    usa la clasificación OFICIAL de XM. Si no, cae al respaldo por texto
    sobre el nombre (menos preciso)."""
    out = df.copy()
    cols_oficiales = ("TipoOficial", "RecTypeOficial", "FuenteOficial")
    if all(c in out.columns for c in cols_oficiales):
        out["Tipo"] = out.apply(
            lambda r: clasificar_tecnologia_oficial(
                r["TipoOficial"], r["RecTypeOficial"], r["FuenteOficial"]
            ), axis=1,
        )
    else:
        out["Tipo"] = out[planta_col].map(clasificar_tecnologia)
    return out.groupby("Tipo")[HOUR_COLS].sum()


def etiquetas_leyenda_con_fuente(df_enriquecido: pd.DataFrame) -> dict[str, str]:
    """Para cada categoría de Tipo, arma una etiqueta de leyenda que incluye
    las fuentes de energía (Values_EnerSource) reales que la componen —
    ej. 'Térmica (Carbón, Gas Natural)' en vez de solo 'Térmica'. Solo
    funciona si `df_enriquecido` tiene 'FuenteOficial' (viene de
    enriquecer_con_recursos()); si no, devuelve etiquetas simples (mismo
    nombre de categoría, sin paréntesis)."""
    if not all(c in df_enriquecido.columns for c in ("TipoOficial", "RecTypeOficial", "FuenteOficial")):
        return {t: t for t in ORDEN_TIPOS}

    out = df_enriquecido.copy()
    out["Tipo"] = out.apply(
        lambda r: clasificar_tecnologia_oficial(
            r["TipoOficial"], r["RecTypeOficial"], r["FuenteOficial"]
        ), axis=1,
    )
    etiquetas = {}
    for tipo, grupo in out.groupby("Tipo"):
        fuentes = sorted({
            str(f).strip().title() for f in grupo["FuenteOficial"]
            if pd.notna(f) and str(f).strip()
        })
        etiquetas[tipo] = f"{tipo} ({', '.join(fuentes)})" if fuentes else tipo
    return etiquetas


def resumen_participacion(gen_por_tipo: pd.DataFrame) -> pd.DataFrame:
    """% de participación de cada tecnología sobre el total del día."""
    total_dia = gen_por_tipo.sum(axis=1)
    part = (total_dia / total_dia.sum() * 100).round(1)
    return part.sort_values(ascending=False).rename("Participación (%)").to_frame()


def resumen_participacion_agente(df_enriquecido: pd.DataFrame,
                                  nombres_agentes: pd.DataFrame | None = None) -> pd.DataFrame:
    """% de participación por AGENTE (empresa generadora) — solo disponible
    si `df` viene enriquecido con la columna 'Agente' (código de la
    empresa). Solo incluye agentes con participación > 0%.

    `nombres_agentes`: DataFrame opcional [CodigoAgente, NombreAgente] —
    si se pasa, agrega el nombre completo de la empresa en vez de solo el
    código."""
    if "Agente" not in df_enriquecido.columns:
        raise RuntimeError(
            "El DataFrame no tiene columna 'Agente' — cruza primero con "
            "predespacho_xm.enriquecer_con_recursos()."
        )
    total_por_agente = df_enriquecido.groupby("Agente")[HOUR_COLS].sum().sum(axis=1)
    total_por_agente = total_por_agente[total_por_agente > 0]  # excluye 0% real
    part = (total_por_agente / total_por_agente.sum() * 100).round(1)
    part = part[part > 0]  # excluye lo que redondeó a 0.0%
    out = part.sort_values(ascending=False).rename("Participación (%)").to_frame()

    if nombres_agentes is not None:
        out = out.reset_index().rename(columns={"Agente": "CodigoAgente"})
        out["CodigoAgente"] = out["CodigoAgente"].astype(str).str.strip().str.upper()
        out = out.merge(nombres_agentes, on="CodigoAgente", how="left")
        out["NombreAgente"] = out["NombreAgente"].fillna(out["CodigoAgente"])
        out = out.set_index("NombreAgente")[["Participación (%)"]]

    return out


def pct_fncer_transversal(df_enriquecido: pd.DataFrame) -> float | None:
    """% del total de generación que viene de fuentes FNCER, SIN IMPORTAR
    si el recurso es Autogeneración, Gen. Distribuida, o centralizado
    normal — a diferencia de la categoría 'FNCER' del gráfico apilado
    (que excluye AUTOG/GD porque esos se separan PRIMERO por Values_RecType,
    sin mirar el combustible), este KPI es transversal: si un autogenerador
    corre con biogás o una GD es solar, ESO SÍ cuenta aquí como FNCER,
    aunque en el gráfico apilado aparezca bajo 'Autogeneración (AUTOG)' o
    'Gen. Distribuida (GD)'.

    Requiere la columna 'FuenteOficial' (salida de
    predespacho_xm.enriquecer_con_recursos()) — devuelve None si no está
    disponible (ej. archivo manual de respaldo)."""
    if "FuenteOficial" not in df_enriquecido.columns:
        return None
    total = df_enriquecido[HOUR_COLS].sum().sum()
    if not total:
        return None

    fuente = df_enriquecido["FuenteOficial"].astype(str).str.upper().str.strip()
    es_fncer = fuente.apply(lambda f: bool(f) and f not in ("NAN", "NONE")
                             and (f in _FUENTES_FNCER or any(k in f for k in _FUENTES_FNCER)))
    fncer_total = df_enriquecido.loc[es_fncer, HOUR_COLS].sum().sum()
    return float(fncer_total / total * 100)


def kpis_generacion(gen_por_tipo: pd.DataFrame, df_enriquecido: pd.DataFrame | None = None) -> dict[str, float | None]:
    """4 KPIs de composición para la fila encima del gráfico:
      - autog: % Autogeneración (AUTOG) — capacidad fuera del mercado
        mayorista centralizado.
      - gd: % Generación Distribuida — mismo espíritu, a menor escala.
      - termica: % Térmica — exposición a combustibles fósiles y costos
        marginales más altos; sube cuando la hidrología aprieta (link
        directo con el módulo de Riesgo Climático-Hidrológico).
      - fncer: % FNCER TRANSVERSAL (solar, eólica, biomasa, biogás,
        bagazo...) — incluye AutoG/GD cuyo combustible aplique, no solo la
        categoría 'FNCER' del gráfico apilado. Si se pasa `df_enriquecido`
        (con 'FuenteOficial'), usa el cálculo transversal preciso; si no,
        cae al cálculo por categoría del gráfico apilado (menos preciso,
        subestima el FNCER que quedó escondido dentro de AUTOG/GD).
    Devuelve None para cualquier KPI si el total es 0 (evita división por cero)."""
    total = gen_por_tipo.sum().sum()
    if not total:
        return {"autog": None, "gd": None, "termica": None, "fncer": None}

    def pct(tipos: list[str]) -> float:
        return float(sum(gen_por_tipo.loc[t].sum() for t in tipos if t in gen_por_tipo.index) / total * 100)

    fncer = None
    if df_enriquecido is not None:
        fncer = pct_fncer_transversal(df_enriquecido)
    if fncer is None:
        fncer = pct(["FNCER"])  # respaldo: subestima si hay FNCER dentro de AUTOG/GD

    return {
        "autog": pct(["Autogeneración (AUTOG)"]),
        "gd": pct(["Gen. Distribuida (GD)"]),
        "termica": pct(["Térmica"]),
        "fncer": fncer,
    }
