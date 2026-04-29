import streamlit as st
import sqlite3
import re
import time
from datetime import datetime
from fpdf import FPDF
from google import genai

# --- 1. CONFIGURACIÓN Y ESTÉTICA "COOL" ---
st.set_page_config(page_title="HCE - Sistema Médico Pro", layout="wide", initial_sidebar_state="expanded")

if 'logeado' not in st.session_state: st.session_state['logeado'] = False
if 'gemini_key' not in st.session_state: st.session_state['gemini_key'] = ""

# Lógica de CSS: Fondo completo en Login, y solo en la barra lateral cuando estás dentro.
# SE CORRIGIÓ: El diseño de los botones en la barra lateral para que no se pierdan en el modo claro.
if not st.session_state['logeado']:
    css_dinamico = ".stApp { background: radial-gradient(circle, #1e90ff 0%, #001f3f 100%); }"
else:
    css_dinamico = """
    [data-testid="stSidebar"] { background: radial-gradient(circle, #1e90ff 0%, #001f3f 100%) !important; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] p, [data-testid="stSidebar"] label { color: white !important; }
    [data-testid="stSidebar"] button { background-color: rgba(255, 255, 255, 0.1) !important; color: white !important; border: 1px solid rgba(255, 255, 255, 0.4) !important; }
    [data-testid="stSidebar"] button p { color: white !important; }
    [data-testid="stSidebar"] button:hover { background-color: rgba(255, 255, 255, 0.25) !important; border: 1px solid white !important; }
    """

# Insertamos el CSS
st.markdown(f"""
    <style>
    /* Ocultar botones de Deploy */
    [data-testid="stAppDeployButton"] {{display: none !important;}}
    .stDeployButton {{display:none !important;}}
    footer {{visibility: hidden;}}
    
    {css_dinamico}
    
    .encabezado-blanco {{ text-align: center; color: white; font-family: 'Segoe UI', sans-serif; }}
    button[kind="primary"] {{ background-color: #1e90ff !important; border: none !important; color: white !important;}}
    .receta-box {{ background-color: white; color: black; padding: 30px; border: 2px solid #001f3f; border-radius: 10px; font-family: 'Courier New', Courier, monospace; }}
    </style>
    """, unsafe_allow_html=True)

# --- 2. BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect('hce_profesional.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS pacientes 
                      (id TEXT PRIMARY KEY, nombre TEXT, edad INTEGER, sexo TEXT, 
                       peso REAL, altura REAL, temp REAL, ant TEXT, nota TEXT, 
                       estatus TEXT, medico TEXT, fecha_registro TEXT, diagnostico_cie TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 3. FUNCIONES DE APOYO ---
def obtener_clasificacion_imc(imc):
    if imc < 18.5: return "Bajo Peso ⚠️", "orange"
    elif 18.5 <= imc < 24.9: return "Peso Normal ✅", "green"
    elif 25 <= imc < 29.9: return "Sobrepeso 🟠", "orange"
    else: return "Obesidad 🔴", "red"

def validar_curp(curp):
    patron = r'^[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z\d]\d$'
    return re.match(patron, curp.upper())

def generar_pdf_receta(medico, paciente, fecha, diagnostico, indicaciones):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, txt="RECETA MEDICA", ln=True, align='C')
    pdf.line(10, 20, 200, 20)
    
    pdf.set_font("Arial", size=12)
    pdf.ln(10)
    pdf.cell(100, 10, txt=f"Medico: Dr(a). {medico}")
    pdf.cell(90, 10, txt=f"Fecha: {fecha}", align='R', ln=True)
    pdf.ln(5)
    pdf.cell(190, 10, txt=f"Paciente: {paciente}", ln=True)
    pdf.cell(190, 10, txt=f"Diagnostico: {diagnostico}", ln=True)
    
    y_actual = pdf.get_y()
    pdf.line(10, y_actual, 200, y_actual)
    
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(190, 10, txt="Indicaciones y Tratamiento:", ln=True)
    pdf.set_font("Arial", size=12)
    indicaciones_limpias = indicaciones.replace('\n\n', '\n') if indicaciones else "Sin indicaciones registradas."
    pdf.multi_cell(190, 10, txt=indicaciones_limpias)
    
    pdf.ln(30)
    pdf.cell(190, 10, txt="__________________________", ln=True, align='C')
    pdf.cell(190, 10, txt="Firma del Medico", ln=True, align='C')
    
    return pdf.output(dest='S').encode('latin-1')

CIE_11 = {
    "J00": "Rinofaringitis aguda (Resfriado común)",
    "A09": "Diarrea y gastroenteritis de presunto origen infeccioso",
    "E11": "Diabetes mellitus tipo 2",
    "I10": "Hipertensión esencial (primaria)",
    "M54.5": "Lumbago no especificado",
    "K21.9": "Enfermedad por reflujo gastroesofágico",
    "BA00": "Hipertensión arterial",
    "CA00": "Asma Bronquial"
}

