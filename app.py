import streamlit as st
import fitz  # PyMuPDF
import re
import json

# Configuración de la página en Streamlit
st.set_page_config(
    page_title="Extractor de Mallas y Pensums - UAA",
    page_icon="🎓",
    layout="wide"
)

def extract_rows_from_pdf(uploaded_file):
    """
    Extrae líneas de texto ordenadas por coordenadas Y (arriba a abajo) y X (izquierda a derecha)
    utilizando PyMuPDF para evitar errores de referencias PDFObjRef corruptas.
    """
    # Leer los bytes del archivo cargado por Streamlit
    pdf_bytes = uploaded_file.getvalue()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    all_pages_rows = []
    
    for page in doc:
        # Extraer estructura de texto con bboxes
        page_dict = page.get_text("dict")
        items = []
        
        for block in page_dict.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    bbox = line["bbox"]  # (x0, y0, x1, y1)
                    # Unir los fragmentos de texto de la línea
                    text = " ".join([span["text"] for span in line["spans"]]).strip()
                    if text:
                        # y0 representa la posición vertical superior en PyMuPDF
                        items.append({'y': bbox[1], 'x': bbox[0], 'text': text})
        
        # En PyMuPDF Y=0 está arriba, ordenamos de menor a mayor Y (de arriba a abajo)
        items.sort(key=lambda item: item['y'])
        
        rows = []
        if not items:
            continue
            
        current_row = [items[0]]
        for item in items[1:]:
            # Agrupar elementos en la misma línea (tolerancia de 4 puntos)
            if abs(item['y'] - current_row[0]['y']) <= 4.0:
                current_row.append(item)
            else:
                current_row.sort(key=lambda it: it['x'])
                rows.append(current_row)
                current_row = [item]
        if current_row:
            current_row.sort(key=lambda it: it['x'])
            rows.append(current_row)
            
        all_pages_rows.append(rows)
        
    doc.close()
    return all_pages_rows

def parse_pensum(pdf_file):
    """Extrae las materias, categorías, créditos y prerrequisitos del PDF del Pensum"""
    pages = extract_rows_from_pdf(pdf_file)
    categoria = "Formación General"
    subcategoria = "Obligatorias"
    
    facultad = "Facultad de Ciencias Económicas y Empresariales"
    carrera = "Carrera Desconocida"
    promocion = None
    anio_inicio = None
    
    materias = []
    
    for page in pages:
        for row in page:
            row_str = " ".join([it['text'] for it in row])
            
            # Detectar Facultad, Carrera y Promoción
            if "Facultad:" in row_str or "Facultad de" in row_str:
                m_fac = re.search(r'Facultad:\s*([^|]+)', row_str) or re.search(r'Facultad de [^|]+', row_str)
                if m_fac: 
                    facultad = m_fac.group(1 if 'Facultad:' in row_str else 0).strip()
            if "Carrera:" in row_str:
                m_car = re.search(r'Carrera:\s*([^|]+)', row_str)
                if m_car and "Facultad" not in m_car.group(1):
                    carrera = m_car.group(1).split("Promoción")[0].strip()
            if "Promoción:" in row_str or "Promoción" in row_str:
                m_prom = re.search(r'Promoción:\s*(\d+)', row_str) or re.search(r'Promoción\s*(\d+)', row_str)
                if m_prom: 
                    promocion = int(m_prom.group(1))
            if "Año Inicio:" in row_str:
                m_anio = re.search(r'Año Inicio:\s*(\d{4})', row_str)
                if m_anio: 
                    anio_inicio = int(m_anio.group(1))

            # Detectar Categorías y Subcategorías
            if "Materias de Formación General" in row_str:
                categoria = "Formación General"
                continue
            elif "Materias Específicas de la Carrera" in row_str:
                categoria = "Específicas de la Carrera"
                continue
                
            if "Obligatorias" in row_str and not re.search(r'[A-Z]{3,4}-\d{3}', row_str):
                subcategoria = "Obligatorias"
                continue
            elif "Suficiencia" in row_str and not re.search(r'[A-Z]{3,4}-\d{3}', row_str):
                subcategoria = "Suficiencia"
                continue
            elif "Grado Académico" in row_str and not re.search(r'[A-Z]{3,4}-\d{3}', row_str):
                subcategoria = "Trabajo de Grado"
                continue
            elif "Electivas" in row_str and not re.search(r'[A-Z]{3,4}-\d{3}', row_str):
                subcategoria = "Electivas"
                continue
                
            # Detectar fila de materia
            cod_mat_match = re.search(r'\b([A-Z]{3,4}-\d{3})\b', row_str)
            if cod_mat_match:
                cod_materia = cod_mat_match.group(1)
                
                # Código sistema
                cod_sis = None
                for it in row:
                    if 50 <= it['x'] <= 160:
                        m_s = re.search(r'\b(\d{1,2}\.?\d{3}|\d{1,5})\b', it['text'])
                        if m_s:
                            cod_sis = m_s.group(1)
                            break
                            
                # Créditos Presenciales y Prácticas Asistidas
                cp, pa, tot = 4, 0, 4
                for it in row:
                    if 350 <= it['x'] <= 375 and it['text'].isdigit(): cp = int(it['text'])
                    elif 380 <= it['x'] <= 405 and it['text'].isdigit(): pa = int(it['text'])
                    elif 415 <= it['x'] <= 440 and it['text'].isdigit(): tot = int(it['text'])
                
                # Nombre de la Materia
                name_parts = []
                for it in row:
                    if 60 <= it['x'] <= 340:
                        t = re.sub(r'^\d{1,2}\.?\d{3}\s*|\^\d{1,5}\s*', '', it['text'])
                        t = re.sub(r'^\d+\s*', '', t)
                        if t.strip() and not t.strip().isdigit():
                            name_parts.append(t.strip())
                nombre = " ".join(name_parts)
                
                # Prerrequisitos
                all_codes = re.findall(r'\b([A-Z]{3,4}-\d{3})\b', row_str)
                prereqs = [c for c in all_codes if c != cod_materia]
                
                materias.append({
                    "codigo_materia": cod_materia,
                    "codigo_sistema": cod_sis,
                    "nombre": nombre,
                    "categoria": categoria,
                    "subcategoria": subcategoria,
                    "creditos_presenciales": cp,
                    "practica_asistida": pa,
                    "creditos_totales": tot,
                    "prerrequisitos": prereqs
                })
                
    return {
        "facultad": facultad,
        "carrera": carrera,
        "promocion": promocion,
        "anio_inicio": anio_inicio,
        "materias": materias
    }

