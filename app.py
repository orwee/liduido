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
    # Columnas que queremos seleccionar de la tabla.
    columns_to_select = "pair,tier,dex,apy24h,tvl,volume24h,fees24h"
    
    # Construimos la URL completa para la petición GET.
    url = f"{supabase_url}/rest/v1/Tabla2?select={columns_to_select}&blockchain=eq.hyperevm"
    
    # Preparamos los headers para la autenticación.
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
                # Asegurarse que las columnas numéricas sean del tipo correcto
                for col in ['apy24h', 'tvl', 'volume24h', 'fees24h', 'tier']:
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

# --- Interfaz de la Aplicación ---
st.title("📊 Comparador de Pares en DEXs para HyperEVM")
st.markdown("Esta aplicación busca datos en Supabase y compara los pares disponibles en diferentes DEXs.")

df = load_data()

if not df.empty:
    all_pairs = sorted(df['pair'].unique())
    
    # Establecemos el par por defecto
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
                
                # --- Calculadora para 'gliquid_test' ---
                st.subheader("Calculadora APY para 'gliquid_test'")
                col1, col2, col3 = st.columns(3)
                with col1:
                    new_tier = st.number_input("Tier", value=1.0, step=0.01, format="%.2f", key=f"tier_{pair}")
                with col2:
                    new_tvl = st.number_input("TVL", value=100000, step=1000, key=f"tvl_{pair}")
                with col3:
                    new_volume = st.number_input("Volumen 24h", value=50000, step=1000, key=f"vol_{pair}")

                # Calcular el nuevo APY
                if new_tvl > 0:
                    # Fórmula: (tier * volumen / tvl) * 100 (para %) * 365 (anual)
                    new_apy = (new_tier * new_volume / new_tvl) * 100 * 365
                else:
                    new_apy = 0

                # Crear la nueva fila
                new_row_data = {
                    'pair': pair, 'tier': new_tier, 'dex': 'gliquid_test',
                    'apy24h': new_apy, 'tvl': new_tvl, 'volume24h': new_volume,
                    'fees24h': 0 # Asumimos 0 fees para el test
                }
                new_row_df = pd.DataFrame([new_row_data])

                # --- Preparar y mostrar la tabla ---
                pair_df = df[df['pair'] == pair].copy()
                
                # Combinar la fila de la calculadora con los datos existentes
                combined_df = pd.concat([new_row_df, pair_df])
                
                # Ordenar el DataFrame combinado por apy24h en orden descendente
                sorted_df = combined_df.sort_values(by='apy24h', ascending=False)
                
                sorted_df.reset_index(drop=True, inplace=True)
                
                st.dataframe(sorted_df, use_container_width=True)
    else:
        st.info("Por favor, selecciona al menos un par para ver la comparativa.")
else:
    st.info("No hay datos disponibles para mostrar.")

if st.button('Recargar Datos'):
    st.cache_data.clear()
    st.rerun()