# --- 4. MEMORIA DEL SISTEMA ---
if 'usuario_actual' not in st.session_state: st.session_state['usuario_actual'] = ""
if 'vista_actual' not in st.session_state: st.session_state['vista_actual'] = "Registro"
if 'paciente_editar' not in st.session_state: st.session_state['paciente_editar'] = None

# --- PANTALLA DE LOGIN ---
if not st.session_state['logeado']:
    st.markdown("<br><h1 class='encabezado-blanco'>🏥</h1><h2 class='encabezado-blanco'>SISTEMA MÉDICO HCE</h2>", unsafe_allow_html=True)
    _, col_login, _ = st.columns([1, 1.5, 1])
    with col_login:
        with st.form("login_form"):
            user = st.text_input("Usuario (Nombre del Médico)")
            pwd = st.text_input("Contraseña", type="password")
            if st.form_submit_button("ENTRAR AL CONSULTORIO", type="primary", use_container_width=True):
                if (user == "Jose Miguel Hernandez Gomez" and pwd == "2007") or (user == "Jose Angel Chavez Alva" and pwd == "2026"):
                    st.session_state['logeado'] = True
                    st.session_state['usuario_actual'] = user
                    st.rerun()
                else:
                    st.error("Acceso denegado: Credenciales incorrectas.")

