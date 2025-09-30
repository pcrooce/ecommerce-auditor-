import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import time
import requests
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sqlite3
import os
from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils.dataframe import dataframe_to_rows
except ImportError:
    st.error("Por favor instala openpyxl: pip install openpyxl")

# Configuración de la página
st.set_page_config(
    page_title="Auditor Automático de Publicaciones",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado mejorado
st.markdown("""
    <style>
    /* Estilos generales */
    .main {
        padding: 0rem 1rem;
    }
    
    /* Header principal con gradiente */
    .audit-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2.5rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        text-align: center;
    }
    
    /* Métricas personalizadas */
    div[data-testid="metric-container"] {
        background-color: #f8f9fa;
        border: 2px solid #e9ecef;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0px;
        transition: transform 0.2s;
    }
    
    div[data-testid="metric-container"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    
    /* Botones mejorados */
    .stButton > button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 600;
        border-radius: 8px;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
    }
    
    /* Tabs mejorados */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f8f9fa;
        padding: 4px;
        border-radius: 10px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        color: #495057;
        font-weight: 500;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #667eea;
        color: white;
    }
    
    /* Progress bar personalizado */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Headers de sección */
    .section-header {
        background: linear-gradient(90deg, #f8f9fa 0%, #e9ecef 100%);
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 4px solid #667eea;
    }
    
    /* Indicadores de cambio de precio */
    .price-up {
        color: #e74c3c;
        font-weight: bold;
    }
    
    .price-down {
        color: #27ae60;
        font-weight: bold;
    }
    
    .price-equal {
        color: #95a5a6;
    }
    </style>
    """, unsafe_allow_html=True)

# Título principal
st.markdown("""
    <div class="audit-header">
        <h1 style="text-align: center; color: white;">🤖 Sistema de Auditoría Automática</h1>
        <p style="text-align: center; color: white; margin-top: 10px;">
            Verificación automática de precios en tiendas online con historial
        </p>
    </div>
    """, unsafe_allow_html=True)

# Inicializar estado de sesión
if 'audit_results' not in st.session_state:
    st.session_state.audit_results = None
if 'db_initialized' not in st.session_state:
    st.session_state.db_initialized = False

# CONFIGURACIÓN DE BASE DE DATOS
DB_PATH = "auditoria_historial.db"

def init_database():
    """Inicializa la base de datos SQLite con las tablas necesarias"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabla de auditorías generales
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auditorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tienda TEXT NOT NULL,
            total_productos INTEGER,
            productos_ok INTEGER,
            productos_error INTEGER,
            productos_no_disponibles INTEGER,
            precision_porcentaje REAL,
            modo_operacion TEXT,
            usuario TEXT DEFAULT 'default'
        )
    ''')
    
    # Tabla de escaneos individuales
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS escaneos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id INTEGER,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tienda TEXT,
            sku TEXT,
            precio_maestro REAL,
            precio_web REAL,
            variacion_porcentaje REAL,
            precio_ok BOOLEAN,
            estado_producto TEXT,
            url TEXT,
            FOREIGN KEY (auditoria_id) REFERENCES auditorias(id)
        )
    ''')
    
    # Tabla de historial de precios (para tracking a largo plazo)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_precios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT,
            tienda TEXT,
            precio REAL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fuente TEXT DEFAULT 'web'
        )
    ''')
    
    # Tabla de ajustes sugeridos/realizados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ajustes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT,
            tienda TEXT,
            precio_anterior REAL,
            precio_sugerido REAL,
            fecha_deteccion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_ajuste TIMESTAMP,
            estado TEXT DEFAULT 'pendiente',
            notas TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    st.session_state.db_initialized = True

# Inicializar DB si no existe
if not st.session_state.db_initialized:
    init_database()

def guardar_auditoria(df_results, tienda, modo_operacion):
    """Guarda los resultados de la auditoría en la base de datos"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Calcular métricas
    total = len(df_results)
    productos_ok = len(df_results[df_results['precio_ok'] == True])
    productos_error = len(df_results[(df_results['precio_ok'] == False) & df_results['precio_web'].notna()])
    productos_no_disponibles = len(df_results[df_results['estado_producto'] == 'No disponible en el front'])
    
    precision = (productos_ok / (productos_ok + productos_error) * 100) if (productos_ok + productos_error) > 0 else 0
    
    # Insertar auditoría general
    cursor.execute('''
        INSERT INTO auditorias (tienda, total_productos, productos_ok, productos_error, 
                               productos_no_disponibles, precision_porcentaje, modo_operacion)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (tienda, total, productos_ok, productos_error, productos_no_disponibles, precision, modo_operacion))
    
    auditoria_id = cursor.lastrowid
    
    # Insertar escaneos individuales
    for _, row in df_results.iterrows():
        cursor.execute('''
            INSERT INTO escaneos (auditoria_id, tienda, sku, precio_maestro, precio_web, 
                                 variacion_porcentaje, precio_ok, estado_producto, url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (auditoria_id, tienda, row.get('sku'), row.get('precio_maestro'), 
              row.get('precio_web'), row.get('variacion_precio_%'), 
              row.get('precio_ok'), row.get('estado_producto'), row.get('url')))
        
        # Guardar en historial de precios si hay precio web
        if pd.notna(row.get('precio_web')):
            cursor.execute('''
                INSERT INTO historial_precios (sku, tienda, precio)
                VALUES (?, ?, ?)
            ''', (row.get('sku'), tienda, row.get('precio_web')))
    
    conn.commit()
    conn.close()
    
    return auditoria_id

def obtener_precio_anterior(sku, tienda):
    """Obtiene el último precio escaneado para un SKU y tienda"""
    conn = sqlite3.connect(DB_PATH)
    query = '''
        SELECT precio_web, fecha, variacion_porcentaje
        FROM escaneos
        WHERE sku = ? AND tienda = ? AND precio_web IS NOT NULL
        ORDER BY fecha DESC
        LIMIT 2
    '''
    df = pd.read_sql_query(query, conn, params=(sku, tienda))
    conn.close()
    
    if len(df) >= 2:
        return {
            'precio': df.iloc[1]['precio_web'],
            'fecha': df.iloc[1]['fecha'],
            'variacion_anterior': df.iloc[1]['variacion_porcentaje']
        }
    return None

def obtener_historial_sku(sku, tienda):
    """Obtiene el historial completo de precios para un SKU"""
    conn = sqlite3.connect(DB_PATH)
    query = '''
        SELECT fecha, precio_web as precio, variacion_porcentaje
        FROM escaneos
        WHERE sku = ? AND tienda = ? AND precio_web IS NOT NULL
        ORDER BY fecha DESC
        LIMIT 30
    '''
    df = pd.read_sql_query(query, conn, params=(sku, tienda))
    conn.close()
    return df

def obtener_resumen_auditorias():
    """Obtiene un resumen de todas las auditorías realizadas"""
    conn = sqlite3.connect(DB_PATH)
    query = '''
        SELECT 
            fecha,
            tienda,
            total_productos,
            productos_ok,
            productos_error,
            productos_no_disponibles,
            precision_porcentaje,
            modo_operacion
        FROM auditorias
        ORDER BY fecha DESC
        LIMIT 50
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# CONFIGURACIÓN DE TIENDAS Y MAPEO DE COLUMNAS
TIENDAS_CONFIG = {
    "ICBC": {
        "base_url": "https://mall.icbc.com.ar",
        "columnas_busqueda": ["ICBC", "icbc", "Icbc"],
        "formato_precio_web": "496.569",  # Sin símbolo $, con punto como separador de miles
        "columna_url": "URL ICBC",
        "selector_precio": [
            "p.monto",  # Selector correcto para ICBC
            "span.price",
            "div.precio-final"
        ],
        "selector_no_disponible": [
            "li:contains('This product is no longer available')",
            "div.product-unavailable",
            "div.error-404"
        ]
    },
    "Supervielle": {
        "base_url": "https://www.clubsupervielle.com.ar",
        "columnas_busqueda": ["Supervielle", "supervielle", "SUPERVIELLE", "Sup"],
        "formato_precio_web": "505.009,00",  # Con punto para miles y coma para decimales
        "columna_url": "URL Supervielle",
        "selector_precio": [
            "span#our_price_display",  # Selector correcto para Supervielle
            "span.price[itemprop='price']",
            "span.price"
        ],
        "selector_no_disponible": [
            "li:contains('This product is no longer available')",
            "div.product-unavailable"
        ]
    },
    "Galicia": {
        "base_url": "https://tienda.galicia.ar",
        "columnas_busqueda": ["Galicia", "galicia", "GALICIA", "Gal"],
        "formato_precio_web": "570.659,00",  # Con punto para miles y coma para decimales
        "columna_url": "URL Galicia",
        "selector_precio": [
            "div.productPrice span",  # Selector para el span dentro del precio
            "span.productPrice",
            "div.price-wrapper span",
            ".productPrice span"
        ],
        "selector_no_disponible": [
            "li:contains('This product is no longer available')",
            "div.product-unavailable"
        ]
    },
    "Tienda Ciudad": {
        "base_url": "https://tiendaciudad.com.ar",
        "columnas_busqueda": ["Ciudad", "ciudad", "CIUDAD", "Cdad"],
        "formato_precio_web": "15.000,00",
        "columna_url": "URL Ciudad",
        "selector_precio": ["span.price", "span.precio-actual", "div.price-now"],
        "selector_no_disponible": ["li:contains('This product is no longer available')"]
    },
    "Tienda BNA": {
        "base_url": "https://tiendabna.com.ar",
        "columnas_busqueda": ["BNA", "bna", "Bna"],
        "formato_precio_web": "15.000,00",
        "columna_url": "URL BNA",
        "selector_precio": ["span.price"],
        "selector_no_disponible": ["li:contains('This product is no longer available')"]
    },
    "Fravega": {
        "base_url": "https://www.fravega.com",
        "columnas_busqueda": ["Fravega", "fravega", "FRAVEGA", "Fvg", "FVG"],
        "formato_precio_web": "15000",
        "columna_url": "URL Fravega",
        "selector_precio": ["span.PriceLayout__Main", "span[data-test-id='price-value']"],
        "selector_no_disponible": ["div.product-not-found"]
    },
    "Megatone": {
        "base_url": "https://www.megatone.net",
        "columnas_busqueda": ["Megatone", "megatone", "MEGATONE", "Meg", "MEG", "Mgt", "MGT"],
        "formato_precio_web": "15000",
        "columna_url": "URL Megatone",
        "selector_precio": ["span.price"],
        "selector_no_disponible": ["div.product-not-found"]
    }
}

# Lista de todas las tiendas
TODAS_LAS_TIENDAS = list(TIENDAS_CONFIG.keys())

def detectar_columnas_automaticamente(df, tienda):
    """Detecta automáticamente las columnas según la tienda seleccionada"""
    config = TIENDAS_CONFIG[tienda]
    columnas_detectadas = {
        'url': None,
        'precio': None,
        'sku': None
    }
    
    # Buscar columna de URL para la tienda específica
    for col in df.columns:
        # Buscar URL
        for busqueda in config['columnas_busqueda']:
            if busqueda in col:
                columnas_detectadas['url'] = col
                break
        
        # Buscar precio (que contenga la palabra de la tienda)
        if columnas_detectadas['precio'] is None:
            for busqueda in config['columnas_busqueda']:
                if busqueda in col and any(word in col.lower() for word in ['precio', 'price']):
                    columnas_detectadas['precio'] = col
                    break
    
    # Buscar SKU generales
    for col in df.columns:
        if columnas_detectadas['sku'] is None and any(word in col.lower() for word in ['sku', 'codigo', 'código', 'id']):
            columnas_detectadas['sku'] = col
    
    return columnas_detectadas

def limpiar_y_convertir_precio(valor):
    """Convierte cualquier formato de precio a número"""
    if pd.isna(valor):
        return np.nan
    
    # Convertir a string
    precio_str = str(valor)
    
    # Eliminar símbolos de moneda y espacios
    precio_str = precio_str.replace('$', '').replace(' ', '').strip()
    
    # IMPORTANTE: Detectar formato argentino vs formato internacional
    # Si tiene punto Y coma, es formato argentino (1.234,56)
    if '.' in precio_str and ',' in precio_str:
        # Formato argentino: punto para miles, coma para decimales
        precio_str = precio_str.replace('.', '').replace(',', '.')
    # Si solo tiene coma, podría ser decimal o miles
    elif ',' in precio_str:
        # Si la coma está seguida de 2 dígitos, es decimal
        if re.search(r',\d{2}$', precio_str):
            precio_str = precio_str.replace(',', '.')
        else:
            # Si no, es separador de miles
            precio_str = precio_str.replace(',', '')
    # Si solo tiene punto, verificar si es decimal o miles
    elif '.' in precio_str:
        # Si el punto está seguido de 3 dígitos, es separador de miles
        if re.search(r'\.\d{3}', precio_str):
            precio_str = precio_str.replace('.', '')
        # Si está seguido de 2 dígitos al final, es decimal
        elif re.search(r'\.\d{2}$', precio_str):
            pass  # Dejar el punto como está (decimal)
        else:
            # Para casos como 486.199 que es claramente miles
            precio_str = precio_str.replace('.', '')
    
    # Eliminar cualquier caracter no numérico excepto el punto decimal
    precio_str = re.sub(r'[^\d.]', '', precio_str)
    
    try:
        return float(precio_str)
    except:
        return np.nan

def crear_excel_formateado(df_results, tienda):
    """Crea un Excel con formato profesional - versión simplificada"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        # Si no está instalado openpyxl, devolver Excel simple
        output = BytesIO()
        df_results.to_excel(output, index=False)
        output.seek(0)
        return output
    
    output = BytesIO()
    
    # Crear workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultados"
    
    # Título
    ws['A1'] = f'AUDITORÍA {tienda.upper()} - {datetime.now().strftime("%d/%m/%Y %H:%M")}'
    ws['A1'].font = Font(bold=True, size=14)
    ws.merge_cells('A1:I1')
    
    # Espacio
    ws.append([])
    
    # Encabezados (sin columna Stock Web)
    columnas = ['SKU', 'Precio Correcto', 'Precio Web', 'Variación %', 
                'Precio OK', 'Estado', 'Cambio vs Anterior', 'Tendencia', 'URL']
    ws.append(columnas)
    
    # Formato encabezados
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="667EEA", end_color="667EEA", fill_type="solid")
    
    for cell in ws[3]:
        cell.font = header_font
        cell.fill = header_fill
    
    # Agregar datos
    for _, row in df_results.iterrows():
        estado = row.get('estado_producto', 'Activo')
        cambio = row.get('cambio_vs_anterior', '')
        tendencia = row.get('tendencia', '')
        
        row_data = [
            row.get('sku', ''),
            row.get('precio_maestro', 0),
            row.get('precio_web', 0),
            row.get('variacion_precio_%', 0),
            'Sí' if row.get('precio_ok', False) else 'No',
            estado,
            cambio,
            tendencia,
            row.get('url', '')
        ]
        ws.append(row_data)
    
    # Aplicar formato básico
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Aplicar bordes y colores
    for row_num in range(4, ws.max_row + 1):
        for col_num in range(1, 10):  # 9 columnas ahora
            try:
                cell = ws.cell(row=row_num, column=col_num)
                cell.border = thin_border
                
                # Color para Precio OK
                if col_num == 5:  # Columna de Precio OK
                    if cell.value == 'Sí':
                        cell.fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
                    else:
                        cell.fill = PatternFill(start_color="FFB6C1", end_color="FFB6C1", fill_type="solid")
                
                # Color para Estado
                if col_num == 6:  # Columna Estado
                    if cell.value == 'No disponible en el front':
                        cell.fill = PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid")
                
                # Color para Cambio vs Anterior
                if col_num == 7:  # Columna Cambio vs Anterior
                    if '↑' in str(cell.value):
                        cell.font = Font(color="FF0000")
                    elif '↓' in str(cell.value):
                        cell.font = Font(color="008000")
            except:
                pass
    
    # Ajustar anchos de columna
    ws.column_dimensions['A'].width = 15  # SKU
    ws.column_dimensions['B'].width = 15  # Precio Correcto
    ws.column_dimensions['C'].width = 15  # Precio Web
    ws.column_dimensions['D'].width = 12  # Variación
    ws.column_dimensions['E'].width = 10  # Precio OK
    ws.column_dimensions['F'].width = 25  # Estado
    ws.column_dimensions['G'].width = 20  # Cambio vs Anterior
    ws.column_dimensions['H'].width = 15  # Tendencia
    ws.column_dimensions['I'].width = 40  # URL
    
    # Guardar
    wb.save(output)
    output.seek(0)
    
    return output

class WebScraper:
    """Clase para hacer web scraping de las tiendas"""
    
    def __init__(self, tienda_config):
        self.config = tienda_config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def limpiar_precio(self, precio_texto):
        """Limpia y convierte el precio a número"""
        if not precio_texto:
            return None
        
        # Eliminar símbolos de moneda y espacios
        precio_texto = precio_texto.replace('$', '').replace(' ', '').strip()
        
        # IMPORTANTE: Para precios argentinos con punto como separador de miles
        # Ejemplos: 486.199 → 486199, 1.234.567 → 1234567
        
        # Si tiene múltiples puntos, es claramente separador de miles
        if precio_texto.count('.') > 1:
            precio_texto = precio_texto.replace('.', '')
        # Si tiene punto y coma, formato argentino
        elif '.' in precio_texto and ',' in precio_texto:
            precio_texto = precio_texto.replace('.', '').replace(',', '.')
        # Si solo tiene punto
        elif '.' in precio_texto:
            # Verificar si es separador de miles (seguido de 3 dígitos)
            if re.search(r'\.\d{3}', precio_texto):
                precio_texto = precio_texto.replace('.', '')
            # Si NO es seguido de exactamente 2 dígitos al final, es miles
            elif not re.search(r'\.\d{2}$', precio_texto):
                precio_texto = precio_texto.replace('.', '')
        # Si solo tiene coma
        elif ',' in precio_texto:
            # Si está seguida de 2 dígitos, es decimal
            if re.search(r',\d{2}$', precio_texto):
                precio_texto = precio_texto.replace(',', '.')
            else:
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
            'estado_producto': 'Activo',
            'error': None,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            response = self.session.get(url, timeout=10)
            
            # Si es 404, marcar como no disponible
            if response.status_code == 404:
                resultado['estado_producto'] = 'No disponible en el front'
                resultado['error'] = None  # No es un error técnico
                return resultado
            
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            html_text = soup.get_text()
            
            # Verificar si el producto no está disponible
            if 'This product is no longer available' in html_text or \
               'Este producto ya no está disponible' in html_text or \
               'Producto no disponible' in html_text:
                resultado['estado_producto'] = 'No disponible en el front'
                resultado['error'] = None
                return resultado
            
            # Buscar precio
            for selector in self.config['selector_precio']:
                elemento = soup.select_one(selector)
                if elemento:
                    precio_texto = elemento.get_text(strip=True)
                    resultado['precio_web'] = self.limpiar_precio(precio_texto)
                    if resultado['precio_web']:
                        break
            
            # Si no se encontró precio pero la página cargó, podría no estar disponible
            if not resultado['precio_web'] and response.status_code == 200:
                # Verificar si hay indicadores de producto no disponible
                if 'selector_no_disponible' in self.config:
                    for selector in self.config.get('selector_no_disponible', []):
                        if soup.select_one(selector):
                            resultado['estado_producto'] = 'No disponible en el front'
                            break
            
        except requests.exceptions.HTTPError as e:
            if '404' in str(e):
                resultado['estado_producto'] = 'No disponible en el front'
                resultado['error'] = None
            else:
                resultado['error'] = str(e)
        except Exception as e:
            resultado['error'] = str(e)
        
        return resultado

def realizar_scraping(df_tienda, tienda_config, progress_bar, status_text):
    """Realiza el scraping de todas las URLs de una tienda"""
    scraper = WebScraper(tienda_config)
    resultados = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scraper.scrape_url, row['url']): idx 
                  for idx, row in df_tienda.iterrows() if pd.notna(row.get('url'))}
        
        completed = 0
        total_futures = len(futures)
        
        for future in as_completed(futures):
            completed += 1
            idx = futures[future]
            progress = min(completed / total_futures, 1.0)
            progress_bar.progress(progress)
            status_text.text(f"Escaneando URL {completed}/{total_futures}...")
