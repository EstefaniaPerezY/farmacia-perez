# app.py
import io
import os
import glob
import datetime
import pytz
import pandas as pd
import streamlit as st

# =========================
# CONFIG Y ESTILO
# =========================
st.set_page_config(page_title="Cotizador Farmacia Pérez", page_icon="💊", layout="wide")

CSS = """
<style>
  .box {
    font-family: Roboto, Arial, sans-serif;
    font-size: 15px;
    background: #F9FBFD;
    border: 1px solid #D6EAF8;
    border-radius: 10px;
    padding: 16px;
    text-align: left;
  }
  .box h3 {
    color: #2E86C1; margin: 0 0 12px 0; text-align: left;
  }
  .box h4 {
    color: #34495E; margin: 14px 0 8px 0; text-align: left;
  }
  .box h5 {
    color: #1A5276; margin: 10px 0 6px 0; text-align: left;
  }
  .tbl {
    width: auto; border-collapse: collapse; background: #fff;
    border: 1px solid #E5EAF2; border-radius: 10px; margin-left: 0;
  }
  .tbl th, .tbl td {
    padding: 8px 10px; border-bottom: 1px solid #EEF2F7;
    vertical-align: middle; text-align: left;
  }
  .tbl thead th {
    background: #F3F7FB; color: #2C3E50; font-weight: 600; font-size: 14px;
  }
  .tbl tbody tr:hover { background: #FAFCFF; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

st.title("💊 Cotizador — Farmacia Pérez")
st.write("Sube archivos **.xlsx** (uno por proveedor) con columnas **SKU**, **Nombre**, **Precio Unitario** Holaaaa.")

# =========================
# SIDEBAR: Parámetros
# =========================
with st.sidebar:
    st.header("⚙️ Parámetros")
    precision_empate = st.number_input(
        "Precisión para decidir empates (decimales)",
        min_value=0, max_value=6, value=2, step=1
    )
    mostrar_previas = st.checkbox("Mostrar tablas intermedias", value=False)
    limpiar_resultados = st.checkbox("Limpiar carpeta 'resultados' de días anteriores", value=True)

# =========================
# INPUT: Archivos
# =========================
files = st.file_uploader(
    "Selecciona uno o varios Excel (.xlsx), uno por proveedor",
    type=["xlsx"], accept_multiple_files=True
)

if not files:
    st.info("Sube tus archivos para comenzar.")
    st.stop()

# =========================
# Limpieza de carpeta resultados (opcional)
# =========================
if limpiar_resultados:
    results_dir = "resultados"
    os.makedirs(results_dir, exist_ok=True)
    cst = pytz.timezone("America/Mexico_City")
    today = datetime.datetime.now(cst).strftime("%Y%m%d")
    removed = []
    for fname in os.listdir(results_dir):
        if not fname.endswith(".xlsx"):
            continue
        parts = fname.split("_")
        if len(parts) >= 2:
            date_part = parts[1]
            if not date_part.startswith(today):
                try:
                    os.remove(os.path.join(results_dir, fname))
                    removed.append(fname)
                except Exception:
                    pass
    if removed:
        st.toast(f"🗑️ Eliminados {len(removed)} archivos antiguos en 'resultados'")

# =========================
# LECTURA + VALIDACIÓN DE ENTRADA
# =========================
dataframes = {}
for upl in files:
    prov_name = os.path.splitext(upl.name)[0]
    try:
        df = pd.read_excel(upl)

        # Normaliza headers
        df.columns = df.columns.str.strip()

        # Columnas mínimas
        min_cols = ['SKU', 'Precio Unitario']
        if not all(c in df.columns for c in min_cols):
            st.error(f"❌ {upl.name} no tiene columnas mínimas {min_cols}.")
            st.stop()

        if 'Nombre' not in df.columns:
            df['Nombre'] = ""

        df['Proveedor'] = prov_name

        # SKU: string limpio y validación estricta (solo dígitos)
        df['SKU'] = df['SKU'].astype(str).str.strip()
        invalid_skus = df[~df['SKU'].str.match(r'^\d+$', na=False)]
        if not invalid_skus.empty:
            st.error(f"❌ SKUs inválidos en {upl.name}. Solo dígitos permitidos.")
            st.dataframe(invalid_skus[['SKU']])
            st.stop()

        # Normaliza Nombre
        df['Nombre'] = df['Nombre'].astype(str).str.strip()

        # Precio: limpia símbolos y convierte
        df['Precio Unitario'] = (
            df['Precio Unitario'].astype(str)
              .str.replace(r'[^0-9,\.\-]', '', regex=True)
              .str.replace(',', '', regex=False)  # ajusta si usas coma decimal
        )
        df['Precio Unitario'] = pd.to_numeric(df['Precio Unitario'], errors='coerce')

        dataframes[prov_name] = df

        if mostrar_previas:
            st.success(f"✅ Cargado: {upl.name}")
            st.dataframe(df.head())
    except Exception as e:
        st.error(f"❌ Error leyendo {upl.name}: {e}")
        st.stop()

if not dataframes:
    st.error("No se cargaron datos válidos.")
    st.stop()

# =========================
# MERGE + NOMBRE CANÓNICO
# =========================
merged_df = pd.concat(dataframes.values(), ignore_index=True)
merged_df['SKU'] = merged_df['SKU'].astype(str).str.strip()

# Nombre canónico por SKU (mode; si no hay, el más largo)
nombres_canon = (
    merged_df.assign(Nombre_norm=merged_df['Nombre'].astype(str).str.strip())
             .groupby('SKU')['Nombre_norm']
             .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else (max(s, key=len) if len(s) else ""))
             .rename('Nombre_canonico')
             .reset_index()
)
merged_df = merged_df.merge(nombres_canon, on='SKU', how='left')

# Orden básico
merged_df = merged_df.sort_values(by='SKU', ascending=True).reset_index(drop=True)

if mostrar_previas:
    st.subheader("📊 Vista combinada (primeras filas)")
    st.dataframe(merged_df.head(20))

# =========================
# EMPATES/MEJORES (con columna comparativa)
# =========================
tmp = merged_df.dropna(subset=['Precio Unitario']).copy()
tmp['Precio_cmp'] = pd.to_numeric(tmp['Precio Unitario'], errors='coerce').round(precision_empate)

# Mínimo por SKU (comparativa)
min_por_sku = tmp.groupby('SKU')['Precio_cmp'].transform('min')

# Ganador mínimo por SKU (uno)
idx = tmp.groupby('SKU')['Precio_cmp'].idxmin()
mejores_precios_df = tmp.loc[idx].sort_values('SKU').reset_index(drop=True)

# Empates: todos los que igualan el mínimo (con la precisión deseada)
empates_df = (
    tmp[min_por_sku == tmp['Precio_cmp']]
      .sort_values(['SKU', 'Proveedor'])
      .reset_index(drop=True)
)

# Derivados para resumen
_emp = empates_df.copy()
_emp['SKU_str'] = _emp['SKU'].astype(str)
_emp['SKU_num'] = pd.to_numeric(_emp['SKU'], errors='coerce')

counts = _emp.groupby('SKU_str')['SKU_str'].transform('size')
ganadores_unicos = _emp[counts == 1].copy()
empates_reales  = _emp[counts > 1].copy()

ganadores_unicos = ganadores_unicos.sort_values(
    by=['Proveedor', 'SKU_num', 'SKU_str'], ascending=[True, True, True]
).reset_index(drop=True)

empates_reales = empates_reales.sort_values(
    by=['SKU_num', 'Proveedor', 'Precio Unitario'], ascending=[True, True, True]
).reset_index(drop=True)

# =========================
# RENDER RESUMEN EN HTML (mismo estilo)
# =========================
def fmt_money4(x):
    try:
        return f"${float(x):,.4f}"
    except:
        return x

html = """
<div class='box'>
  <h3>💼 Tu cotización ha finalizado</h3>
  <p style='color:#7F8C8D; margin-top:-6px'>
    Resumen profesional a partir de precios mínimos y empates por SKU (precisión: {prec} decimales).
  </p>
  <h4>🏆 Ganadores por proveedor</h4>
