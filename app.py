import os
import io
import json
import re
import time
import queue
import uuid
import datetime
import string
import ssl
import urllib.request
import requests
from datetime import timedelta
from bs4 import BeautifulSoup

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    send_from_directory,
    send_file,
    make_response,
    Response,
)
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix
from youtube_transcript_api import YouTubeTranscriptApi
import openai

import config
import storage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIAGRAMS_DIR = os.path.join(BASE_DIR, "diagrams")
os.makedirs(DIAGRAMS_DIR, exist_ok=True)

# ---------------------------------------------------------
# SSE Announcer (Server-Sent Events)
# ---------------------------------------------------------
class MessageAnnouncer:
    def __init__(self):
        self.listeners = []

    def listen(self):
        q = queue.Queue(maxsize=10)
        self.listeners.append(q)
        return q

    def announce(self, msg):
        for i in reversed(range(len(self.listeners))):
            try:
                self.listeners[i].put_nowait(msg)
            except queue.Full:
                del self.listeners[i]

    def publish(self, data, type="notificacion", channel=None):
        msg = format_sse(data, None, type, channel)
        self.announce(msg)


sse2 = MessageAnnouncer()


def format_sse(data, event=None, type=None, channel=None) -> str:
    msg = f"data: {json.dumps(data)}\n\n"
    client_id = channel or session.get("user_id", "")
    if event is not None:
        msg = f"event: {event}\n{msg}"
    if type is not None:
        msg = f"event: {type}\n{msg}"
    if client_id:
        msg = f"client_id: {client_id}\n{msg}"
    return msg


# ---------------------------------------------------------
# Flask App Setup
# ---------------------------------------------------------
app = Flask(__name__, static_folder=None)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = config.SECRET_KEY

app.config["SESSION_TYPE"] = config.SESSION_TYPE
app.config["SESSION_FILE_DIR"] = config.SESSION_FILE_DIR
os.makedirs(config.SESSION_FILE_DIR, exist_ok=True)
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)
Session(app)

# Persistencia desacoplada (MongoDB con fallback a JSON local)
db = storage.init_storage(BASE_DIR, config.MONGO_URI, config.MONGO_DB)

# Configuración LLM (DeepSeek / OpenAI compatible)
openai.api_base = config.DEEPSEEK_BASE_URL
openai.api_key = config.DEEPSEEK_API_KEY


def get_or_create_user_id() -> str:
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())
        session["dark_mode"] = False
        session["shared_id"] = "0"
    return session["user_id"]


# ---------------------------------------------------------
# Carga de Prompts
# ---------------------------------------------------------
def read_text_file(filename: str) -> str:
    p_prompts = os.path.join(BASE_DIR, "prompts", filename)
    if os.path.exists(p_prompts):
        with open(p_prompts, "r", encoding="utf-8") as f:
            return f.read()
    p_root = os.path.join(BASE_DIR, filename)
    with open(p_root, "r", encoding="utf-8") as f:
        return f.read()


contenido = read_text_file("consulta.txt")
contenidoarbol = read_text_file("consultaarbol.txt")
consultadescripciones = read_text_file("consultadescripciones.txt")


# ---------------------------------------------------------
# Robust JSON Parsing for LLMs
# ---------------------------------------------------------
def parse_llm_json(raw_text: str) -> dict:
    if not raw_text:
        raise ValueError("Respuesta vacía del modelo")

    text = raw_text.strip()

    # 1. Extraer bloques de markdown ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()

    # 2. Encontrar límites del JSON ({ ... })
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    # 3. Intentar parseo directo
    try:
        return json.loads(text)
    except Exception:
        pass

    # 4. Limpieza de saltos de linea y comas colgantes
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 5. Reparación heurística de cierre
    for suffix in ["}", "]}", '"]}', '"}]}']:
        try:
            return json.loads(cleaned + suffix)
        except Exception:
            continue

    raise ValueError(f"No se pudo estructurar el JSON devuelto por el LLM")


# ---------------------------------------------------------
# Utilidades de YouTube y Web Scraping
# ---------------------------------------------------------
def get_youtube_code(url: str):
    if not url:
        return None
    match = re.search(r"(?:v=|\/|youtu\.be\/|embed\/)([0-9A-Za-z_-]{11})", str(url))
    return match.group(1) if match else None


