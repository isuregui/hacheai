import streamlit as st
import openai
import json
import asyncio
import edge_tts
import base64
import os
import urllib.parse
import re
from duckduckgo_search import DDGS 

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Hache - Actualidad Limpia", page_icon="⚽")

def check_auth():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.title("🔐 Acceso a Hache")
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Entrar"):
            if u == "Lio" and p == "160801":
                st.session_state.authenticated = True
                st.rerun()
        return False
    return True

if check_auth():
    DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
    client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    def realizar_busqueda(query):
        try:
            with DDGS() as ddgs:
                # Buscamos noticias del último tiempo
                resultados = ddgs.text(f"{query} resultado hoy argentina", max_results=5)
                return "\n".join([f"{r['title']}: {r['body']}" for r in resultados]) if resultados else "No hay info nueva."
        except: return "Error de conexión web."

    async def generar_audio(texto):
        # Limpieza profunda para el audio (sin asteriscos ni etiquetas)
        texto_limpio = re.sub(r'<.*?>', '', texto).replace("*", "")
        archivo = "hache_voz.mp3"
        try:
            communicate = edge_tts.Communicate(texto_limpio, "es-AR-TomasNeural")
            await communicate.save(archivo)
            with open(archivo, "rb") as f: data = f.read()
            os.remove(archivo)
            return base64.b64encode(data).decode()
        except: return None

    st.title("🤖 Hache: Filtro de Pensamiento Activo")
    if "messages" not in st.session_state: st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    if prompt := st.chat_input("¿Cómo salió Argentina?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            tools = [{
                "type": "function",
                "function": {
                    "name": "realizar_busqueda",
                    "description": "Obligatorio para deportes o noticias de hoy.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
                }
            }]

            historial = [{"role": "system", "content": "Eres Hache. Responde SIEMPRE como argentino. Si necesitas saber un resultado, USA 'realizar_busqueda'. IMPORTANTE: No muestres etiquetas técnicas ni pensamientos internos en tu respuesta final."}]
            for m in st.session_state.messages: historial.append({"role": m["role"], "content": m["content"]})

            # 1. PASO: Llamada para Herramientas
            response = client.chat.completions.create(model="deepseek-chat", messages=historial, tools=tools)
            msg_ia = response.choices[0].message

            if msg_ia.tool_calls:
                for tool in msg_ia.tool_calls:
                    query_web = json.loads(tool.function.arguments)['query']
                    with st.status(f"🏟️ Buscando {query_web}..."):
                        info = realizar_busqueda(query_web)
                    historial.append(msg_ia)
                    historial.append({"role": "tool", "tool_call_id": tool.id, "name": "realizar_busqueda", "content": info})

            # 2. PASO: Respuesta Final con Limpieza de Streaming
            full_res = ""
            placeholder = st.empty()
            stream = client.chat.completions.create(model="deepseek-chat", messages=historial, stream=True)
            
            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    # FILTRO ANTI-PENSAMIENTO INTERNO
                    if not any(x in content for x in ["<|", "|DSML|", "thought", "<"]):
                        full_res += content
                        placeholder.markdown(full_res + "▌")
            
            placeholder.markdown(full_res)
            st.session_state.messages.append({"role": "assistant", "content": full_res})

            # 3. PASO: Audio
            b64_audio = asyncio.run(generar_audio(full_res))
            if b64_audio:
                st.components.v1.html(f'<audio autoplay src="data:audio/mp3;base64,{b64_audio}">', height=0)