# --- SISTEMA PRINCIPAL ---
else:
    medico = st.session_state['usuario_actual']
    conn = sqlite3.connect('hce_profesional.db')
    
    with st.sidebar:
        st.title(f"👨‍⚕️ Dr. {medico}")
        if st.button("📝 Registro de Paciente", use_container_width=True):
            st.session_state['vista_actual'] = "Registro"
            st.session_state['paciente_editar'] = None
            st.rerun()
        if st.button("📇 Directorio Clínico", use_container_width=True):
            st.session_state['vista_actual'] = "Lista"
            st.rerun()
        st.divider()
        if st.button("Cerrar Sesión"):
            st.session_state['logeado'] = False
            conn.close()
            st.rerun()
            
        with st.expander("🛠️ Opciones de Sistema"):
            key_input = st.text_input("🔑 API Key de Gemini (IA)", type="password", value=st.session_state['gemini_key'])
            if st.button("Guardar Key"):
                st.session_state['gemini_key'] = key_input
                st.success("API Key guardada temporalmente.")
                
            st.divider()
            if st.button("Resetear Base de Datos") and st.text_input("Código:", type="password") == "RESET2026":
                conn.execute("DROP TABLE IF EXISTS pacientes")
                conn.commit()
                conn.close()
                init_db()
                st.success("Sistema reiniciado.")
                st.rerun()

    # --- PANTALLA 1: REGISTRO / EDICIÓN ---
    if st.session_state['vista_actual'] == "Registro":
        st.header("📄 Expediente Clínico (NOM-004-SSA3)")
        p_edit = None
        if st.session_state['paciente_editar']:
            p_edit = conn.execute("SELECT * FROM pacientes WHERE id=?", (st.session_state['paciente_editar'],)).fetchone()
            st.warning(f"Modo Edición: {p_edit[1]}")

        with st.container(border=True):
            st.subheader("1. Identificación del Paciente")
            c1, c2 = st.columns(2)
            nom = c1.text_input("Nombre Completo*", value=p_edit[1] if p_edit else "")
            curp = c2.text_input("CURP (18 caracteres)*", value=p_edit[0] if p_edit else "").upper()
            
            c3, c4, c5 = st.columns(3)
            edad = c3.number_input("Edad", min_value=0, max_value=120, value=p_edit[2] if p_edit else 20)
            sexo = c4.selectbox("Sexo", ["Masculino", "Femenino"], index=0 if not p_edit or p_edit[3] == "Masculino" else 1)
            estatus = c5.selectbox("Estatus del Paciente", ["Activo", "Inactivo"], index=0 if not p_edit or p_edit[9] == "Activo" else 1)
            
            st.divider()
            st.subheader("2. Signos Vitales y Somatometría")
            c6, c7, c8 = st.columns(3)
            peso = c6.number_input("Peso (kg)", value=float(p_edit[4]) if p_edit else 0.0)
            altura = c7.number_input("Altura (m)", value=float(p_edit[5]) if p_edit else 0.0)
            temp = c8.number_input("Temperatura (°C)", min_value=30.0, max_value=45.0, value=float(p_edit[6]) if p_edit else 36.5)
            
            if altura > 0:
                imc_val = peso / (altura ** 2)
                txt_imc, color_imc = obtener_clasificacion_imc(imc_val)
                st.markdown(f"**IMC:** {imc_val:.2f} - <span style='color:{color_imc}; font-weight:bold;'>{txt_imc}</span>", unsafe_allow_html=True)

            st.divider()
            st.subheader("3. Historia y Diagnóstico")
            ant = st.text_area("Antecedentes Heredofamiliares y Patológicos", value=p_edit[7] if p_edit else "")
            
            opciones_diag = list(CIE_11.values()) + ["Otro (Escribir manualmente)"]
            
            index_default = 0
            diag_db = p_edit[12] if p_edit else ""
            if diag_db:
                if diag_db in CIE_11.values():
                    index_default = list(CIE_11.values()).index(diag_db)
                else:
                    index_default = len(opciones_diag) - 1

            diag_sel = st.selectbox("Diagnóstico Principal", opciones_diag, index=index_default)
            
            if diag_sel == "Otro (Escribir manualmente)":
                diag_input = st.text_input("Especificar Diagnóstico:*", value=diag_db if index_default == len(opciones_diag)-1 else "")
            else:
                diag_input = diag_sel
            
            nota = st.text_area("Nota de Evolución / Tratamiento", value=p_edit[8] if p_edit else "", height=150)

        if st.button("💾 GUARDAR EXPEDIENTE", type="primary", use_container_width=True):
            if not nom or not curp or (diag_sel == "Otro (Escribir manualmente)" and not diag_input):
                st.error("⚠️ Error: Faltan campos obligatorios por llenar.")
            elif not validar_curp(curp):
                st.error("⚠️ Error: La CURP no es válida o está incompleta.")
            else:
                fecha_actual = datetime.now().strftime("%d/%m/%Y")
                conn.execute("INSERT OR REPLACE INTO pacientes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", 
                             (curp, nom, edad, sexo, peso, altura, temp, ant, nota, estatus, medico, fecha_actual, diag_input))
                conn.commit()
                st.success(f"✅ ¡Éxito! Expediente de {nom} guardado.")
                conn.close() 
                time.sleep(1.5)
                st.session_state['paciente_editar'] = None
                st.rerun()

    # --- PANTALLA 2: DIRECTORIO ---
    else:
        st.header("📇 Directorio Médico de Pacientes")
        busq = st.text_input("🔍 Buscar por nombre del paciente...")
        
        query = "SELECT * FROM pacientes WHERE medico=? "
        params = [medico]
        if busq:
            query += "AND nombre LIKE ? "
            params.append(f"%{busq}%")
        query += "ORDER BY estatus ASC, nombre ASC"
        
        pacientes = conn.execute(query, params).fetchall()
        
        for p in pacientes:
            with st.expander(f"{'🟢' if p[9]=='Activo' else '🔴'} {p[1]} | ID: {p[0]}"):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(f"**Edad:** {p[2]} años | **Sexo:** {p[3]}")
                    st.markdown(f"**Signos:** {p[4]}kg | {p[5]}m | {p[6]}°C")
                    st.markdown(f"**Antecedentes:** {p[7]}")
                    st.info(f"**Diagnóstico:** {p[12]}\n\n**Notas:** {p[8]}")
                    
                    if st.button("🤖 Resumir con IA", key=f"ia_{p[0]}"):
                        if st.session_state['gemini_key']:
                            try:
                                client = genai.Client(api_key=st.session_state['gemini_key'])
                                prompt = f"Actúa como un asistente médico profesional. Haz un resumen clínico breve y profesional del paciente. Nombre: {p[1]}, Edad: {p[2]}, Sexo: {p[3]}, Peso: {p[4]}kg, Altura: {p[5]}m, Temp: {p[6]}°C. Antecedentes: {p[7]}. Diagnóstico: {p[12]}. Notas: {p[8]}."
                                
                                with st.spinner("Generando resumen..."):
                                    respuesta = client.models.generate_content(
                                        model='gemini-2.5-flash',
                                        contents=prompt
                                    )
                                st.success("Resumen Generado:")
                                st.write(respuesta.text)
                            except Exception as e:
                                st.error(f"Error detallado de la IA: {e}")
                        else:
                            st.warning("⚠️ Necesitas colocar tu API Key en 'Opciones de Sistema' para usar esta función.")

                with c2:
                    st.subheader("📝 Acciones")
                    nueva_obs = st.text_input("Añadir observación rápida:", key=f"note_{p[0]}")
                    if st.button("➕ Pegar Nota", key=f"btn_{p[0]}"):
                        nueva_h = f"{p[8]}\n[{datetime.now().strftime('%H:%M')}] {nueva_obs}"
                        conn.execute("UPDATE pacientes SET nota=? WHERE id=?", (nueva_h, p[0]))
                        conn.commit()
                        conn.close() 
                        st.rerun()
                    
                    if st.button("✏️ Editar Todo", key=f"ed_{p[0]}", use_container_width=True):
                        st.session_state['paciente_editar'] = p[0]
                        st.session_state['vista_actual'] = "Registro"
                        conn.close() 
                        st.rerun()
                    if st.button("🗑️ Borrar Paciente", key=f"del_{p[0]}", use_container_width=True):
                        conn.execute("DELETE FROM pacientes WHERE id=?", (p[0],))
                        conn.commit()
                        conn.close()
                        st.rerun()
                    pdf_data = generar_pdf_receta(medico, p[1], p[11], p[12], p[8])
                    nombre_archivo = f"Receta_{p[1].replace(' ', '_')}.pdf"
                    
                    st.download_button(
                        label="📄 Descargar Receta (PDF)",
                        data=pdf_data,
                        file_name=nombre_archivo,
                        mime="application/pdf",
                        key=f"down_{p[0]}",
                        use_container_width=True
                    )

    try:
        conn.close()
    except:
        pass