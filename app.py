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
st.set_page_config(page_title="Hache Real-Time", page_icon="⚽", layout="centered")

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

    # --- FUNCIONES DE HERRAMIENTAS ---
    def buscar_internet(query):
        try:
            with DDGS() as ddgs:
                # Buscamos noticias muy recientes
                res = ddgs.text(query, max_results=5)
                return "\n".join([f"{r['title']}: {r['body']}" for r in res])
        except:
            return "No pude conectar con el radar de noticias."

    async def generar_audio_b64(texto):
        texto_limpio = texto.replace("*", "").replace("#", "")
        archivo = "voz.mp3"
        try:
            communicate = edge_tts.Communicate(texto_limpio, "es-AR-TomasNeural")
            await communicate.save(archivo)
            with open(archivo, "rb") as f: data = f.read()
            os.remove(archivo)
            return base64.b64encode(data).decode()
        except: return None

    # --- INTERFAZ ---
    st.title("⚽ Hache: Modo Estadio")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if "image" in m: st.image(m["image"])

    if prompt := st.chat_input("¿Cómo salió Argentina?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            # 1. PRE-PROCESAMIENTO: ¿Necesita buscar en internet?
            # Le damos herramientas a la IA
            tools = [
                {"type": "function", "function": {"name": "buscar_internet", "description": "Usa esto para resultados deportivos, noticias de hoy o clima.", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}}
            ]

            historial = [{"role": "system", "content": "Eres Hache. Si el usuario te pregunta por deportes, noticias o eventos de hoy, TIENES QUE usar buscar_internet. No digas que no sabes, ¡BUSCA! Responde como argentino, sin asteriscos."}]
            for m in st.session_state.messages:
                historial.append({"role": m["role"], "content": m["content"]})

            # Primera llamada para ver si quiere usar herramientas
            response = client.chat.completions.create(model="deepseek-chat", messages=historial, tools=tools)
            msg_ia = response.choices[0].message

            if msg_ia.tool_calls:
                for tool in msg_ia.tool_calls:
                    query_busqueda = json.loads(tool.function.arguments)['q']
                    st.write(f"🔍 Buscando info real sobre: {query_busqueda}...")
                    resultado_web = buscar_internet(query_busqueda)
                    historial.append(msg_ia)
                    historial.append({"role": "tool", "tool_call_id": tool.id, "name": "buscar_internet", "content": resultado_web})

            # 2. GENERACIÓN CON STREAMING
            full_response = ""
            container = st.empty()
            
            stream = client.chat.completions.create(model="deepseek-chat", messages=historial, stream=True)
            
            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    full_response += content
                    container.markdown(full_response + "▌")
            
            container.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})

            # 3. AUDIO
            b64_audio = asyncio.run(generar_audio_b64(full_response))
            if b64_audio:
                audio_html = f'<audio autoplay src="data:audio/mp3;base64,{b64_audio}">'
                st.components.v1.html(audio_html, height=0)
