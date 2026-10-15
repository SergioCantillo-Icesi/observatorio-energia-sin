"""
PRUEBA 7b — Comparación directa entre los dos candidatos a "Predespacho
Ideal" en el catálogo de SIMEM:

  2a301d = "Datos soporte del proceso de Despacho Ideal por Recurso,
            versión y horaria" — nombre exacto, pero sin datos desde
            2025-09-30 (parece descontinuado).
  ff027b = "Despacho programado recursos de generación" — nombre distinto,
            pero al día (dato hasta ayer).

Trae un día de cada uno y compara columnas/contenido, en vez de adivinar
por el nombre. Usa una fecha ANTIGUA (dentro del rango de ambos, ej.
2025-06-01) para que la comparación sea justa incluso si 2a301d ya no
recibe datos nuevos.

Correr: python test_7b_comparar_candidatos.py
"""
import datetime as dt

from sala_control.data.predespacho_xm import fetch_generacion_simem

FECHA_PRUEBA = dt.date(2025, 6, 2)  # dentro del rango de ambos datasets

candidatos = {
    "2a301d (Despacho Ideal por Recurso)": "2a301d",
    "ff027b (Despacho programado recursos de generación)": "ff027b",
}

resultados = {}
for nombre, ds_id in candidatos.items():
    print(f"\n{'='*70}\n{nombre}\n{'='*70}")
    try:
        df = fetch_generacion_simem(FECHA_PRUEBA, FECHA_PRUEBA, dataset_id=ds_id)
        print(f"Filas: {len(df)}")
        print(f"Columnas: {df.columns.tolist()}")
        print(df.head(8).to_string(index=False))
        resultados[nombre] = df
    except Exception as e:
        print(f"FALLÓ: {e}")
        resultados[nombre] = None

print(f"\n{'='*70}")
print("RESUMEN")
print(f"{'='*70}")
for nombre, df in resultados.items():
    if df is None:
        print(f"{nombre}: sin datos / error")
    else:
        print(f"{nombre}: {len(df)} filas, columnas {df.columns.tolist()}")

print("\nCompara: ¿cuál trae generación POR RECURSO/PLANTA (nombres como GUAVIO, "
      "TERMOSIERRA, etc.) con valores horarios? Ese es el que necesitamos. Si uno "
      "trae datos agregados por tecnología/región en vez de por planta individual, "
      "no sirve para la clasificación por tecnología que ya construimos.")