def parse_malla(pdf_file):
    """Extrae la secuencia temporal por semestres del PDF de la Malla Curricular"""
    pages = extract_rows_from_pdf(pdf_file)
    
    secuencia = []
    semestre_actual = "Primero"
    curso_actual = 1
    
    semestres_ord = {
        "Primero": 1, "Segundo": 2, "Tercero": 3, "Cuarto": 4, "Quinto": 5,
        "Sexto": 6, "Séptimo": 7, "Octavo": 8, "Noveno": 9, "Décimo": 10
    }
    
    for page in pages:
        for row in page:
            row_str = " ".join([it['text'] for it in row])
            
            # Detectar Curso
            for it in row:
                if it['x'] < 30 and it['text'].isdigit() and int(it['text']) <= 5:
                    curso_actual = int(it['text'])
                    
            # Detectar Semestre
            for sem in semestres_ord.keys():
                if sem in row_str:
                    semestre_actual = sem
                    break
                    
            # Detectar Año Lectivo
            m_anio = re.search(r'\b(202\d|203\d)\b', row_str)
            anio_lectivo = int(m_anio.group(1)) if m_anio else 2026
            
            # Slot Electiva o Materia Fija
            if "ELECTIVA" in row_str and not re.search(r'\b[A-Z]{3,4}-\d{3}\b', row_str):
                m_elec = re.search(r'ELECTIVA\s*(\d+)?', row_str)
                slot_name = m_elec.group(0) if m_elec else "ELECTIVA"
                secuencia.append({
                    "curso": curso_actual,
                    "semestre_nro": semestres_ord.get(semestre_actual, 1),
                    "semestre_nombre": semestre_actual,
                    "anio_lectivo": anio_lectivo,
                    "codigo_materia": None,
                    "es_slot_electiva": True,
                    "slot_nombre": slot_name
                })
            elif re.search(r'\b[A-Z]{3,4}-\d{3}\b', row_str):
                cod_materia = re.search(r'\b([A-Z]{3,4}-\d{3})\b', row_str).group(1)
                if "Prerrequisitos" not in row_str and "Código" not in row_str:
                    secuencia.append({
                        "curso": curso_actual,
                        "semestre_nro": semestres_ord.get(semestre_actual, 1),
                        "semestre_nombre": semestre_actual,
                        "anio_lectivo": anio_lectivo,
                        "codigo_materia": cod_materia,
                        "es_slot_electiva": False,
                        "slot_nombre": None
                    })
                    
    return secuencia

# --- INTERFAZ WEB STREAMLIT ---
st.title("🎓 Extractor de Mallas y Pensums - UAA")
st.write("Sube los PDFs del **Pensum** y la **Malla Curricular** para generar el JSON estructurado listo para la Base de Datos.")

col1, col2 = st.columns(2)

with col1:
    pensum_pdf = st.file_uploader("📄 Subir PDF del PENSUM", type=["pdf"])

with col2:
    malla_pdf = st.file_uploader("📊 Subir PDF de la MALLA CURRICULAR", type=["pdf"])

if pensum_pdf and malla_pdf:
    st.success("Archivos cargados correctamente. Procesando...")
    
    data_pensum = parse_pensum(pensum_pdf)
    data_malla = parse_malla(malla_pdf)
    
    # Ensamblar estructura unificada
    resultado_final = {
        "facultad": data_pensum["facultad"],
        "carrera": data_pensum["carrera"],
        "promocion": data_pensum["promocion"],
        "anio_inicio": data_pensum["anio_inicio"],
        "pensum_materias": data_pensum["materias"],
        "malla_secuencia": data_malla
    }
    
    st.subheader(f"📌 {data_pensum['carrera']} (Promoción {data_pensum['promocion']})")
    
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    col_stat1.metric("Total Materias en Pensum", len(data_pensum["materias"]))
    col_stat2.metric("Materias / Slots en Malla", len(data_malla))
    col_stat3.metric("Año Inicio", data_pensum["anio_inicio"] or 2026)
    
    # Pestañas de previsualización
    tab1, tab2 = st.tabs(["👁️ Previsualizar JSON", "📋 Resumen de Materias"])
    
    with tab1:
        st.json(resultado_final)
        
    with tab2:
        st.dataframe(data_pensum["materias"])
        
    # Botón de descarga
    json_str = json.dumps(resultado_final, ensure_ascii=False, indent=2)
    filename = f"{data_pensum['carrera'].replace(' ', '_')}_Prom{data_pensum['promocion']}.json"
    
    st.download_button(
        label="📥 Descargar JSON Estructurado",
        data=json_str,
        file_name=filename,
        mime="application/json"
    )
