import streamlit as st
import pandas as pd
from supabase import create_client, Client
import os

# --- Configuración de la página de Streamlit ---
st.set_page_config(
    page_title="Comparador de Pares DEX",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Conexión a Supabase ---
# Intenta obtener las credenciales desde los secretos de Streamlit.
try:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(supabase_url, supabase_key)
except KeyError:
    # Si las credenciales no se encuentran en los secretos, muestra un error claro.
    st.error("Error: No se encontraron las credenciales de Supabase. Asegúrate de configurar tu archivo `secrets.toml`.")
    st.stop() # Detiene la ejecución si no hay credenciales.

# --- Función para cargar y procesar los datos ---
@st.cache_data(ttl=600) # La caché expira cada 10 minutos (600 segundos)
def load_data():
    """
    Carga los datos desde la tabla 'Tabla2' en Supabase,
    filtrando por blockchain = 'hyperevm'.
    """
    try:
        # Columnas que queremos seleccionar de la tabla.
        columns_to_select = "pair, tier, dex, apy_24h, tvl, volume24h, fees24h"
        
        # Ejecutamos la consulta a Supabase.
        response = supabase.table('Tabla2').select(columns_to_select).eq('blockchain', 'hyperevm').execute()
        
        # Verificamos si la respuesta contiene datos.
        if response.data:
            # Convertimos los datos a un DataFrame de Pandas para un manejo más fácil.
            df = pd.DataFrame(response.data)
            return df
        else:
            # Si no hay datos, devolvemos un DataFrame vacío.
            st.warning("No se encontraron datos para la blockchain 'hyperevm'.")
            return pd.DataFrame()
            
    except Exception as e:
        # Capturamos cualquier error durante la consulta y lo mostramos.
        st.error(f"Ocurrió un error al conectar o consultar Supabase: {e}")
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
        # Iteramos sobre cada par seleccionado por el usuario.
        for pair in selected_pairs:
            # Creamos un sub-DataFrame para el par actual.
            pair_df = df[df['pair'] == pair].copy()
            
            # Usamos st.expander para organizar la vista y no sobrecargar la pantalla.
            with st.expander(f"Comparativa para el par: **{pair}**", expanded=True):
                
                # Reiniciamos el índice para que no muestre el índice original del DataFrame.
                pair_df.reset_index(drop=True, inplace=True)
                
                # Mostramos la tabla de datos para el par.
                st.dataframe(pair_df, use_container_width=True)
    else:
        st.info("Por favor, selecciona al menos un par para ver la comparativa.")

else:
    # Mensaje que se muestra si no se pudieron cargar datos.
    st.info("No hay datos disponibles para mostrar.")

# Botón para forzar la recarga de los datos, limpiando la caché.
if st.button('Recargar Datos'):
    st.cache_data.clear()
    st.rerun()

