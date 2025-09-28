import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import time
import requests
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

# Configuración de la página
st.set_page_config(
    page_title="Auditor Automático de Publicaciones",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
    <style>
    .main {
        padding: 0rem 1rem;
    }
    .stAlert {
        margin-top: 1rem;
    }
    div[data-testid="metric-container"] {
        background-color: #f0f2f6;
        border: 1px solid #c3c3c3;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0px;
    }
    .audit-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        color: white;
        margin-bottom: 2rem;
    }
    .price-ok {
        color: green;
        font-weight: bold;
    }
    .price-error {
        color: red;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# Título principal
st.markdown("""
    <div class="audit-header">
        <h1 style="text-align: center; color: white;">🤖 Sistema de Auditoría Automática</h1>
        <p style="text-align: center; color: white; margin-top: 10px;">
            Web Scraping Automático de Precios y Stock en Tiendas
        </p>
    </div>
    """, unsafe_allow_html=True)

# Inicializar estado de sesión
if 'audit_results' not in st.session_state:
    st.session_state.audit_results = None
if 'scraping_progress' not in st.session_state:
    st.session_state.scraping_progress = 0

# CONFIGURACIÓN DE TIENDAS Y SCRAPING
TIENDAS_CONFIG = {
    "Tienda Ciudad": {
        "base_url": "https://tiendaciudad.com.ar",
        "selector_precio": [
            "span.price",
            "span.precio-actual",
            "div.price-now",
            "meta[property='product:price:amount']"
        ],
        "selector_stock": [
            "span.stock-disponible",
            "div.availability",
            "meta[property='product:availability']"
        ],
        "formato_precio": "con_puntos",  # 15.000,00
        "columna_url": "URL Ciudad"
    },
    "ICBC": {
        "base_url": "https://mall.icbc.com.ar",
        "selector_precio": [
            "span.price-now",
            "div.precio-final",
            "span.price"
        ],
        "selector_stock": [
            "span.stock-qty",
            "div.stock-disponible"
        ],
        "formato_precio": "sin_puntos",  # 15000
        "columna_url": "URL ICBC"
    },
    "Supervielle": {
        "base_url": "https://tienda.supervielle.com.ar",
        "selector_precio": [
            "span.price",
            "div.precio"
        ],
        "selector_stock": [
            "div.stock",
            "span.disponibilidad"
        ],
        "formato_precio": "sin_puntos",
        "columna_url": "URL Supervielle"
    },
    "Galicia": {
        "base_url": "https://tienda.galicia.com.ar",
        "selector_precio": [
            "span.precio",
            "div.price-box"
        ],
        "selector_stock": [
            "span.stock",
            "div.availability"
        ],
        "formato_precio": "sin_puntos",
        "columna_url": "URL Galicia"
    },
    "Tienda BNA": {
        "base_url": "https://tiendabna.com.ar",
        "selector_precio": ["span.price"],
        "selector_stock": ["span.stock"],
        "formato_precio": "con_puntos",
        "columna_url": "URL BNA"
    },
    "Fravega": {
        "base_url": "https://www.fravega.com",
        "selector_precio": [
            "span.PriceLayout__Main",
            "span[data-test-id='price-value']"
        ],
        "selector_stock": ["button.AddToCart"],
        "formato_precio": "sin_puntos",
        "columna_url": "URL Fravega"
    },
    "Megatone": {
        "base_url": "https://www.megatone.net",
        "selector_precio": ["span.price"],
        "selector_stock": ["div.stock"],
        "formato_precio": "sin_puntos",
        "columna_url": "URL Megatone"
    }
}

# Lista de todas las tiendas
TODAS_LAS_TIENDAS = list(TIENDAS_CONFIG.keys())

class WebScraper:
    """Clase para hacer web scraping de las tiendas"""
    
    def __init__(self, tienda_config):
        self.config = tienda_config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def limpiar_precio(self, precio_texto, formato):
        """Limpia y convierte el precio a número"""
        if not precio_texto:
            return None
        
        # Eliminar símbolos de moneda y espacios
        precio_texto = re.sub(r'[$\s]', '', precio_texto)
        
        if formato == "con_puntos":
            # Formato: 15.000,00 o 15.000
            precio_texto = precio_texto.replace('.', '').replace(',', '.')
        else:
            # Formato: 15000 o 15000.00
            precio_texto = precio_texto.replace(',', '')
        
        try:
            return float(re.sub(r'[^\d.]', '', precio_texto))
        except:
            return None
    
    def scrape_url(self, url):
        """Scrapea una URL específica"""
        resultado = {
            'url': url,
            'precio_web': None,
            'stock_web': None,
            'error': None,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Buscar precio
            for selector in self.config['selector_precio']:
                if selector.startswith('meta'):
                    # Buscar en meta tags
                    meta = soup.find('meta', property=selector.split("'")[1])
                    if meta and meta.get('content'):
                        precio_texto = meta['content']
                        resultado['precio_web'] = self.limpiar_precio(precio_texto, self.config['formato_precio'])
                        break
                else:
                    elemento = soup.select_one(selector)
                    if elemento:
                        precio_texto = elemento.get_text(strip=True)
                        resultado['precio_web'] = self.limpiar_precio(precio_texto, self.config['formato_precio'])
                        break
            
            # Buscar stock
            for selector in self.config['selector_stock']:
                if selector.startswith('meta'):
                    meta = soup.find('meta', property=selector.split("'")[1])
                    if meta:
                        content = meta.get('content', '').lower()
                        resultado['stock_web'] = 'Si' if 'instock' in content or 'available' in content else 'No'
                        break
                else:
                    elemento = soup.select_one(selector)
                    if elemento:
                        texto = elemento.get_text(strip=True).lower()
                        if 'sin stock' in texto or 'agotado' in texto or 'no disponible' in texto:
                            resultado['stock_web'] = 'No'
                        elif 'disponible' in texto or 'stock' in texto:
                            resultado['stock_web'] = 'Si'
                        else:
                            # Si existe el botón de agregar al carrito, hay stock
                            resultado['stock_web'] = 'Si' if elemento else 'No'
                        break
            
            # Si no se encontró stock, buscar botón de compra
            if not resultado['stock_web']:
                buy_button = soup.select_one('button[class*="add"], button[class*="comprar"], button[class*="cart"]')
                resultado['stock_web'] = 'Si' if buy_button else 'Desconocido'
            
        except requests.exceptions.RequestException as e:
            resultado['error'] = f"Error de conexión: {str(e)}"
        except Exception as e:
            resultado['error'] = f"Error: {str(e)}"
        
        return resultado

def realizar_scraping(df_tienda, tienda_config, progress_bar, status_text):
    """Realiza el scraping de todas las URLs de una tienda"""
    scraper = WebScraper(tienda_config)
    resultados = []
    total_urls = len(df_tienda)
    
    # Usar ThreadPoolExecutor para scraping paralelo (más rápido)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scraper.scrape_url, row['url']): idx 
                  for idx, row in df_tienda.iterrows() if pd.notna(row.get('url'))}
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            idx = futures[future]
            
            # Actualizar progreso
            progress = int((completed / total_urls) * 100)
            progress_bar.progress(progress)
            status_text.text(f"Escaneando URL {completed}/{total_urls}...")
            
            try:
                resultado = future.result()
                resultado['idx'] = idx
                resultados.append(resultado)
            except Exception as e:
                resultados.append({
                    'idx': idx,
                    'url': df_tienda.loc[idx, 'url'],
                    'error': str(e)
                })
    
    return resultados

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuración de Auditoría")
    
    # Selección de tienda
    st.subheader("🏪 Seleccionar Tienda")
    selected_store = st.selectbox(
        "Tienda a auditar:",
        TODAS_LAS_TIENDAS,
        help="Selecciona la tienda que deseas auditar automáticamente"
    )
    
    # Configuración de umbrales
    st.markdown("---")
    st.subheader("📊 Parámetros de Control")
    
    price_threshold = st.slider(
        "Variación de precio máxima (%)",
        min_value=1,
        max_value=20,
        value=5,
        help="Diferencia máxima aceptable entre precio web y base de datos"
    )
    
    max_productos = st.number_input(
        "Máximo de productos a escanear",
        min_value=10,
        max_value=1000,
        value=100,
        help="Limitar cantidad para pruebas rápidas"
    )
    
    st.markdown("---")
    
    # Información de la tienda seleccionada
    if selected_store in TIENDAS_CONFIG:
        config = TIENDAS_CONFIG[selected_store]
        st.info(f"""
        📋 **Configuración de {selected_store}**
        
        • Base URL: {config['base_url']}
        • Columna URL: {config['columna_url']}
        • Formato precio: {config['formato_precio']}
        """)
    
    # Modo de operación
    st.markdown("---")
    st.subheader("🔧 Modo de Operación")
    
    modo_operacion = st.radio(
        "Seleccionar modo:",
        ["Auditoría Rápida (primeros 10)", "Auditoría Completa", "Modo Prueba (simular)"],
        help="Rápida para verificar que funcione, Completa para todos los productos"
    )

# Área principal
st.header(f"🔍 Auditoría Automática - {selected_store}")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📁 Cargar y Ejecutar", "📊 Resultados", "📈 Dashboard", "⚙️ Configuración"])

with tab1:
    st.markdown("### 1️⃣ Cargar Archivo Maestro")
    
    # Cargar archivo
    uploaded_file = st.file_uploader(
        "Cargar Auditoria General.xlsx",
        type=['xlsx', 'xls'],
        help="Tu archivo maestro con SKUs, URLs, precios y stock correctos"
    )
    
    if uploaded_file:
        try:
            # Cargar el archivo
            df_maestro = pd.read_excel(uploaded_file)
            
            st.success(f"✅ Archivo cargado: {len(df_maestro)} productos totales")
            
            # Mostrar columnas disponibles
            with st.expander("Ver estructura del archivo"):
                st.write("**Columnas detectadas:**")
                cols = df_maestro.columns.tolist()
                col1, col2, col3 = st.columns(3)
                for i, col in enumerate(cols):
                    if i % 3 == 0:
                        col1.write(f"• {col}")
                    elif i % 3 == 1:
                        col2.write(f"• {col}")
                    else:
                        col3.write(f"• {col}")
                
                st.write(f"\n**Total de filas:** {len(df_maestro)}")
            
            # Identificar columnas relevantes
            st.markdown("### 2️⃣ Mapeo de Columnas")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Buscar columna de URL automáticamente
                url_column = None
                columna_esperada = TIENDAS_CONFIG[selected_store]['columna_url']
                
                if columna_esperada in df_maestro.columns:
                    url_column = columna_esperada
                    st.success(f"✅ Columna URL detectada: {url_column}")
                else:
                    # Buscar alternativas
                    posibles = [col for col in df_maestro.columns if 'url' in col.lower() or selected_store.lower() in col.lower()]
                    if posibles:
                        url_column = st.selectbox("Seleccionar columna de URLs:", posibles)
                    else:
                        url_column = st.selectbox("Seleccionar columna de URLs:", df_maestro.columns)
                
                # Columna de precio maestro
                precio_columns = [col for col in df_maestro.columns if 'precio' in col.lower() or 'price' in col.lower()]
                if precio_columns:
                    precio_column = st.selectbox("Columna de Precio Correcto:", precio_columns)
                else:
                    precio_column = st.selectbox("Columna de Precio Correcto:", df_maestro.columns)
            
            with col2:
                # Columna de SKU
                sku_columns = [col for col in df_maestro.columns if 'sku' in col.lower() or 'codigo' in col.lower() or 'id' in col.lower()]
                if sku_columns:
                    sku_column = st.selectbox("Columna de SKU/ID:", sku_columns)
                else:
                    sku_column = st.selectbox("Columna de SKU/ID:", df_maestro.columns)
                
                # Columna de stock
                stock_columns = [col for col in df_maestro.columns if 'stock' in col.lower() or 'cantidad' in col.lower()]
                if stock_columns:
                    stock_column = st.selectbox("Columna de Stock:", stock_columns)
                else:
                    stock_column = st.selectbox("Columna de Stock:", df_maestro.columns)
            
            # Filtrar solo productos de la tienda seleccionada (que tengan URL)
            df_tienda = df_maestro[df_maestro[url_column].notna()].copy()
            df_tienda = df_tienda.rename(columns={
                url_column: 'url',
                precio_column: 'precio_maestro',
                sku_column: 'sku',
                stock_column: 'stock_maestro'
            })
            
            # Aplicar límite según modo
            if modo_operacion == "Auditoría Rápida (primeros 10)":
                df_tienda = df_tienda.head(10)
            elif modo_operacion == "Auditoría Completa":
                df_tienda = df_tienda.head(max_productos)
            
            st.info(f"📋 Productos de {selected_store} con URL: {len(df_tienda)}")
            
            # Vista previa
            with st.expander("Ver productos a auditar"):
                st.dataframe(
                    df_tienda[['sku', 'url', 'precio_maestro', 'stock_maestro']].head(10),
                    use_container_width=True
                )
            
            # Botón de ejecutar auditoría
            st.markdown("### 3️⃣ Ejecutar Auditoría")
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button(f"🚀 Iniciar Auditoría Automática", type="primary", use_container_width=True):
                    
                    if modo_operacion == "Modo Prueba (simular)":
                        # Modo simulación para pruebas
                        st.warning("🧪 Ejecutando en modo prueba (datos simulados)")
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        # Simular resultados
                        resultados = []
                        for idx, row in df_tienda.iterrows():
                            # Simular variación de precio aleatoria
                            variacion = np.random.uniform(-10, 10)
                            precio_web = row['precio_maestro'] * (1 + variacion/100)
                            
                            resultados.append({
                                'idx': idx,
                                'url': row['url'],
                                'precio_web': precio_web,
                                'stock_web': np.random.choice(['Si', 'No', 'Si', 'Si']),  # 75% con stock
                                'error': None if np.random.random() > 0.1 else "Error simulado",
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            })
                            
                            progress_bar.progress((idx + 1) / len(df_tienda))
                            status_text.text(f"Simulando producto {idx + 1}/{len(df_tienda)}")
                            time.sleep(0.1)  # Pausa para efecto visual
                        
                        progress_bar.empty()
                        status_text.empty()
                        
                    else:
                        # Modo real con web scraping
                        st.warning("🌐 Iniciando web scraping real...")
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        # Realizar scraping
                        tienda_config = TIENDAS_CONFIG[selected_store]
                        resultados = realizar_scraping(df_tienda, tienda_config, progress_bar, status_text)
                        
                        progress_bar.empty()
                        status_text.empty()
                    
                    # Procesar resultados
                    st.success(f"✅ Auditoría completada: {len(resultados)} productos analizados")
                    
                    # Agregar resultados al dataframe
                    for resultado in resultados:
                        idx = resultado['idx']
                        df_tienda.loc[idx, 'precio_web'] = resultado.get('precio_web')
                        df_tienda.loc[idx, 'stock_web'] = resultado.get('stock_web')
                        df_tienda.loc[idx, 'error_scraping'] = resultado.get('error')
                        df_tienda.loc[idx, 'timestamp'] = resultado.get('timestamp')
                    
                    # Calcular variaciones
                    df_tienda['variacion_precio_%'] = ((df_tienda['precio_web'] - df_tienda['precio_maestro']) / df_tienda['precio_maestro'] * 100).round(2)
                    df_tienda['precio_ok'] = df_tienda['variacion_precio_%'].abs() <= price_threshold
                    df_tienda['requiere_accion'] = (~df_tienda['precio_ok']) | (df_tienda['stock_web'] == 'No')
                    
                    # Guardar en sesión
                    st.session_state.audit_results = df_tienda
                    
                    # Mostrar resumen rápido
                    st.markdown("### 📊 Resumen de Resultados")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        total = len(df_tienda)
                        st.metric("Total Auditados", total)
                    
                    with col2:
                        errores_precio = len(df_tienda[~df_tienda['precio_ok']])
                        st.metric("Errores de Precio", errores_precio, 
                                 delta=f"{(errores_precio/total*100):.1f}%" if total > 0 else "0%")
                    
                    with col3:
                        sin_stock = len(df_tienda[df_tienda['stock_web'] == 'No'])
                        st.metric("Sin Stock", sin_stock,
                                 delta=f"{(sin_stock/total*100):.1f}%" if total > 0 else "0%")
                    
                    with col4:
                        errores_scraping = len(df_tienda[df_tienda['error_scraping'].notna()])
                        st.metric("Errores Técnicos", errores_scraping)
                    
                    st.info("💡 Ve a la pestaña 'Resultados' para ver el detalle completo")
            
        except Exception as e:
            st.error(f"Error al procesar el archivo: {str(e)}")

with tab2:
    st.markdown("### 📊 Resultados Detallados de Auditoría")
    
    if st.session_state.audit_results is not None:
        df_results = st.session_state.audit_results
        
        # Filtros
        col1, col2, col3 = st.columns(3)
        
        with col1:
            filtro = st.selectbox(
                "Filtrar por:",
                ["Todos", "Solo errores de precio", "Solo sin stock", "Requieren acción"]
            )
        
        with col2:
            orden = st.selectbox(
                "Ordenar por:",
                ["Variación de precio", "SKU", "Stock"]
            )
        
        with col3:
            if st.button("🔄 Refrescar"):
                st.rerun()
        
        # Aplicar filtros
        df_filtrado = df_results.copy()
        
        if filtro == "Solo errores de precio":
            df_filtrado = df_filtrado[~df_filtrado['precio_ok']]
        elif filtro == "Solo sin stock":
            df_filtrado = df_filtrado[df_filtrado['stock_web'] == 'No']
        elif filtro == "Requieren acción":
            df_filtrado = df_filtrado[df_filtrado['requiere_accion']]
        
        # Ordenar
        if orden == "Variación de precio":
            df_filtrado = df_filtrado.sort_values('variacion_precio_%', ascending=False, key=lambda x: x.abs())
        elif orden == "SKU":
            df_filtrado = df_filtrado.sort_values('sku')
        elif orden == "Stock":
            df_filtrado = df_filtrado.sort_values('stock_web')
        
        # Mostrar tabla con formato
        st.dataframe(
            df_filtrado[[
                'sku', 
                'precio_maestro', 
                'precio_web', 
                'variacion_precio_%',
                'precio_ok',
                'stock_maestro',
                'stock_web',
                'requiere_accion',
                'url'
            ]].style.applymap(
                lambda x: 'background-color: #ffcccc' if x == False else 'background-color: #ccffcc' if x == True else '',
                subset=['precio_ok']
            ).applymap(
                lambda x: 'background-color: #ffcccc' if x == 'No' else '',
                subset=['stock_web']
            ).format({
                'precio_maestro': '${:,.0f}',
                'precio_web': '${:,.0f}',
                'variacion_precio_%': '{:.1f}%'
            }),
            use_container_width=True,
            height=500
        )
        
        # Exportar resultados
        st.markdown("### 💾 Exportar Resultados")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Excel completo
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_results.to_excel(writer, sheet_name='Auditoría Completa', index=False)
                
                # Hoja de errores
                df_errores = df_filtrado[df_filtrado['requiere_accion']]
                if not df_errores.empty:
                    df_errores.to_excel(writer, sheet_name='Requieren Acción', index=False)
            
            output.seek(0)
            
            st.download_button(
                label="📊 Descargar Excel Completo",
                data=output,
                file_name=f"Auditoria_{selected_store}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with col2:
            # CSV de errores
            csv = df_filtrado[df_filtrado['requiere_accion']].to_csv(index=False)
            st.download_button(
                label="📄 Descargar Solo Errores (CSV)",
                data=csv,
                file_name=f"Errores_{selected_store}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        
        with col3:
            # Reporte resumen
            resumen = f"""
REPORTE DE AUDITORÍA - {selected_store}
Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}
=====================================

RESUMEN:
- Total de productos auditados: {len(df_results)}
- Errores de precio: {len(df_results[~df_results['precio_ok']])}
- Productos sin stock: {len(df_results[df_results['stock_web'] == 'No'])}
- Requieren acción inmediata: {len(df_results[df_results['requiere_accion']])}

PRODUCTOS CON ERRORES DE PRECIO:
{df_results[~df_results['precio_ok']][['sku', 'precio_maestro', 'precio_web', 'variacion_precio_%']].to_string()}

PRODUCTOS SIN STOCK:
{df_results[df_results['stock_web'] == 'No'][['sku', 'url']].to_string()}
            """
            
            st.download_button(
                label="📝 Descargar Reporte TXT",
                data=resumen,
                file_name=f"Reporte_{selected_store}_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain"
            )
    
    else:
        st.info("👆 Primero ejecuta una auditoría en la pestaña 'Cargar y Ejecutar'")

with tab3:
    st.markdown("### 📈 Dashboard de Auditoría")
    
    if st.session_state.audit_results is not None:
        df = st.session_state.audit_results
        
        # Métricas principales
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            accuracy = (len(df[df['precio_ok']]) / len(df) * 100) if len(df) > 0 else 0
            st.metric(
                "Precisión de Precios",
                f"{accuracy:.1f}%",
                delta="Bueno" if accuracy > 90 else "Regular" if accuracy > 80 else "Malo"
            )
        
        with col2:
            disponibilidad = (len(df[df['stock_web'] == 'Si']) / len(df) * 100) if len(df) > 0 else 0
            st.metric(
                "Disponibilidad",
                f"{disponibilidad:.1f}%",
                delta="Óptimo" if disponibilidad > 95 else "Aceptable" if disponibilidad > 85 else "Crítico"
            )
        
        with col3:
            variacion_promedio = df['variacion_precio_%'].abs().mean() if not df.empty else 0
            st.metric(
                "Variación Promedio",
                f"{variacion_promedio:.1f}%",
                delta="Excelente" if variacion_promedio < 2 else "Bueno" if variacion_promedio < 5 else "Alto"
            )
        
        with col4:
            health_score = ((accuracy * 0.6) + (disponibilidad * 0.4))
            st.metric(
                "Health Score",
                f"{health_score:.0f}/100",
                delta="⭐" if health_score > 90 else "✓" if health_score > 75 else "⚠️"
            )
        
        # Gráficos
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Gráfico de distribución de variaciones
            fig_hist = px.histogram(
                df[df['variacion_precio_%'].notna()],
                x='variacion_precio_%',
                title='Distribución de Variaciones de Precio',
                labels={'variacion_precio_%': 'Variación (%)', 'count': 'Cantidad'},
                color_discrete_sequence=['#764ba2']
            )
            fig_hist.add_vline(x=-price_threshold, line_dash="dash", line_color="red")
            fig_hist.add_vline(x=price_threshold, line_dash="dash", line_color="red")
            st.plotly_chart(fig_hist, use_container_width=True)
        
        with col2:
            # Gráfico de pie de estados
            estados = pd.DataFrame({
                'Estado': ['Precio OK', 'Error Precio', 'Sin Stock', 'OK Total'],
                'Cantidad': [
                    len(df[df['precio_ok']]),
                    len(df[~df['precio_ok']]),
                    len(df[df['stock_web'] == 'No']),
                    len(df[(df['precio_ok']) & (df['stock_web'] != 'No')])
                ]
            })
            
            fig_pie = px.pie(
                estados,
                values='Cantidad',
                names='Estado',
                title='Estado de Productos',
                color_discrete_map={
                    'OK Total': '#00CC00',
                    'Precio OK': '#90EE90',
                    'Error Precio': '#FFA500',
                    'Sin Stock': '#FF4444'
                }
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        # Top productos con mayor variación
        st.markdown("---")
        st.subheader("🔴 Top 10 Productos con Mayor Variación")
        
        top_variaciones = df.nlargest(10, 'variacion_precio_%')[['sku', 'precio_maestro', 'precio_web', 'variacion_precio_%', 'url']]
        
        st.dataframe(
            top_variaciones.style.format({
                'precio_maestro': '${:,.0f}',
                'precio_web': '${:,.0f}',
                'variacion_precio_%': '{:.1f}%'
            }).background_gradient(subset=['variacion_precio_%'], cmap='Reds'),
            use_container_width=True
        )
        
        # Timeline de auditoría
        if 'timestamp' in df.columns:
            st.markdown("---")
            st.subheader("📅 Timeline de Auditoría")
            st.info(f"Última actualización: {df['timestamp'].iloc[0] if not df.empty else 'N/A'}")
    
    else:
        st.info("👆 Primero ejecuta una auditoría para ver el dashboard")

with tab4:
    st.markdown("### ⚙️ Configuración de Scraping")
    
    st.warning("⚠️ Esta sección es para usuarios avanzados")
    
    # Mostrar configuración actual
    st.subheader(f"Configuración actual para {selected_store}")
    
    if selected_store in TIENDAS_CONFIG:
        config = TIENDAS_CONFIG[selected_store]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Selectores de Precio:**")
            for selector in config['selector_precio']:
                st.code(selector)
            
            st.markdown("**Formato de Precio:**")
            st.info(config['formato_precio'])
        
        with col2:
            st.markdown("**Selectores de Stock:**")
            for selector in config['selector_stock']:
                st.code(selector)
            
            st.markdown("**URL Base:**")
            st.info(config['base_url'])
    
    # Instrucciones para agregar nuevas tiendas
    with st.expander("📚 Cómo agregar una nueva tienda"):
        st.markdown("""
        Para agregar una nueva tienda, necesitas:
        
        1. **Inspeccionar el HTML** de la página del producto
        2. **Identificar los selectores CSS** para precio y stock
        3. **Determinar el formato** del precio (con o sin puntos/comas)
        4. **Agregar la configuración** al diccionario TIENDAS_CONFIG
        
        Ejemplo:
        ```python
        "NuevaTienda": {
            "base_url": "https://nuevatienda.com",
            "selector_precio": ["span.price", "div.precio"],
            "selector_stock": ["span.stock"],
            "formato_precio": "con_puntos",
            "columna_url": "URL NuevaTienda"
        }
        ```
        """)
    
    # Test de scraping
    st.markdown("---")
    st.subheader("🧪 Test de Scraping")
    
    test_url = st.text_input("URL de prueba:", placeholder="https://tienda.com/producto")
    
    if st.button("Probar Scraping") and test_url:
        with st.spinner("Probando..."):
            scraper = WebScraper(TIENDAS_CONFIG[selected_store])
            resultado = scraper.scrape_url(test_url)
            
            if resultado['error']:
                st.error(f"Error: {resultado['error']}")
            else:
                st.success("✅ Scraping exitoso!")
                st.json(resultado)

# Footer
st.markdown("---")
st.markdown(
    f"""
    <div style='text-align: center; color: gray; padding: 20px;'>
        <p>🤖 Sistema de Auditoría Automática con Web Scraping v1.0 | 
        {selected_store} | 
        {datetime.now().strftime("%d/%m/%Y %H:%M")}</p>
        <p style='font-size: 12px;'>⚡ Powered by BeautifulSoup + Requests</p>
    </div>
    """,
    unsafe_allow_html=True
)
