import streamlit as st
import openai
import json
import asyncio
import edge_tts
import base64
import os
import urllib.parse
from duckduckgo_search import DDGS 

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Hache - Resultados en Vivo", page_icon="⚽")

# --- LOGIN ---
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
    # 🔑 Clave desde Secrets de Streamlit
    try:
        DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
    except:
        st.error("Falta la API KEY en Secrets.")
        st.stop()

    client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    # --- FUNCIÓN DE BÚSQUEDA ---
    def realizar_busqueda(query):
        try:
            with DDGS() as ddgs:
                # Buscamos específicamente noticias de las últimas 24hs/semana
                resultados = ddgs.text(f"{query} resultado hoy", max_results=5)
                if resultados:
                    texto_web = "\n".join([f"{r['title']}: {r['body']}" for r in resultados])
                    return texto_web
                return "No encontré resultados recientes en la web."
        except Exception as e:
            return f"Error en la conexión web: {e}"

    # --- MOTOR DE VOZ ---
    async def generar_audio(texto):
        texto_limpio = texto.replace("*", "").replace("#", "")
        archivo = "hache_voz.mp3"
        try:
            communicate = edge_tts.Communicate(texto_limpio, "es-AR-TomasNeural")
            await communicate.save(archivo)
            with open(archivo, "rb") as f:
                data = f.read()
            b64 = base64.b64encode(data).decode()
            if os.path.exists(archivo): os.remove(archivo)
            return b64
        except: return None

    # --- INTERFAZ DE CHAT ---
    st.title("🤖 Hache: Modo Actualidad")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if prompt := st.chat_input("¿Cómo salió el partido?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            # Definimos la herramienta de búsqueda para la IA
            tools = [{
                "type": "function",
                "function": {
                    "name": "realizar_busqueda",
                    "description": "Obligatorio para resultados deportivos, noticias de hoy o datos actuales.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"]
                    }
                }
            }]

            # 1. PASO: ¿Necesita buscar?
            historial = [{"role": "system", "content": "Eres Hache, asistente argentino. Si te piden resultados deportivos o noticias de HOY, DEBES usar 'realizar_busqueda'. Luego responde con la info encontrada de forma natural, sin asteriscos."}]
            for m in st.session_state.messages:
                historial.append({"role": m["role"], "content": m["content"]})

            # Llamada inicial
            response = client.chat.completions.create(model="deepseek-chat", messages=historial, tools=tools)
            msg_ia = response.choices[0].message

            # Si la IA decide buscar (Tool Call)
            if msg_ia.tool_calls:
                for tool in msg_ia.tool_calls:
                    query_web = json.loads(tool.function.arguments)['query']
                    with st.status(f"🏟️ Buscando resultado de {query_web}...", expanded=True):
                        info_encontrada = realizar_busqueda(query_web)
                        st.write("Información obtenida de la red.")
                    
                    historial.append(msg_ia)
                    historial.append({"role": "tool", "tool_call_id": tool.id, "name": "realizar_busqueda", "content": info_encontrada})

            # 2. PASO: Generar respuesta final con STREAMING
            full_res = ""
            placeholder = st.empty()
            
            # Segunda llamada (ya con los datos de internet si hubo búsqueda)
            stream = client.chat.completions.create(model="deepseek-chat", messages=historial, stream=True)
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    full_res += chunk.choices[0].delta.content
                    placeholder.markdown(full_res + "▌")
            
            placeholder.markdown(full_res)
            st.session_state.messages.append({"role": "assistant", "content": full_res})

            # 3. PASO: Audio
            b64_audio = asyncio.run(generar_audio(full_res))
            if b64_audio:
                audio_html = f'<audio autoplay src="data:audio/mp3;base64,{b64_audio}">'
                st.components.v1.html(audio_html, height=0)
