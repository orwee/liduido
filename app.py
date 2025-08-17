import streamlit as st
import pandas as pd
import plotly.express as px

# --- Configuración de la página ---
st.set_page_config(
    page_title="Análisis Histórico de APY",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Análisis Histórico de APY desde GitHub")
st.markdown("Esta aplicación carga datos históricos desde un repositorio de GitHub y visualiza la evolución del APY de diferentes pools.")

# --- Funciones de Carga y Procesamiento ---

@st.cache_data(ttl=600) # Cache para no recargar en cada interacción
def load_all_data(github_repo_url, filenames):
    """
    Carga múltiples archivos CSV desde un repositorio de GitHub y los combina.
    """
    all_data = []
    base_url = github_repo_url.replace("github.com", "raw.githubusercontent.com") + "/main/data/"

    for filename in filenames:
        file_url = base_url + filename
        try:
            # Leemos el CSV y extraemos la fecha del nombre del archivo
            df = pd.read_csv(file_url)
            date_str = filename.replace('.csv', '')
            # Convertimos la fecha a un formato estándar (YYYY-MM-DD)
            df['date'] = pd.to_datetime(date_str, format='%d-%m-%y')
            all_data.append(df)
        except Exception as e:
            st.warning(f"No se pudo cargar el archivo: {filename}. Error: {e}")
    
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

    # Filtramos solo los datos históricos de gliquid
    gliquid_df = df[df['dex'] == 'gliquid'].copy()
    if gliquid_df.empty:
        st.info("No se encontraron datos para el DEX 'gliquid' para realizar la simulación.")
        return df

    # Creamos la versión de test
    gliquid_test_df = gliquid_df.copy()
    gliquid_test_df['dex'] = 'gliquid_test'
    
    # Recalculamos el APY con la nueva tier
    # Aseguramos que no haya división por cero
    gliquid_test_df['apy24h'] = gliquid_test_df.apply(
        lambda row: (new_tier * row['volume24h2'] / row['tvl']) * 365 if row['tvl'] > 0 else 0,
        axis=1
    )
    
    # Combinamos los datos originales con la simulación
    return pd.concat([df, gliquid_test_df], ignore_index=True)


# --- Interfaz de Usuario ---

# 1. Input para el repositorio de GitHub
st.subheader("1. Configuración del Repositorio")
repo_url = st.text_input(
    "URL del Repositorio de GitHub:",
    "https://github.com/tu_usuario/tu_repositorio"
)

# Lista de archivos a cargar. Puedes modificarla si añades más.
files_to_load = [
    "31-07-25.csv", "01-08-25.csv", "02-08-25.csv", "03-08-25.csv",
    "04-08-25.csv", "05-08-25.csv", "06-08-25.csv"
]

# 2. Slider para la simulación
st.subheader("2. Simulación para 'gliquid_test'")
simulated_tier = st.slider(
    "Selecciona el Fee Tier para la simulación de 'gliquid_test':",
    min_value=0.01, max_value=5.0, value=1.0, step=0.05, format="%.2f"
)

# --- Lógica Principal ---
if repo_url and repo_url != "https://github.com/tu_usuario/tu_repositorio":
    # Cargamos los datos
    historical_df = load_all_data(repo_url, files_to_load)

    if not historical_df.empty:
        # Ejecutamos la simulación
        analysis_df = run_simulation(historical_df, simulated_tier)
        
        # Creamos un identificador único para cada línea del gráfico
        analysis_df['identifier'] = analysis_df['pair'] + " (" + analysis_df['dex'] + ")"
        
        st.subheader("3. Análisis y Comparativa")
        
        # 3. Filtro para seleccionar qué pools mostrar
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

            # 4. Gráfico
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
else:
    st.info("Por favor, introduce la URL de tu repositorio de GitHub para cargar los datos.")

