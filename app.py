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
st.set_page_config(page_title="Hache AI - Lio's Assistant", page_icon="🎨", layout="centered")

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
    # --- 3. CONFIGURACIÓN DE CEREBRO Y MEMORIA ---
    # REEMPLAZA CON TU API KEY REAL DE DEEPSEEK
    DEEPSEEK_API_KEY = "TU_API_KEY_AQUI" 
    client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    # Memoria persistente
    chroma_client = chromadb.PersistentClient(path="./memoria_hache_web")
    default_ef = embedding_functions.DefaultEmbeddingFunction()
    collection = chroma_client.get_or_create_collection(name="hache_v3", embedding_function=default_ef)

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
        return "\n".join(res['documents'][0]) if res['documents'][0] else "No tengo recuerdos sobre eso."

    def generar_imagen(prompt_descripcion):
        # Codificamos el texto para que sea una URL válida
        prompt_safe = urllib.parse.quote(prompt_descripcion)
        url_imagen = f"https://image.pollinations.ai/prompt/{prompt_safe}?width=1024&height=1024&nologo=true"
        return url_imagen

    # --- 5. MOTOR DE VOZ ---
    async def generar_audio(texto):
        archivo = "temp_voz.mp3"
        communicate = edge_tts.Communicate(texto, "es-AR-TomasNeural")
        await communicate.save(archivo)
        with open(archivo, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode()
        os.remove(archivo)
        return f'<audio autoplay src="data:audio/mp3;base64,{b64}">'

    # --- 6. INTERFAZ VISUAL ---
    st.title("🤖 Hache: Mi Asistente")
    st.subheader("Hola Lio, ¿qué vamos a crear hoy?")
    st.markdown("---")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Mostrar historial
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "image" in msg:
                st.image(msg["image"], caption="Imagen generada por Hache")

    # Entrada de chat
    if prompt := st.chat_input("Escribe aquí..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            historial = [{"role": "system", "content": "Eres Hache, asistente de Lio. Eres argentino, creativo y eficiente. Tienes acceso a internet, memoria e IMÁGENES. Si Lio te pide un dibujo o foto, usa generar_imagen."}]
            for m in st.session_state.messages:
                historial.append({"role": m["role"], "content": m["content"]})

            tools = [
                {"type": "function", "function": {"name": "buscar_internet", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}},
                {"type": "function", "function": {"name": "guardar_memoria", "parameters": {"type": "object", "properties": {"d": {"type": "string"}, "e": {"type": "string"}}, "required": ["d", "e"]}}},
                {"type": "function", "function": {"name": "buscar_memoria", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}},
                {"type": "function", "function": {"name": "generar_imagen", "description": "Genera una imagen artística basada en una descripción.", "parameters": {"type": "object", "properties": {"p": {"type": "string", "description": "Descripción detallada de la imagen en inglés para mejor calidad"}}, "required": ["p"]}}}
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
                            r = f"Imagen generada con éxito. URL: {img_url}"
                        historial.append({"role": "tool", "tool_call_id": t.id, "name": t.function.name, "content": r})
                else:
                    texto_ia = msg_ia.content
                    st.markdown(texto_ia)
                    
                    new_msg = {"role": "assistant", "content": texto_ia}
                    if img_url:
                        st.image(img_url)
                        new_msg["image"] = img_url
                    
                    st.session_state.messages.append(new_msg)
                    
                    # Audio
                    html_audio = asyncio.run(generar_audio(texto_ia))
                    st.components.v1.html(html_audio, height=0)
                    break