""".format(prec=precision_empate)

if not ganadores_unicos.empty:
    for prov, g in ganadores_unicos.groupby('Proveedor', sort=True):
        g2 = (
            g[['SKU','Nombre_canonico','Precio Unitario']]
            .rename(columns={'Nombre_canonico':'Nombre', 'Precio Unitario':'Precio'})
            .sort_values(['SKU'])
            .copy()
        )
        g2['Precio'] = g2['Precio'].map(fmt_money4)
        html += f"<h5>🏪 {prov}</h5>"
        html += g2.to_html(index=False, escape=False, classes='tbl')
        html += "<br>"
else:
    html += "<p style='color:#7F8C8D;'>No hay ganadores únicos por SKU.</p>"

html += "<hr><h4>⚖️ Empates detectados</h4>"

if not empates_reales.empty:
    for sku, g in empates_reales.groupby('SKU_str', sort=False):
        nombre = g.iloc[0]['Nombre_canonico']
        html += f"<h5>SKU {sku} — {nombre}</h5>"
        e2 = (
            g[['Proveedor','Precio Unitario']]
            .rename(columns={'Precio Unitario':'Precio'})
            .sort_values(['Proveedor'])
            .copy()
        )
        e2['Precio'] = e2['Precio'].map(fmt_money4)
        html += e2.to_html(index=False, escape=False, classes='tbl')
        html += "<br>"
else:
    html += "<p style='color:#7F8C8D;'>No hay empates.</p>"

html += "</div>"

st.markdown(html, unsafe_allow_html=True)

# =========================
# DESCARGA DEL EXCEL (en memoria)
# =========================
cst = pytz.timezone("America/Mexico_City")
timestamp = datetime.datetime.now(cst).strftime("%Y%m%d_%H%M%S")
excel_name = f"cotizacion_{timestamp}.xlsx"

# Crea un Excel con hojas útiles
output = io.BytesIO()
with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
    merged_df.to_excel(writer, index=False, sheet_name="Combinado")
    mejores_precios_df.to_excel(writer, index=False, sheet_name="Mejores")
    empates_df.to_excel(writer, index=False, sheet_name="Empates_base")
    ganadores_unicos.to_excel(writer, index=False, sheet_name="Ganadores_unicos")
    empates_reales.to_excel(writer, index=False, sheet_name="Empates_reales")

st.download_button(
    label="💾 Descargar Excel",
    data=output.getvalue(),
    file_name=excel_name,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# =========================
# DEBUG OPCIONAL
# =========================
with st.expander("🔍 Debug (opcional)"):
    st.write("Filas combinadas:", len(merged_df))
    st.write("Ganadores únicos:", len(ganadores_unicos))
    st.write("Empates reales:", len(empates_reales))
    st.dataframe(mejores_precios_df.head())
