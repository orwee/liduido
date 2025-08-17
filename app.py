import streamlit as st
import pandas as pd
import requests # Importamos la librería requests

# --- Configuración de la página de Streamlit ---
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
    # CORRECCIÓN: Se cambia a un color gris con texto blanco para mejor contraste en ambos temas
    style = 'background-color: #4F4F4F; color: white;'
    if row.dex in ['gliquid', 'gliquid_test']:
        return [style] * len(row)
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
            with st.expander(f"Comparativa para el par: **{pa
