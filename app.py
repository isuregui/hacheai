import streamlit as st
import openai
import json
import chromadb
import asyncio
import edge_tts
import base64
import os
import urllib.parse
# --- LÍNEA 10 CORREGIDA ---
from duckduckgo_search import DDGS 
from chromadb.utils import embedding_functions

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Hache AI - Lio's Assistant", page_icon="🤖", layout="centered")

# --- 2. LOGIN DE SEGURIDAD ---
def check_auth():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🔐 Acceso a Hache")
        user = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        if st.button("Ingresar"):
            if user == "Lio" and password == "160801":
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
        return False
    return True

if check_auth():
    # --- 3. CONFIGURACIÓN DE SEGURIDAD (SECRETS) ---
    try:
        DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
    except:
        st.error("⚠️ Falta configurar la API KEY en los Secrets de Streamlit.")
        st.stop()

    client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    # Memoria persistente
    @st.cache_resource
    def get_memory():
        # En la nube usamos una ruta absoluta para evitar errores de permisos
        persist_path = os.path.join(os.getcwd(), "memoria_hache_web")
        chroma_client = chromadb.PersistentClient(path=persist_path)
        default_ef = embedding_functions.DefaultEmbeddingFunction()
        return chroma_client.get_or_create_collection(name="hache_v3", embedding_function=default_ef)

    collection = get_memory()

    # --- 4. HERRAMIENTAS (FUNCIONES) ---
    def buscar_internet(query):
        try:
            with DDGS() as ddgs:
                res = ddgs.text(query, max_results=3)
                return "\n".join([f"{r['title']}: {r['body']}" for r in res])
        except Exception as e:
            return f"Error al buscar en internet: {str(e)}"

    def guardar_memoria(dato, etiqueta):
        collection.add(documents=[dato], metadatas=[{"tema": etiqueta}], ids=[str(collection.count()+1)])
        return "Hecho, lo guardé en mi memoria."

    def buscar_memoria(query):
        res = collection.query(query_texts=[query], n_results=2)
        if res['documents'] and res['documents'][0]:
            return "\n".join(res['documents'][0])
        return "No tengo recuerdos sobre eso."

    def generar_imagen(prompt_descripcion):
        prompt_safe = urllib.parse.quote(prompt_descripcion)
        return f"https://image.pollinations.ai/prompt/{prompt_safe}?width=1024&height=1024&nologo=true"

    # --- 5. MOTOR DE VOZ (Versión Limpia) ---
    async def generar_audio(texto):
        archivo = "temp_voz.mp3"
        # LIMPIEZA: Quitamos los asteriscos para que no los nombre
        texto_limpio = texto.replace("*", "") 

        try:
            # Usamos el texto limpio para el audio
            communicate = edge_tts.Communicate(texto_limpio, "es-AR-TomasNeural")
            await communicate.save(archivo)
            with open(archivo, "rb") as f:
                data = f.read()
            b64 = base64.b64encode(data).decode()
            if os.path.exists(archivo):
                os.remove(archivo)
            return f'<audio autoplay src="data:audio/mp3;base64,{b64}">'
        except:
            return ""

    # --- 6. INTERFAZ VISUAL ---
    st.title("🤖 Hache: Mi Asistente")
    st.write(f"Conectado como: **Lio**")
    st.markdown("---")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Mostrar historial
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "image" in msg:
                st.image(msg["image"])

    # Entrada de chat
    if prompt := st.chat_input("¿Qué hacemos hoy, Lio?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            historial = [{"role": "system", "content": "Eres Hache, asistente personal de Lio. Eres argentino, creativo y directo. Usas tus herramientas para buscar en internet, recordar cosas o generar imágenes."}]
            historial = [{"role": "system", "content": "Eres Hache, asistente de Lio. Eres argentino y creativo.puedes buscar informacion en internet, generar imagenes y tienes la capacidad de hablar, recordar, aprender y enseñar. IMPORTANTE: No uses asteriscos ni formato Markdown en tus respuestas, habla de forma limpia y natural."}]
            for m in st.session_state.messages:
                historial.append({"role": m["role"], "content": m["content"]})
