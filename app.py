# app.py
import io
import os
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
  /* Estrechar el contenido para que se vea más ordenado */
  .block-container { max-width: 1100px; padding-top: 1rem; }
  
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
st.write("Sube archivos **.xlsx** (uno por proveedor) con columnas **SKU**, **Nombre**, **Precio Unitario**.")

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
    modo_flechas = st.toggle("Editar cantidades con flechas (por fila)", value=False)


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

# ========= Helpers =========
def fmt_money4(x):
    try:
        return f"${float(x):,.4f}"
    except:
        return x

if "empate_sel" not in st.session_state:
    st.session_state.empate_sel = {}   # {sku_str: proveedor_elegido}

if "cantidades" not in st.session_state:
    st.session_state.cantidades = {}   # {(prov, sku_str): int}

# ======== PESTAÑAS =========
tab_empates, tab_pedido = st.tabs(["1) Resolver empates", "2) Armar pedido"])

# ---------- TAB 1: Resolver empates ----------
with tab_empates:
    st.markdown("<h4>⚖️ Empates detectados</h4>", unsafe_allow_html=True)

    if empates_reales.empty:
        st.info("No hay empates.")
    else:
        skus_empatados = sorted(empates_reales['SKU_str'].unique())

        # Progreso: solo cuentan los SKUs que ya tienen proveedor elegido (no placeholder)
        resueltos = sum(1 for s in skus_empatados if s in st.session_state.empate_sel)
        st.write(f"Progreso: **{resueltos}/{len(skus_empatados)} SKUs**")
        st.progress(resueltos / len(skus_empatados) if len(skus_empatados) else 0.0)

        PLACEHOLDER = "— Selecciona proveedor —"

        for sku, g in empates_reales.groupby('SKU_str', sort=False):
            nombre = g.iloc[0]['Nombre_canonico']
            st.markdown(f"**SKU {sku} — {nombre}**")

            proveedores = list(g['Proveedor'].unique())
            opciones = [PLACEHOLDER] + proveedores

            # Valor previo (si ya eligieron algo en otra interacción)
            prev = st.session_state.empate_sel.get(sku, PLACEHOLDER)
            idx = opciones.index(prev) if prev in opciones else 0

            elegido = st.selectbox(
                "Elige proveedor para este SKU",
                opciones,
                index=idx,
                key=f"sel_{sku}"
            )

            # Actualiza session_state solo si eligió un proveedor real
            if elegido != PLACEHOLDER:
                st.session_state.empate_sel[sku] = elegido
            else:
                # Si vuelve a placeholder, borra la elección
                st.session_state.empate_sel.pop(sku, None)

            # Tabla informativa de precios
            g_show = g[['Proveedor','Precio Unitario']].rename(columns={'Precio Unitario':'Precio'}).copy()
            g_show['Precio'] = g_show['Precio'].map(lambda x: f"${float(x):,.4f}")
            st.markdown(g_show.to_html(index=False, classes='tbl', escape=False), unsafe_allow_html=True)
            st.write("")


# ---------- Construir “ganadores” incluyendo elecciones (fuera de tabs para reutilizar) ----------
gan_base = ganadores_unicos[['Proveedor','SKU','SKU_str','Nombre_canonico','Precio Unitario']].copy()

if not empates_reales.empty and len(st.session_state.empate_sel) > 0:
    elegidas = []
    for sku, prov_elegido in st.session_state.empate_sel.items():
        block = empates_reales[(empates_reales['SKU_str'] == sku) & (empates_reales['Proveedor'] == prov_elegido)]
        if not block.empty:
            elegidas.append(block[['Proveedor','SKU','SKU_str','Nombre_canonico','Precio Unitario']].iloc[0])
    gan_total = pd.concat([gan_base, pd.DataFrame(elegidas)], ignore_index=True) if elegidas else gan_base.copy()
else:
    gan_total = gan_base.copy()

