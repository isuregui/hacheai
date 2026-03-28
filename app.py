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

# --- 1. CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Hache AI - Definitivo", page_icon="🤖", layout="centered")

st.markdown("""
    <style>
    .stChatMessage { border-radius: 12px; margin-bottom: 15px; }
    .stChatFloatingInputContainer { background-color: transparent; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SISTEMA DE LOGIN ---
def check_auth():
    if "auth" not in st.session_state: 
        st.session_state.auth = False
    
    if not st.session_state.auth:
        st.title("🛡️ Acceso Hache")
        col1, col2 = st.columns(2)
        with col1: u = st.text_input("Usuario")
        with col2: p = st.text_input("Clave", type="password")
        if st.button("Iniciar Sesión"):
            if u == "Lio" and p == "160801":
                st.session_state.auth = True
                st.rerun()
            else: 
                st.error("Credenciales incorrectas")
        return False
    return True

if check_auth():
    # Conexión con DeepSeek
    try:
        DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
    except:
        st.error("⚠️ Falta configurar DEEPSEEK_API_KEY en los Secrets de Streamlit.")
        st.stop()

    client = openai.OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    # --- 3. MEMORIA Y HERRAMIENTAS ---
    @st.cache_resource
    def init_db():
        ruta = os.path.join(os.getcwd(), "memoria_hache")
        chroma = chromadb.PersistentClient(path=ruta)
        return chroma.get_or_create_collection(
            name="hache_master", 
            embedding_function=embedding_functions.DefaultEmbeddingFunction()
        )
    collection = init_db()

    def buscar_web(query):
        try:
            with DDGS() as ddgs:
                resultados = ddgs.text(query, max_results=3)
                if not resultados: return "No encontré resultados recientes."
                return "\n".join([f"Título: {r['title']}\nDetalle: {r['body']}" for r in resultados])
        except Exception as e: 
            return f"Fallo al conectar a internet: {e}"

    def memorizar(dato, tema):
        collection.add(documents=[dato], metadatas=[{"tema": tema}], ids=[str(collection.count()+1)])
        return "Dato guardado en la memoria a largo plazo."

    def recordar(query):
        res = collection.query(query_texts=[query], n_results=1)
        if res['documents'] and res['documents'][0]:
            return res['documents'][0][0]
        return "No tengo recuerdos previos sobre esto."

    def dibujar(prompt):
        safe_p = urllib.parse.quote(prompt)
        return f"https://image.pollinations.ai/prompt/{safe_p}?width=1024&height=1024&nologo=true"

    # --- 4. MOTOR DE VOZ (FILTRO EXTREMO) ---
    async def generar_audio(texto):
        # Eliminamos absolutamente cualquier etiqueta, corchete o asterisco antes de hablar
        t_limpio = re.sub(r'<.*?>', '', texto)
        t_limpio = t_limpio.replace("*", "").replace("#", "").replace("|DSML|", "").strip()
        
        if not t_limpio: return None
        archivo = "audio_temp.mp3"
        try:
            comm = edge_tts.Communicate(t_limpio, "es-AR-TomasNeural")
            await comm.save(archivo)
            with open(archivo, "rb") as f: data = f.read()
            os.remove(archivo)
            return base64.b64encode(data).decode()
        except: return None

    # --- 5. INTERFAZ DE CHAT ---
    st.title("🤖 Hache")
    st.caption("Conectado | Internet: OK | Memoria: OK | Arte: OK")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Dibujar historial
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if "img" in m: st.image(m["img"])

    # Entrada del usuario
    if prompt := st.chat_input("¿Qué hacemos hoy, Lio?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            # Configuración de herramientas
            tools = [
                {"type": "function", "function": {"name": "buscar_web", "description": "Busca noticias actuales, resultados deportivos y clima.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
                {"type": "function", "function": {"name": "memorizar", "description": "Guarda gustos o datos del usuario.", "parameters": {"type": "object", "properties": {"dato": {"type": "string"}, "tema": {"type": "string"}}, "required": ["dato", "tema"]}}},
                {"type": "function", "function": {"name": "recordar", "description": "Busca en tus propios recuerdos.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
                {"type": "function", "function": {"name": "dibujar", "description": "Crea una imagen artística.", "parameters": {"type": "object", "properties": {"prompt": {"type": "string", "description": "Descripción en inglés"}}, "required": ["prompt"]}}}
            ]

            sys_prompt = "Eres Hache, asistente de Lio. Eres de Argentina. Si te preguntan algo de actualidad (como un partido), usa 'buscar_web' OBLIGATORIAMENTE. Responde de forma limpia, sin usar código, ni etiquetas, ni formato markdown complejo."
            
            api_messages = [{"role": "system", "content": sys_prompt}]
            for m in st.session_state.messages:
                api_messages.append({"role": m["role"], "content": m["content"]})

            img_url = None
            
            # --- FASE 1: PENSAMIENTO (Análisis de herramientas) ---
            try:
                # temperature=0.1 hace que la IA sea menos creativa al elegir herramientas y no cometa errores de formato
                res_inicial = client.chat.completions.create(
                    model="deepseek-chat", 
                    messages=api_messages, 
                    tools=tools,
                    temperature=0.1 
                )
                msg_ia = res_inicial.choices[0].message
            except Exception as e:
                st.error(f"Fallo de conexión: {e}")
                st.stop()

            # Si la IA decidió usar una herramienta
            if msg_ia.tool_calls:
                api_messages.append(msg_ia) # Guardamos su decisión
                
                for t in msg_ia.tool_calls:
                    # Limpiamos los argumentos por si la IA metió comillas raras
                    args_str = t.function.arguments.replace("```json", "").replace("```", "").strip()
                    args = json.loads(args_str)
                    
                    # Ejecutamos la herramienta que eligió
                    if t.function.name == "buscar_web":
                        with st.spinner(f"🌍 Buscando: {args.get('query')}..."):
                            tool_res = buscar_web(args.get('query'))
                    elif t.function.name == "memorizar":
                        with st.spinner("🧠 Guardando recuerdo..."):
                            tool_res = memorizar(args.get('dato'), args.get('tema'))
                    elif t.function.name == "recordar":
                        with st.spinner("🔍 Revisando memoria..."):
                            tool_res = recordar(args.get('query'))
                    elif t.function.name == "dibujar":
                        with st.spinner("🎨 Creando obra de arte..."):
                            img_url = dibujar(args.get('prompt'))
                            tool_res = "Imagen generada con éxito."
                    else:
                        tool_res = "Error interno."
                        
                    api_messages.append({"role": "tool", "tool_call_id": t.id, "name": t.function.name, "content": tool_res})

                # --- FASE 2: RESPUESTA FINAL (Con Streaming) ---
                holder = st.empty()
                full_txt = ""
                stream = client.chat.completions.create(model="deepseek-chat", messages=api_messages, stream=True)
                
                for chunk in stream:
                    token = chunk.choices[0].delta.content
                    if token:
                        full_txt += token
                        # Filtro visual para que nunca veas basura en pantalla
                        display_txt = re.sub(r'<.*?>', '', full_txt).replace("|DSML|", "")
                        holder.markdown(display_txt + "▌")
                
                display_txt = re.sub(r'<.*?>', '', full_txt).replace("|DSML|", "")
                holder.markdown(display_txt)

            else:
                # Si no usó herramientas, procesamos su respuesta directa
                holder = st.empty()
                full_txt = msg_ia.content
                display_txt = re.sub(r'<.*?>', '', full_txt).replace("|DSML|", "")
                holder.markdown(display_txt)

            # --- FASE 3: GUARDADO Y AUDIO ---
            new_msg = {"role": "assistant", "content": display_txt}
            if img_url:
                st.image(img_url)
                new_msg["img"] = img_url
            st.session_state.messages.append(new_msg)

            # Disparamos la voz
            b64_audio = asyncio.run(generar_audio(display_txt))
            if b64_audio:
                st.components.v1.html(f'<audio autoplay src="data:audio/mp3;base64,{b64_audio}">', height=0)
