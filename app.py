import streamlit as st
import pandas as pd
import plotly.express as px
import os # Importamos os para manejar rutas de archivos

# --- Configuración de la página ---
st.set_page_config(
    page_title="Análisis Histórico de APY",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Análisis Histórico de APY (desde archivos locales)")
st.markdown("Esta aplicación carga datos históricos desde una carpeta local `data` y visualiza la evolución del APY.")

# --- Funciones de Carga y Procesamiento ---

@st.cache_data(ttl=600) # Cache para no recargar en cada interacción
def load_all_data(data_folder="data"):
    """
    Carga todos los archivos CSV desde una carpeta local y los combina.
    """
    all_data = []
    
    # Verificamos si la carpeta 'data' existe
    if not os.path.isdir(data_folder):
        st.error(f"Error: No se encontró la carpeta '{data_folder}'. Asegúrate de que exista en el mismo directorio que el script.")
        return pd.DataFrame()

    # Listamos solo los archivos .csv en la carpeta
    filenames = [f for f in os.listdir(data_folder) if f.endswith('.csv')]
    if not filenames:
        st.warning(f"No se encontraron archivos .csv en la carpeta '{data_folder}'.")
        return pd.DataFrame()

    for filename in filenames:
        file_path = os.path.join(data_folder, filename)
        try:
            # Leemos el CSV y extraemos la fecha del nombre del archivo
            df = pd.read_csv(file_path)
            date_str = filename.replace('.csv', '')
            # Convertimos la fecha a un formato estándar (YYYY-MM-DD)
            df['date'] = pd.to_datetime(date_str, format='%d-%m-%y')
            all_data.append(df)
        except Exception as e:
            st.warning(f"No se pudo cargar o procesar el archivo: {filename}. Error: {e}")
    
    if not all_data:
        return pd.DataFrame()
        
    # Combinamos todos los dataframes en uno solo
    combined_df = pd.concat(all_data, ignore_index=True)
    return combined_df

def run_simulation(df, new_tier):
    """
    Crea una copia de los datos de 'gliquid', la renombra a 'gliquid_test'
    y recalcula el APY con el nuevo tier.
    """
    if df.empty or 'dex' not in df.columns:
        return df

    gliquid_df = df[df['dex'] == 'gliquid'].copy()
    if gliquid_df.empty:
        st.info("No se encontraron datos para el DEX 'gliquid' para realizar la simulación.")
        return df

    gliquid_test_df = gliquid_df.copy()
    gliquid_test_df['dex'] = 'gliquid_test'
    
    gliquid_test_df['apy24h'] = gliquid_test_df.apply(
        lambda row: (new_tier * row['volume24h2'] / row['tvl']) * 365 if row['tvl'] > 0 else 0,
        axis=1
    )
    
    return pd.concat([df, gliquid_test_df], ignore_index=True)


# --- Interfaz de Usuario ---

# 1. Slider para la simulación
st.subheader("1. Simulación para 'gliquid_test'")
simulated_tier = st.slider(
    "Selecciona el Fee Tier para la simulación de 'gliquid_test':",
    min_value=0.01, max_value=5.0, value=1.0, step=0.05, format="%.2f"
)

# --- Lógica Principal ---
# Cargamos los datos directamente
historical_df = load_all_data()

if not historical_df.empty:
    # Ejecutamos la simulación
    analysis_df = run_simulation(historical_df, simulated_tier)
    
    # Creamos un identificador único para cada línea del gráfico
    analysis_df['identifier'] = analysis_df['pair'] + " (" + analysis_df['dex'] + ")"
    
    st.subheader("2. Análisis y Comparativa")
    
    # 2. Filtro para seleccionar qué pools mostrar
    all_pools = sorted(analysis_df['identifier'].unique())
    
    # Por defecto seleccionamos gliquid y gliquid_test si existen
    default_selection = [p for p in all_pools if 'gliquid' in p]
    
    selected_pools = st.multiselect(
        "Selecciona los pools a visualizar en el gráfico:",
        options=all_pools,
        default=default_selection
    )

    if selected_pools:
        # Filtramos el dataframe final para el gráfico
        chart_df = analysis_df[analysis_df['identifier'].isin(selected_pools)]

        # 3. Gráfico
        fig = px.line(
            chart_df,
            x='date',
            y='apy24h',
            color='identifier',
            title="Evolución Histórica del APY",
            labels={'date': 'Fecha', 'apy24h': 'APY (%)', 'identifier': 'Pool'},
            markers=True
        )
        fig.update_layout(legend_title_text='Pools')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Selecciona al menos un pool para generar el gráfico.")

