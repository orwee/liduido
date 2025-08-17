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
    
    if not os.path.isdir(data_folder):
        st.error(f"Error: No se encontró la carpeta '{data_folder}'. Asegúrate de que exista en el mismo directorio que el script.")
        return pd.DataFrame()

    filenames = [f for f in os.listdir(data_folder) if f.endswith('.csv')]
    if not filenames:
        st.warning(f"No se encontraron archivos .csv en la carpeta '{data_folder}'.")
        return pd.DataFrame()

    for filename in filenames:
        file_path = os.path.join(data_folder, filename)
        try:
            df = pd.read_csv(file_path)
            date_str = filename.replace('.csv', '')
            df['date'] = pd.to_datetime(date_str, format='%d-%m-%y')
            all_data.append(df)
        except Exception as e:
            st.warning(f"No se pudo cargar o procesar el archivo: {filename}. Error: {e}")
    
    if not all_data:
        return pd.DataFrame()
        
    combined_df = pd.concat(all_data, ignore_index=True)
    return combined_df

def run_simulation(df, new_tier):
    """
    Crea una copia de los datos de 'gliquid', la renombra a 'gliquid_test'
    y recalcula el APY con el nuevo tier.
    """
    # CORRECCIÓN: Se usan los nombres de columna correctos del CSV
    gliquid_df = df[df['DEX'] == 'Gliquid'].copy() # Asumiendo que el nombre es 'Gliquid' con mayúscula
    if gliquid_df.empty:
        st.info("No se encontraron datos para el DEX 'Gliquid' para realizar la simulación.")
        return df

    gliquid_test_df = gliquid_df.copy()
    gliquid_test_df['DEX'] = 'gliquid_test'
    
    # CORRECCIÓN: Se usan los nombres de columna correctos del CSV para el cálculo
    gliquid_test_df['APY_24h'] = gliquid_test_df.apply(
        lambda row: (new_tier * row['Volume_24h'] / row['TVL']) * 365 if row['TVL'] > 0 else 0,
        axis=1
    )
    
    return pd.concat([df, gliquid_test_df], ignore_index=True)


# --- Interfaz de Usuario ---

st.subheader("1. Simulación para 'gliquid_test'")
simulated_tier = st.slider(
    "Selecciona el Fee Tier para la simulación de 'gliquid_test':",
    min_value=0.01, max_value=5.0, value=1.0, step=0.05, format="%.2f"
)

# --- Lógica Principal ---
historical_df = load_all_data()

if not historical_df.empty:
    # --- Verificación de Columnas ---
    # CORRECCIÓN: Se actualiza la lista con los nombres de columna correctos
    required_columns = ['Address', 'DEX', 'Volume_24h', 'TVL', 'APY_24h']
    missing_columns = [col for col in required_columns if col not in historical_df.columns]
    
    if missing_columns:
        st.error(f"Error: Faltan las siguientes columnas en tus archivos CSV: **{', '.join(missing_columns)}**.")
        st.info(f"Las columnas que se encontraron en tus archivos son: **{', '.join(historical_df.columns)}**")
        st.stop()

    # --- Continuación de la Lógica ---
    analysis_df = run_simulation(historical_df, simulated_tier)
    
    # CORRECCIÓN: Se usan los nombres de columna correctos para crear el identificador
    analysis_df['identifier'] = analysis_df['Address'].astype(str) + " (" + analysis_df['DEX'] + ")"
    
    st.subheader("2. Análisis y Comparativa")
    
    all_pools = sorted(analysis_df['identifier'].unique())
    
    # CORRECCIÓN: Se ajusta el filtro por defecto
    default_selection = [p for p in all_pools if 'Gliquid' in p or 'gliquid_test' in p]
    
    selected_pools = st.multiselect(
        "Selecciona los pools a visualizar en el gráfico:",
        options=all_pools,
        default=default_selection
    )

    if selected_pools:
        chart_df = analysis_df[analysis_df['identifier'].isin(selected_pools)]

        fig = px.line(
            chart_df,
            x='date',
            y='APY_24h', # CORRECCIÓN: Se usa la columna correcta para el eje Y
            color='identifier',
            title="Evolución Histórica del APY",
            labels={'date': 'Fecha', 'APY_24h': 'APY (%)', 'identifier': 'Address (DEX)'},
            markers=True
        )
        fig.update_layout(legend_title_text='Pools')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Selecciona al menos un pool para generar el gráfico.")

