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
    columns_to_select = "pair,tier,dex,apy_24h,tvl,volume24h,fees24h"
    
    # Construimos la URL completa para la petición GET.
    # Añadimos los parámetros para seleccionar columnas y filtrar por blockchain.
    url = f"{supabase_url}/rest/v1/Tabla2?select={columns_to_select}&blockchain=eq.hyperevm"
    
    # Preparamos los headers para la autenticación, como en el ejemplo de cURL.
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}"
    }
    
    try:
        # Realizamos la petición GET a la API.
        response = requests.get(url, headers=headers)
        
        # Verificamos que la petición fue exitosa (código 200).
        if response.status_code == 200:
            data = response.json()
            if data:
                # Convertimos la respuesta JSON a un DataFrame de Pandas.
                df = pd.DataFrame(data)
                return df
            else:
                st.warning("No se encontraron datos para la blockchain 'hyperevm'.")
                return pd.DataFrame()
        else:
            # Si hay un error en la respuesta, lo mostramos.
            st.error(f"Error al consultar la API de Supabase: {response.status_code} - {response.text}")
            return pd.DataFrame()
            
    except requests.exceptions.RequestException as e:
        # Capturamos errores de conexión (ej. no hay internet).
        st.error(f"Ocurrió un error de conexión: {e}")
        return pd.DataFrame()

# --- Interfaz de la Aplicación ---

# Título principal de la aplicación.
st.title("📊 Comparador de Pares en DEXs para HyperEVM")
st.markdown("Esta aplicación busca datos en Supabase y compara los pares disponibles en diferentes DEXs.")

# Cargamos los datos usando nuestra función cacheada.
df = load_data()

# Si el DataFrame no está vacío, procedemos a mostrar los datos.
if not df.empty:
    
    # Obtenemos la lista de todos los pares únicos para el filtro.
    all_pairs = sorted(df['pair'].unique())
    
    # Creamos un multiselector para que el usuario elija qué pares visualizar.
    selected_pairs = st.multiselect(
        "Selecciona los pares que quieres comparar:",
        options=all_pairs,
        default=all_pairs
    )
    
    st.markdown("---") # Separador visual

    # Filtramos el DataFrame principal para mostrar solo los pares seleccionados.
    if selected_pairs:
        for pair in selected_pairs:
            pair_df = df[df['pair'] == pair].copy()
            
            with st.expander(f"Comparativa para el par: **{pair}**", expanded=True):
                pair_df.reset_index(drop=True, inplace=True)
                st.dataframe(pair_df, use_container_width=True)
    else:
        st.info("Por favor, selecciona al menos un par para ver la comparativa.")

else:
    st.info("No hay datos disponibles para mostrar.")

# Botón para forzar la recarga de los datos, limpiando la caché.
if st.button('Recargar Datos'):
    st.cache_data.clear()
    st.rerun()