# ---------- TAB 2: Armar pedido ----------
with tab_pedido:
    st.markdown("<h4>🏆 Ganadores por proveedor</h4>", unsafe_allow_html=True)

    if gan_total.empty:
        st.info("No hay ganadores por proveedor aún. Elige proveedores en los empates si aplica.")
    else:
        proveedores_orden = sorted(gan_total['Proveedor'].unique())
        tablas_por_proveedor = {}

        # Resumen global (aparece arriba)
        colA, colB, colC = st.columns([1,1,1])
        total_global_placeholder = colA.empty()  # lo llenamos después

        subtotales = {}

        for prov in proveedores_orden:
          st.markdown(f"<h5>🏪 {prov}</h5>", unsafe_allow_html=True)
      
          base = (
              gan_total[gan_total['Proveedor'] == prov]
              [['SKU_str','Nombre_canonico','Precio Unitario']]
              .rename(columns={'SKU_str':'SKU','Nombre_canonico':'Nombre'})
              .assign(SKU_num=lambda d: pd.to_numeric(d['SKU'], errors='coerce'))
              .sort_values('SKU_num')
              .drop(columns='SKU_num')
              .copy()
          )
      
          if modo_flechas:
              # ===== MODO CON FLECHAS (number_input por fila) =====
              cantidades = []
              for _, row in base.iterrows():
                  sku = str(row['SKU'])
                  key = (prov, sku)
                  if key not in st.session_state.cantidades:
                      st.session_state.cantidades[key] = 0
                  qty = st.number_input(
                      f"Cantidad — SKU {sku}",
                      min_value=0, step=1,
                      value=int(st.session_state.cantidades[key]),
                      key=f"qty_{prov}_{sku}"
                  )
                  st.session_state.cantidades[key] = qty
                  cantidades.append(qty)
      
              g = base.copy()
              g['Cantidad'] = cantidades
              g['Total'] = (pd.to_numeric(g['Precio Unitario'], errors='coerce') * g['Cantidad']).fillna(0.0)
              tablas_por_proveedor[prov] = g[['Cantidad','SKU','Nombre','Precio Unitario','Total']].copy()
      
              # Vista bonita
              g_view = tablas_por_proveedor[prov].copy()
              g_view['Precio Unitario'] = g_view['Precio Unitario'].map(lambda x: f"${float(x):,.4f}")
              g_view['Total'] = g_view['Total'].map(lambda x: f"${float(x):,.4f}")
              st.markdown(g_view.to_html(index=False, classes='tbl', escape=False), unsafe_allow_html=True)
      
          else:
              # ===== MODO TABLA EDITABLE (data_editor) =====
              edited = st.data_editor(
                  base.assign(Cantidad=[
                      st.session_state.cantidades.get((prov, str(sku)), 0) for sku in base['SKU']
                  ]),
                  num_rows="fixed",
                  column_config={
                      "Cantidad": st.column_config.NumberColumn("Cantidad", min_value=0, step=1),
                      "Precio Unitario": st.column_config.NumberColumn("Precio Unitario", format="$%.4f", disabled=True),
                      "Total": st.column_config.NumberColumn("Total", format="$%.4f", disabled=True),
                      "SKU": st.column_config.TextColumn("SKU", disabled=True),
                      "Nombre": st.column_config.TextColumn("Nombre", disabled=True),
                  },
                  use_container_width=True,
                  hide_index=True,
                  key=f"edit_{prov}"
              )
              edited['Total'] = edited['Cantidad'] * edited['Precio Unitario']
      
              # Persistir cantidades en session_state
              for _, r in edited.iterrows():
                  st.session_state.cantidades[(prov, str(r['SKU']))] = int(r['Cantidad'])
      
              tablas_por_proveedor[prov] = edited[['Cantidad','SKU','Nombre','Precio Unitario','Total']].copy()
      
          # ===== Subtotal por proveedor (común a ambos modos) =====
          subtotal = float(tablas_por_proveedor[prov]['Total'].sum())
          subtotales[prov] = subtotal
          st.metric("Subtotal", f"${subtotal:,.2f}")


        # Total global
        total_global = sum(subtotales.values())
        total_global_placeholder.metric("Total general", f"${total_global:,.2f}")

        # Descarga (mover al sidebar para que esté siempre visible)
        with st.sidebar:
            st.subheader("📥 Exportar")
            output = io.BytesIO()
            cst = pytz.timezone("America/Mexico_City")
            timestamp = datetime.datetime.now(cst).strftime("%Y%m%d_%H%M%S")
            excel_name = f"pedido_por_proveedor_{timestamp}.xlsx"

            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                for prov, dfprov in tablas_por_proveedor.items():
                    outdf = dfprov[['Cantidad','SKU','Nombre','Precio Unitario','Total']].copy()
                    outdf.to_excel(writer, index=False, sheet_name=str(prov)[:31])
                    # formato bonito en Excel
                    wb  = writer.book
                    money = wb.add_format({'num_format': '$#,##0.00'})
                    qty   = wb.add_format({'num_format': '0'})
                    ws = writer.sheets[str(prov)[:31]]
                    ws.set_column(0, 0, 10, qty)      # Cantidad
                    ws.set_column(1, 1, 12)           # SKU
                    ws.set_column(2, 2, 28)           # Nombre
                    ws.set_column(3, 4, 14, money)    # Precio, Total

            st.download_button(
                label="Generar Excel por proveedor",
                data=output.getvalue(),
                file_name=excel_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )


# =========================
# DEBUG OPCIONAL
# =========================
with st.expander("🔍 Debug (opcional)"):
    st.write("Filas combinadas:", len(merged_df))
    st.write("Ganadores únicos:", len(ganadores_unicos))
    st.write("Empates reales:", len(empates_reales))
    st.dataframe(mejores_precios_df.head())