def is_youtube_url(text: str) -> bool:
    if not text:
        return False
    pattern = r"(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})"
    return bool(re.match(pattern, text))


def extract_transcript_text(text_lines) -> str:
    if not text_lines:
        return ""
    parts = []
    for item in text_lines:
        if isinstance(item, dict):
            parts.append(item.get("text", ""))
        elif hasattr(item, "text"):
            parts.append(getattr(item, "text", ""))
        else:
            parts.append(str(item))
    return " ".join(parts).strip()


def fetch_youtube_transcript(video_id: str):
    if not video_id:
        return None
    try:
        proxy_config = None
        if config.YOUTUBE_PROXY:
            try:
                from youtube_transcript_api.proxies import GenericProxyConfig
                proxy_config = GenericProxyConfig(
                    http_url=config.YOUTUBE_PROXY, https_url=config.YOUTUBE_PROXY
                )
            except Exception as pe:
                print(f"[YouTube] Aviso al configurar proxy: {pe}")

        api = (
            YouTubeTranscriptApi(proxy_config=proxy_config)
            if proxy_config
            else YouTubeTranscriptApi()
        )

        try:
            return api.fetch(video_id, languages=["es", "en"])
        except Exception:
            pass

        transcript_list = api.list(video_id)
        try:
            transcript = transcript_list.find_transcript(["es", "en"])
        except Exception:
            for t in transcript_list:
                if getattr(t, "is_translatable", False):
                    transcript = t.translate("es")
                    break
            else:
                return None
        return transcript.fetch()
    except Exception as e:
        print(f"[YouTube] Error descargando transcripción: {e}")
        return None


def es_url(cadena: str) -> bool:
    regex = r"^(https?:\/\/)?([\da-z\.-]+)\.([a-z\.]{2,6})([\/\w \.-]*)*\/?$"
    return bool(re.match(regex, cadena))


