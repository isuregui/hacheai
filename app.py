import streamlit as st
import openai
import json
import chromadb
import asyncio
import edge_tts
import base64
import os
import urllib.parse
from duckduckgo_search import DDGS 
from chromadb.utils import embedding_functions

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Hache Turbo", page_icon="⚡", layout="centered")

def check_auth():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.title("🔐 Acceso")
        u, p = st.text_input("Usuario"), st.text_input("Clave", type="password")
        if st.button("Entrar"):
            if u == "Lio" and p == "160801":
                st.session_state.authenticated = True
                st.rerun()
        return False
    return True

if check_auth():
    DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
    client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    @st.cache_resource
    def get_memory():
        path = os.path.join(os.getcwd(), "memoria_hache_web")
        c = chromadb.PersistentClient(path=path)
        return c.get_or_create_collection(name="hache_v3", embedding_function=embedding_functions.DefaultEmbeddingFunction())
    
    collection = get_memory()

    # --- MOTOR DE AUDIO ---
    async def generar_audio_b64(texto):
        texto_limpio = texto.replace("*", "").replace("#", "")
        archivo = "voz.mp3"
        communicate = edge_tts.Communicate(texto_limpio, "es-AR-TomasNeural")
        await communicate.save(archivo)
        with open(archivo, "rb") as f:
            data = f.read()
        os.remove(archivo)
        return base64.b64encode(data).decode()

    # --- INTERFAZ ---
    st.title("⚡ Hache Turbo")
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if "image" in m: st.image(m["image"])

    if prompt := st.chat_input("¿Qué onda, Lio?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            container = st.empty() # Espacio para el texto fluido
            full_response = ""
            
            # Llamada con STREAMING habilitado
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "system", "content": "Eres Hache, asistente argentino. Habla limpio, sin asteriscos ni negritas."}] + 
                         [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
                stream=True # <--- ESTO ACTIVA LA VELOCIDAD
            )

            for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    full_response += content
                    container.markdown(full_response + "▌") # Efecto de cursor
            
            container.markdown(full_response) # Texto final sin cursor
            
            # Guardamos y disparamos audio al final del streaming (para que sea fluido)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            
            # Generación de audio ultra rápida
            b64_audio = asyncio.run(generar_audio_b64(full_response))
            audio_html = f'<audio autoplay src="data:audio/mp3;base64,{b64_audio}">'
            st.components.v1.html(audio_html, height=0)

            # Si el texto sugiere una imagen, podrías invocar la herramienta aquí.
            # (Para simplificar y acelerar, Hache ahora prioriza responder y hablar).
