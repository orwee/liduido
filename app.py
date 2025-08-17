import streamlit as st
import pandas as pd
import requests # Importamos la librería requests

# --- Configuración de la página de Streamlit ---
# Por defecto, Streamlit usa un tema claro. No se necesita configuración adicional.
st.set_page_config(
    page_title="Comparador de Pares DEX",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Credenciales de Supabase ---
# Obtenemos las credenciales desde los secretos de Streamlit.
try:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("Error: No se encontraron las credenciales de Supabase. Asegúrate de configurar tu archivo `secrets.toml`.")
    st.stop()

# --- Función para cargar y procesar los datos con Requests ---
@st.cache_data(ttl=600) # La caché expira cada 10 minutos
def load_data():
    """
    Carga los datos desde la API REST de Supabase usando requests,
    filtrando por blockchain = 'hyperevm'.
    """
    columns_to_select = "pair,tier,dex,apy24h,tvl,volume24h2,fees24h"
    url = f"{supabase_url}/rest/v1/Tabla2?select={columns_to_select}&blockchain=eq.hyperevm"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}"
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data:
                df = pd.DataFrame(data)
                for col in ['apy24h', 'tvl', 'volume24h2', 'fees24h', 'tier']:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                return df
            else:
                st.warning("No se encontraron datos para la blockchain 'hyperevm'.")
                return pd.DataFrame()
        else:
            st.error(f"Error al consultar la API de Supabase: {response.status_code} - {response.text}")
            return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        st.error(f"Ocurrió un error de conexión: {e}")
        return pd.DataFrame()

# --- Función para resaltar filas ---
def highlight_dex(row):
    """
    Resalta las filas de 'gliquid' y 'gliquid_test'.
    """
    color = 'background-color: #D6EAF8' # Un color claro para resaltar
    if row.dex in ['gliquid', 'gliquid_test']:
        return [color] * len(row)
    else:
        return [''] * len(row)

# --- Interfaz de la Aplicación ---
st.title("📊 Comparador de Pares en DEXs para HyperEVM")
st.markdown("Esta aplicación busca datos en Supabase y compara los pares disponibles en diferentes DEXs.")

df = load_data()

if not df.empty:
    all_pairs = sorted(df['pair'].unique())
    default_selection = ['kHYPE/WHYPE'] if 'kHYPE/WHYPE' in all_pairs else []
    
    selected_pairs = st.multiselect(
        "Selecciona los pares que quieres comparar:",
        options=all_pairs,
        default=default_selection
    )
    
    st.markdown("---")

    if selected_pairs:
        for pair in selected_pairs:
            with st.expander(f"Comparativa para el par: **{pair}**", expanded=True):
                
                pair_df = df[df['pair'] == pair].copy()
                
                # --- Valores por defecto para la calculadora ---
                # CORRECCIÓN: Busca la fila de 'gliquid' con el mayor apy24h
                gliquid_data = pair_df[pair_df['dex'] == 'gliquid'].sort_values(by='apy24h', ascending=False)
                
                if not gliquid_data.empty:
                    # Si existe 'gliquid', usamos los datos del de mayor APY como defecto
                    best_gliquid = gliquid_data.iloc[0]
                    default_tier = float(best_gliquid['tier'])
                    default_tvl = int(best_gliquid['tvl'])
                    default_volume = int(best_gliquid['volume24h2'])
                else:
                    # Si no, usamos valores genéricos
                    default_tier = 1.0
                    default_tvl = 100000
                    default_volume = 50000

                # --- Calculadora para 'gliquid_test' ---
                st.subheader("Calculadora APY para 'gliquid_test'")
                col1, col2, col3 = st.columns(3)
                with col1:
                    new_tier = st.number_input("Tier", value=default_tier, step=0.05, format="%.2f", key=f"tier_{pair}")
                with col2:
                    new_tvl = st.number_input("TVL", value=default_tvl, step=10000, key=f"tvl_{pair}")
                with col3:
                    new_volume = st.number_input("Volumen 24h", value=default_volume, step=10000, key=f"vol_{pair}")

                # Calcular nuevos valores
                new_apy = (new_tier * new_volume / new_tvl) * 365 if new_tvl > 0 else 0
                # CORRECCIÓN: Calcular las fees para gliquid_test
                new_fees = new_tier * new_volume

                # Crear la nueva fila
                new_row_data = {
                    'pair': pair, 'tier': new_tier, 'dex': 'gliquid_test',
                    'apy24h': new_apy, 'tvl': new_tvl, 
                    'volume24h2': new_volume, 
                    'fees24h': new_fees
                }
                new_row_df = pd.DataFrame([new_row_data])

                # --- Preparar y mostrar la tabla ---
                combined_df = pd.concat([new_row_df, pair_df])
                sorted_df = combined_df.sort_values(by='apy24h', ascending=False).reset_index(drop=True)
                
                formatter = {
                    'tier': "{:.2f}",
                    'apy24h': "{:,.2f}",
                    'tvl': "{:,.2f}",
                    'volume24h2': "{:,.2f}",
                    'fees24h': "{:,.2f}"
                }
                
                # Aplicamos el estilo para resaltar y formatear, y luego mostramos el DataFrame
                st.dataframe(sorted_df.style.apply(highlight_dex, axis=1).format(formatter), use_container_width=True)
    else:
        st.info("Por favor, selecciona al menos un par para ver la comparativa.")
else:
    st.info("No hay datos disponibles para mostrar.")

if st.button('Recargar Datos'):
    st.cache_data.clear()
    st.rerun()