def url_to_text(url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else "Página Web"
    # Eliminar scripts y estilos
    for s in soup(["script", "style", "noscript", "svg"]):
        s.extract()
    text = " ".join(soup.get_text().split())
    return {"text": text, "title": title}


# ---------------------------------------------------------
# Estructuración de Nodos de Mapas
# ---------------------------------------------------------
def add_idlevel(node: dict, level: str = "0"):
    node["idlevel"] = level
    if "children" in node:
        for i, child in enumerate(node["children"], start=1):
            child_level = f"{i}" if level == "0" else f"{level}.{i}"
            add_idlevel(child, child_level)


def generate_text(node: dict, level: int = 0, completo: bool = True, group: str = "") -> str:
    indentation = "\t" * level
    if level == 0:
        number = group
        groupdot = f"{group}." if group != "" else ""
    else:
        groupdot = group
        number = group + node.get("idlevel", "")

    name = node.get("name", "")
    desc = node.get("description", "")
    text = f"{indentation}{number} {name}\n{indentation}{desc}" if (completo and desc) else f"{indentation}{number} {name}"

    keywords = ""
    if "keywords" in node and completo and node["keywords"]:
        keywords = ", ".join(node["keywords"])
        text += f"\n{indentation}{keywords}\n\n"
    else:
        text += "\n\n"

    if "children" in node:
        for child in node["children"]:
            text += generate_text(child, level + 1, completo, groupdot)
    return text


def cargar_descripciones(objeto: dict, descripciones: dict) -> list:
    def cargar_recursivo(node, no_asignados):
        if "children" in node:
            for child in node["children"]:
                desc = next(
                    (d for d in descripciones.get("descriptions", []) if d.get("id") == child.get("idlevel")),
                    None,
                )
                if desc:
                    child["description"] = desc.get("description", "")
                    child["keywords"] = desc.get("keywords", [])
                elif "description" not in child:
                    no_asignados.append(child.get("idlevel"))
                cargar_recursivo(child, no_asignados)

    no_asig = []
    if "map" in objeto:
        cargar_recursivo(objeto["map"], no_asig)
    return no_asig


# ---------------------------------------------------------
# Lógica de Generación de Mapas con LLM
# ---------------------------------------------------------
def montarConsulta(llamada, parametroTexto, size, consulta, estructura=None, excepciones=None):
    if llamada == 0:
        if isinstance(parametroTexto, dict):
            filtro = (
                f'Filtro: Tengo el texto de una pagina web relacionado con "{parametroTexto.get("title", "")}" '
                'y quiero extraer unicamente la informacion relevante.'
            )
            texto = (
                consulta.replace("[contenido]", parametroTexto.get("text", ""))
                .replace("[Filtro]", filtro)
                .replace("[title]", parametroTexto.get("title", ""))
            )
        else:
            p_str = str(parametroTexto)
            if len(p_str) < 10:
                sse2.publish({"error": "Texto demasiado corto para ser procesado"}, channel=session.get("user_id"))
                return jsonify({"error": "Texto demasiado corto para ser procesado"})
            texto = consulta.replace("[contenido]", p_str).replace("[Filtro]", "")

        if size != "100":
            resumen = f"Resumen: Resumir el contenido usando los datos mas importantes al {size}% del contenido."
            texto = texto.replace("[Resumen]", resumen)
        else:
            texto = texto.replace("[Resumen]", "")

        if estructura:
            texto = texto.replace("[estructura]", estructura)
        else:
            texto = texto.replace("[estructura]", "")

        if excepciones:
            texto = texto.replace(
                "[excepciones]",
                f"0. Incluir solamente en la lista las descripciones con los siguientes codigos: {excepciones}",
            )
        else:
            texto = texto.replace("[excepciones]", "")
    else:
        texto = str(parametroTexto)
    return texto


def generarListaMapa(idList, parametroTexto, size, restService, llamada, esUrl):
    user_id = session.get("user_id", "")
    if len(str(parametroTexto)) < 200 and not esUrl:
        consulta = contenidoarbol
        tipo = "arbol"
    else:
        consulta = contenido
        tipo = "normal"

    sse2.publish({"status": "analizando", "mensaje": "Procesando contenido con IA..."}, channel=user_id)
    texto = montarConsulta(llamada, parametroTexto, size, consulta, None)
    return llamadaAPI(restService, texto, llamada, idList, size, tipo, parametroTexto, None, esUrl)


def llamadaAPI(restService, texto, llamada, idList, size, tipo, parametroTexto, objeto, esUrl=False):
    user_id = session.get("user_id", "")
    messages = [
        {"role": "system", "content": "Assistant that generates structured JSON for mind maps."},
        {"role": "user", "content": texto},
    ]

    try:
        start_time = time.time()
        response = openai.ChatCompletion.create(
            model=config.DEEPSEEK_MODEL,
            messages=messages,
            max_tokens=4096,
            temperature=0.5,
        )
        elapsed = time.time() - start_time
        sse2.publish({"time": round(elapsed, 2)}, channel=user_id)

        reply = response["choices"][0]["message"]["content"]
        objeto_json = parse_llm_json(reply)

        if tipo == "descripciones":
            no_asignados = cargar_descripciones(objeto, objeto_json)
            if len(no_asignados) > 0 and llamada < 2:
                excepciones = ", ".join(no_asignados)
                estructura = generate_text(objeto.get("map", {}), 0, False)
                texto = montarConsulta(llamada, parametroTexto, size, consultadescripciones, estructura, excepciones)
                return llamadaAPI(restService, texto, llamada + 1, idList, size, "descripciones", parametroTexto, objeto, esUrl)
            else:
                return insertMap(objeto, idList, restService, size, texto)
        else:
            if "map" in objeto_json and objeto_json["map"].get("name"):
                add_idlevel(objeto_json["map"])
                if tipo == "normal":
                    return insertMap(objeto_json, idList, restService, size, texto)
                else:
                    estructura = generate_text(objeto_json["map"], 0, False)
                    texto_desc = montarConsulta(0, parametroTexto, size, consultadescripciones, estructura)
                    return llamadaAPI(restService, texto_desc, 0, idList, size, "descripciones", parametroTexto, objeto_json, esUrl)
            else:
                sse2.publish({"error": "Error generando estructura de mapa"}, channel=user_id)
                return jsonify({"error": "Error generando estructura de mapa"})

    except Exception as e:
        print(f"[LLM Engine] Error en llamadaAPI (intento {llamada}): {e}")
        if llamada < 2:
            return llamadaAPI(restService, texto, llamada + 1, idList, size, tipo, parametroTexto, objeto, esUrl)
        sse2.publish({"error": f"Error del motor de IA: {str(e)}"}, channel=user_id)
        return jsonify({"error": f"No se pudo completar la generación: {str(e)}"})


def insertMap(objeto_json, idList, restService, size, texto, user_id=None):
    uu_id = str(uuid.uuid4())
    objeto_json["id"] = uu_id
    user_id = user_id or session.get("user_id", "local_user")

    map_root = objeto_json.get("map", {})
    short_title = map_root.get("shorttitle") or map_root.get("name") or "Mapa Mental"

    if idList is None:
        idList = uu_id
        list_doc = {
            "name": short_title,
            "id": idList,
            "idUser": user_id,
            "date": datetime.datetime.now(),
            "delete": False,
        }
        db.save_list(list_doc)
    else:
        existing_list = db.get_list(idList)
        if existing_list:
            short_title = existing_list.get("name", short_title)

    map_doc = {
        "name": map_root.get("name", short_title),
        "id": uu_id,
        "idList": idList,
        "idUser": user_id,
        "request": {"text": str(texto)},
        "order": 1,
        "delete": False,
        "data": objeto_json,
        "size": int(size) if str(size).isdigit() else 30,
        "date": datetime.datetime.now(),
    }
    db.save_map(map_doc)

    objeto_json["map"]["id"] = uu_id
    objeto_json["map"]["idList"] = idList
    objeto_json["map"]["owner"] = True

    try:
        sse2.publish(objeto_json, type="notificacion", channel=user_id)
    except Exception:
        pass

    return jsonify(objeto_json)


# ---------------------------------------------------------
# Rutas Principales
# ---------------------------------------------------------
@app.route("/")
def route_index():
    user_id = get_or_create_user_id()
    session["shared_id"] = "0"
    dark_mode = session.get("dark_mode", False)
    return render_template("index.html", darkmode=dark_mode, shared=session["shared_id"])


@app.route("/calculo")
def calculo():
    return render_template("calculo.html")


@app.route("/notificaciones", methods=["GET"])
def notificaciones():
    client_id = get_or_create_user_id()

    def stream():
        messages = sse2.listen()
        while True:
            msg = messages.get()
            match = re.search(r"client_id:\s+(.+)", msg)
            if match:
                target = match.group(1).strip()
                if target == client_id:
                    yield msg
            else:
                yield msg

    return Response(stream(), mimetype="text/event-stream")


@app.route("/generar", methods=["POST"])
def generar():
    get_or_create_user_id()
    data = request.json or {}
    text = data.get("text", "")
    size = data.get("size", "30")

    if is_youtube_url(text):
        lines = fetch_youtube_transcript(get_youtube_code(text))
        if not lines:
            sse2.publish({"error": "No se pudo obtener la transcripción del video"}, channel=session.get("user_id"))
            return jsonify({"error": "No se pudo obtener la transcripción del video"})
        t_text = extract_transcript_text(lines)
        return generarListaMapa(None, t_text, size, False, 0, True)

    elif es_url(text):
        try:
            page_data = url_to_text(text)
            return generarListaMapa(None, page_data, size, False, 0, True)
        except Exception as e:
            sse2.publish({"error": f"Página no accesible: {str(e)}"}, channel=session.get("user_id"))
            return jsonify({"error": f"Página no accesible: {str(e)}"})
    else:
        return generarListaMapa(None, text, size, False, 0, False)


@app.route("/add", methods=["POST"])
def add():
    get_or_create_user_id()
    data = request.json or {}
    text = data.get("text", "")
    size = data.get("size", "30")
    id_list = data.get("id")

    if is_youtube_url(text):
        lines = fetch_youtube_transcript(get_youtube_code(text))
        if not lines:
            return jsonify({"error": "Problema con la transcripción del video"})
        t_text = extract_transcript_text(lines)
        return generarListaMapa(id_list, t_text, size, True, 0, True)
    elif es_url(text):
        try:
            page_data = url_to_text(text)
            return generarListaMapa(id_list, page_data, size, False, 0, True)
        except Exception:
            return jsonify({"error": "Página no accesible"})
    else:
        return generarListaMapa(id_list, text, size, True, 0, False)


@app.route("/diagram/<idList>", methods=["GET"])
def diagram(idList):
    user_id = get_or_create_user_id()
    dark_mode = session.get("dark_mode", False)

    list_doc = db.get_list(idList)
    name = list_doc.get("name", "Mapa Mental") if list_doc else "Mapa Mental"
    maps_list = db.get_maps_by_list(idList)

    contenido_parts = []
    for mapa in maps_list:
        data = mapa.get("data", {})
        if "map" in data:
            data["map"]["id"] = mapa.get("id")
            data["map"]["idList"] = idList
            data["map"]["owner"] = mapa.get("idUser") == user_id
        contenido_parts.append(json.dumps(data))

    contenido = ", ".join(contenido_parts)
    is_owner = list_doc.get("idUser") == user_id if list_doc else True

    return render_template(
        "map.html",
        texto_generado=contenido,
        name=name,
        idList=idList,
        user=is_owner,
        darkmode=dark_mode,
        shared=session.get("shared_id", "0"),
    )


@app.route("/maps", methods=["GET"])
def list_maps():
    user_id = get_or_create_user_id()
    lists = db.get_user_lists(user_id)
    records = [{"name": l.get("name"), "id": l.get("id")} for l in lists]
    return jsonify({"maps": records})


@app.route("/delete/<idList>", methods=["GET", "POST"])
@app.route("/deletelist/<idList>", methods=["POST"])
def delete_list(idList):
    user_id = get_or_create_user_id()
    ok = db.delete_list(idList, user_id)
    return jsonify({"status": "OK" if ok else "not_found"})


@app.route("/deletemap/<idMap>", methods=["POST"])
def delete_map(idMap):
    user_id = get_or_create_user_id()
    ok = db.delete_map(idMap, user_id)
    return jsonify({"status": "OK" if ok else "not_found"})


@app.route("/refreshmap/<idMap>", methods=["POST"])
def refresh_map(idMap):
    user_id = get_or_create_user_id()
    old = db.get_map(idMap)
    if not old:
        return jsonify({"error": "Mapa no encontrado"}), 404

    size = str(old.get("size", 30))
    text = old.get("request", {}).get("text", "")
    id_list = old.get("idList")

    result = generarListaMapa(id_list, text, size, False, 0, False)
    db.delete_map(idMap, user_id)
    return result


@app.route("/darkmode/<on>", methods=["POST"])
def darkmode(on):
    get_or_create_user_id()
    session["dark_mode"] = on == "1"
    return jsonify({"status": "OK"})


@app.route("/txt/<id>", methods=["GET"])
def export_txt(id):
    map_doc = db.get_map(id)
    if not map_doc or "data" not in map_doc or "map" not in map_doc["data"]:
        return jsonify({"error": "Mapa no encontrado"}), 404

    map_root = map_doc["data"]["map"]
    add_idlevel(map_root)
    text_content = generate_text(map_root)

    resp = make_response(text_content)
    filename = f"{map_doc.get('name', 'mapa')}.txt"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    return resp


# ---------------------------------------------------------
# Rutas Estáticas
# ---------------------------------------------------------
@app.route("/favicon.ico")
def favicon():
    return send_file(os.path.join(BASE_DIR, "icon.svg"), mimetype="image/svg+xml")


@app.route("/svg")
def get_svg():
    return send_file(os.path.join(BASE_DIR, "icon.svg"), mimetype="image/svg+xml")


@app.route("/css/<path:filename>")
def serve_css(filename):
    return send_from_directory(os.path.join(BASE_DIR, "css"), filename)


@app.route("/js/<path:filename>")
def serve_js(filename):
    return send_from_directory(os.path.join(BASE_DIR, "js"), filename)


@app.route("/icons.woff2")
def serve_icons():
    return send_file(os.path.join(BASE_DIR, "resources", "icons.woff2"), mimetype="font/woff2")


if __name__ == "__main__":
    print(f"MindMapGenerator iniciado en http://{config.HOST}:{config.PORT}")
    app.run(port=config.PORT, host=config.HOST)
