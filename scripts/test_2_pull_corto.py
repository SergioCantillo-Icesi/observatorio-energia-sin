"""
PRUEBA 2 de 3 — Descarga real de una ventana corta (60 días).

Objetivo: confirmar que fetch_reservas_pct() trae datos reales y que el
último valor de Pct coincide (o está muy cerca) del dato público de hoy en
https://www.xm.com.co/hidrología/reservas

Correr: python test_2_pull_corto.py
"""
import datetime as dt
from sala_control.data.reservas_xm import fetch_reservas_pct

end = dt.date.today()
start = end - dt.timedelta(days=60)

print(f"Descargando reservas del {start} al {end}...")
df = fetch_reservas_pct(start, end)

print("\nÚltimos 10 días:")
print(df.tail(10).to_string(index=False))

print("\nResumen estadístico de Pct:")
print(df["Pct"].describe())

ultimo_valor = df.iloc[-1]
print(f"\nÚltimo dato disponible: {ultimo_valor['Date']} -> {ultimo_valor['Pct']:.2f} %")
print("Compara este número contra https://www.xm.com.co/hidrología/reservas")

print("\nPRUEBA 2 OK si el número de arriba se parece al dato público. Continúa con test_3_pipeline_completo.py")
