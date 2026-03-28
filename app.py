import streamlit as st
import openai
import json
import chromadb
import asyncio
import edge_tts
import base64
import os
import urllib.parse
from ddgs import DDGS
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
    # Esto busca la clave en "Advanced Settings > Secrets" de Streamlit Cloud
    try:
        DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
    except:
        st.error("⚠️ Falta configurar la API KEY en los Secrets de Streamlit.")
        st.stop()

    client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    # Memoria persistente en la nube
    @st.cache_resource
    def get_memory():
        chroma_client = chromadb.PersistentClient(path="./memoria_hache_web")
        default_ef = embedding_functions.DefaultEmbeddingFunction()
        return chroma_client.get_or_create_collection(name="hache_v3", embedding_function=default_ef)
    
    collection = get_memory()

    # --- 4. HERRAMIENTAS (FUNCIONES) ---
    def buscar_internet(query):
        with DDGS() as ddgs:
            res = ddgs.text(query, max_results=3)
            return "\n".join([f"{r['title']}: {r['body']}" for r in res])

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

    # --- 5. MOTOR DE VOZ ---
    async def generar_audio(texto):
        archivo = "temp_voz.mp3"
        communicate = edge_tts.Communicate(texto, "es-AR-TomasNeural")
        await communicate.save(archivo)
        with open(archivo, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode()
        if os.path.exists(archivo):
            os.remove(archivo)
        return f'<audio autoplay src="data:audio/mp3;base64,{b64}">'

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
            for m in st.session_state.messages:
                historial.append({"role": m["role"], "content": m["content"]})

            tools = [
                {"type": "function", "function": {"name": "buscar_internet", "description": "Busca info actual.", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}},
                {"type": "function", "function": {"name": "guardar_memoria", "description": "Guarda datos de Lio.", "parameters": {"type": "object", "properties": {"d": {"type": "string"}, "e": {"type": "string"}}, "required": ["d", "e"]}}},
                {"type": "function", "function": {"name": "buscar_memoria", "description": "Revisa tus recuerdos.", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}},
                {"type": "function", "function": {"name": "generar_imagen", "description": "Genera una imagen artística.", "parameters": {"type": "object", "properties": {"p": {"type": "string", "description": "Descripción en inglés"}}, "required": ["p"]}}}
            ]

            img_url = None
            while True:
                resp = client.chat.completions.create(model="deepseek-chat", messages=historial, tools=tools)
                msg_ia = resp.choices[0].message
                
                if msg_ia.tool_calls:
                    historial.append(msg_ia)
                    for t in msg_ia.tool_calls:
                        args = json.loads(t.function.arguments)
                        if t.function.name == "buscar_internet": r = buscar_internet(args['q'])
                        elif t.function.name == "guardar_memoria": r = guardar_memoria(args['d'], args['e'])
                        elif t.function.name == "buscar_memoria": r = buscar_memoria(args['q'])
                        elif t.function.name == "generar_imagen": 
                            img_url = generar_imagen(args['p'])
                            r = f"Imagen generada. URL: {img_url}"
                        historial.append({"role": "tool", "tool_call_id": t.id, "name": t.function.name, "content": r})
                else:
                    texto_ia = msg_ia.content
                    st.markdown(texto_ia)
                    
                    msg_data = {"role": "assistant", "content": texto_ia}
                    if img_url:
                        st.image(img_url)
                        msg_data["image"] = img_url
                    
                    st.session_state.messages.append(msg_data)
                    
                    # Ejecutar audio
                    try:
                        audio_html = asyncio.run(generar_audio(texto_ia))
                        st.components.v1.html(audio_html, height=0)
                    except:
                        pass
                    break
                    
                    # Audio
                    html_audio = asyncio.run(generar_audio(texto_ia))
                    st.components.v1.html(html_audio, height=0)
                    break
