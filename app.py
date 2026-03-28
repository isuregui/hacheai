import streamlit as st
import openai
import json
import chromadb
import asyncio
import edge_tts
import base64
import os
import urllib.parse
import re
from duckduckgo_search import DDGS 
from chromadb.utils import embedding_functions

# --- 1. CONFIGURACIÓN DE INTERFAZ ---
st.set_page_config(page_title="Hache AI - Sistema Integral", page_icon="🇦🇷", layout="centered")

# Estilos personalizados para una interfaz más amigable
st.markdown("""
    <style>
    .stChatFloatingInputContainer { background-color: rgba(0,0,0,0); }
    .stChatMessage { border-radius: 15px; margin-bottom: 10px; }
    </style>
    """, unsafe_content_type=True)

# --- 2. SEGURIDAD ---
def check_auth():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.title("🛡️ Acceso Hache V4")
        col1, col2 = st.columns(2)
        with col1: u = st.text_input("Usuario")
        with col2: p = st.text_input("Clave", type="password")
        if st.button("Iniciar Sesión"):
            if u == "Lio" and p == "160801":
                st.session_state.authenticated = True
                st.rerun()
            else: st.error("Acceso denegado")
        return False
    return True

if check_auth():
    # Configuración de Clientes
    try:
        DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
    except:
        st.error("Configura DEEPSEEK_API_KEY en Secrets.")
        st.stop()

    client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    # --- 3. MEMORIA Y HERRAMIENTAS ---
    @st.cache_resource
    def init_memoria():
        path = os.path.join(os.getcwd(), "memoria_hache")
        chroma = chromadb.PersistentClient(path=path)
        return chroma.get_or_create_collection(
            name="hache_master", 
            embedding_function=embedding_functions.DefaultEmbeddingFunction()
        )
    
    collection = init_memoria()

    def buscar_web(q):
        try:
            with DDGS() as ddgs:
                res = ddgs.text(q, max_results=4)
                return "\n".join([f"{r['title']}: {r['body']}" for r in res])
        except: return "Error buscando en la red."

    def memorizar(dato, tema):
        collection.add(documents=[dato], metadatas=[{"tema": tema}], ids=[str(collection.count()+1)])
        return "Hecho Lio, ya lo guardé en mis recuerdos."

    def recordar(q):
        res = collection.query(query_texts=[q], n_results=2)
        return "\n".join(res['documents'][0]) if res['documents'][0] else "No recuerdo nada sobre eso."

    def dibujar(p):
        p_safe = urllib.parse.quote(p)
        return f"https://image.pollinations.ai/prompt/{p_safe}?width=1024&height=1024&nologo=true"

    # --- 4. MOTOR DE VOZ ---
    async def generar_audio(texto):
        # Limpieza de texto para el audio
        t_limpio = re.sub(r'<.*?>', '', texto).replace("*", "").replace("#", "")
        archivo = "hache_temp.mp3"
        try:
            comm = edge_tts.Communicate(t_limpio, "es-AR-TomasNeural")
            await comm.save(archivo)
            with open(archivo, "rb") as f: data = f.read()
            os.remove(archivo)
            return base64.b64encode(data).decode()
        except: return None

    # --- 5. LÓGICA DE CHAT ---
    st.title("🤖 Hache")
    st.caption("Memoria activa | Internet habilitado | Generador de Arte")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if "img" in m: st.image(m["img"])

    if prompt := st.chat_input("¿Qué onda, Lio?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            # Definición de herramientas para la IA
            tools = [
                {"type": "function", "function": {"name": "buscar_web", "description": "Info actual/deportes", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}},
                {"type": "function", "function": {"name": "memorizar", "description": "Guardar datos de Lio", "parameters": {"type": "object", "properties": {"d": {"type": "string"}, "t": {"type": "string"}}, "required": ["d", "t"]}}},
                {"type": "function", "function": {"name": "recordar", "description": "Buscar en recuerdos", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}},
                {"type": "function", "function": {"name": "dibujar", "description": "Crear imágenes", "parameters": {"type": "object", "properties": {"p": {"type": "string"}}, "required": ["p"]}}}
            ]

            hist = [{"role": "system", "content": "Eres Hache, asistente argentino. Habla natural. Si te piden noticias o deportes, BUSCA en la web. No muestres etiquetas técnicas."}]
            for m in st.session_state.messages: hist.append({"role": m["role"], "content": m["content"]})

            # Paso 1: Verificación de Herramientas
            resp_inicial = client.chat.completions.create(model="deepseek-chat", messages=hist, tools=tools)
            msg_ia = resp_inicial.choices[0].message
            
            img_url = None
            if msg_ia.tool_calls:
                for t in msg_ia.tool_calls:
                    args = json.loads(t.function.arguments)
                    if t.function.name == "buscar_web": 
                        with st.spinner("🔍 Rastreando la web..."): res = buscar_web(args['q'])
                    elif t.function.name == "memorizar": res = memorizar(args['d'], args['t'])
                    elif t.function.name == "recordar": res = recordar(args['q'])
                    elif t.function.name == "dibujar": 
                        img_url = dibujar(args['p'])
                        res = "Imagen generada correctamente."
                    
                    hist.append(msg_ia)
                    hist.append({"role": "tool", "tool_call_id": t.id, "name": t.function.name, "content": res})

            # Paso 2: Respuesta con Streaming y Limpieza
            full_txt = ""
            holder = st.empty()
            stream = client.chat.completions.create(model="deepseek-chat", messages=hist, stream=True)
            
            for chunk in stream:
                token = chunk.choices[0].delta.content
                if token:
                    # Filtro anti-pensamiento interno
                    if not any(x in token for x in ["<|", "|DSML|", "thought", "invoke"]):
                        full_txt += token
                        holder.markdown(full_txt + "▌")
            
            holder.markdown(full_txt)
            
            # Guardado final
            new_msg = {"role": "assistant", "content": full_txt}
            if img_url: 
                st.image(img_url)
                new_msg["img"] = img_url
            st.session_state.messages.append(new_msg)

            # Paso 3: Audio automático
            b64 = asyncio.run(generar_audio(full_txt))
            if b64:
                st.components.v1.html(f'<audio autoplay src="data:audio/mp3;base64,{b64}">', height=0)
