import openai
import io
import json
import os
import re
from markupsafe import escape
from flask import Flask, render_template, request, jsonify, session
from flask_session import Session
import random
from pymongo import MongoClient, ASCENDING
from pymongo.server_api import ServerApi
import datetime
import uuid
from hashlib import sha256

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session/'
Session(app)

def generate_user_id(request):
    
    compositionId = request.remote_addr
    compositionId = compositionId + request.headers.get('User-Agent')
    if request.headers.get('Accept-Language'):
        compositionId = compositionId + str(request.headers.get('Accept-Language'))
    if request.headers.get('Accept-Encoding'):
        compositionId = compositionId + str(request.headers.get('Accept-Encoding'))
    if request.remote_addr:
        compositionId = compositionId + str(request.remote_addr)
    hashed = sha256((compositionId).encode()).hexdigest()
    return str(hashed)


client = MongoClient()
URI = "mongodb://localhost:27017"
DATABASE = "maps"
MAPS_COLLECTION = "map"
db = client[DATABASE]




if MAPS_COLLECTION not in db.list_collection_names():
  db.create_collection(MAPS_COLLECTION)
MapasColeccion = db["map"]
# MapasColeccion.create_index([('id', 1)], unique=True)
# MapasColeccion.create_index([('idUser', 1)], unique=False)
# MapasColeccion.create_index([('name', 1)], unique=False)


openai.api_key=""


contenido = ""
with open('consulta.txt', 'r', encoding='utf-8') as archivo:
    contenido = archivo.read()

@app.route('/')
def index():
    user_id = generate_user_id(request)
    session['user_id'] = user_id
    return render_template('index.html')
    

@app.route('/generar', methods=['POST'])
def generar():
    texto = request.form['texto']
    id = session.get('user_id')
    # id = ''
    # if 'id' in request.form:
    #     id = request.form['id']
    # else:
    #     id = random.randrange(10000, 99999)
    #     id = 10
    #     # id  = uuid.uuid4()
    texto = contenido.replace("[articulo]", texto)
    messages = []
    messages.append({"role":"system","content":"assistant to get json string"})
    messages.append({"role":"user","content": texto})
    print("LLAMADA API")


    try:
        response=openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages
        )
        reply = response["choices"][0]["message"]["content"]
        texto_generado = reply  
        print(reply)
        texto_generado = eliminar_texto_izquierda_derecha(reply)
        texto_generado = quitar_texto(reply)
        texto_generado = corregir_json(texto_generado)
        texto_generado = corregir_json(texto_generado)
        objeto_json = json.loads(texto_generado.replace('\n','').replace('\"','"'))
        if objeto_json['map'] and objeto_json['map']['name']:
            # Crear un documento
            uu_id  = uuid.uuid4()
            documento = {
                "name": objeto_json['map']['name'],
                 "_id": str(uu_id),
                "id": str(uu_id),
                "idUser": session['user_id'],
                "data": objeto_json,
                "date": datetime.datetime.now()
            }
            result = MapasColeccion.insert_one(documento)
            return render_template('map.html', texto_generado=texto_generado, idMap='', id=id)
        else:
            return render_template('index.html')


    except OSError as err:
        print("OS error:", err)
    except ValueError:
        nombreFichero = 'Error-' + str(uuid.uuid4()) + ".txt"
        with open("diagrams/" + nombreFichero, "w") as file:
            file.write(texto_generado)
        print("Could not convert data to an integer.")
        raise

@app.route('/diagram/<idMap>', methods=['GET'])
def diagram(idMap):
    # filtro = {"id": idMap, "idUser": session['user_id']}
    if session['user_id'] == None:
        user_id = generate_user_id(request)
        session['user_id'] = user_id
    filtro = {"id": idMap}
    resultado = MapasColeccion.find_one(filtro)
    contenido = json.dumps(resultado["data"])
    return render_template('map.html', texto_generado=contenido, nombre=resultado["name"], id=idMap)
    # return render_template('map.html', texto_generado=contenido, idMap=resultado["id"], id=id)
    # resultado = MapasColeccion.find_one({"name": name, "idUser": int(id)}).data

    # # Comprobar si el archivo existe
    # file = request.remote_addr + '-' + name + ".txt"
    # if file not in os.listdir('./diagrams'):
    #     contenido = "{'map': {}})"

    # # Comprobar si el archivo es de tipo .txt
    # if not name.endswith('.txt'):
    #    contenido = "{'map': {}})"
    # resultado = MapasColeccion.find_one({"name": name, "idUser": int(id)})
    # # Leer el contenido del archivo
    # with open(f"./diagrams/{file}", 'r') as f:
    #     contenido = f.read()
    # contenido = corregir_json(contenido)
    # contenido = corregir_json(contenido)
    # # contenido = json.loads(resultado.data)
    # return render_template('map.html', texto_generado=contenido, nombre=name, id=id)

@app.route('/maps/<id>', methods=['GET'])
def mapsId(id):
    id =session['user_id']
    return maps(id)

@app.route('/maps', methods=['GET'])
def mapsAll():
    id =session['user_id']
    return maps(id)

def maps(id):
    filtro = {"idUser": id}
    proyeccion = {"name": 1, "id": 1, "_id": 0}
    resultados = MapasColeccion.find(filtro, proyeccion)
    registros = [{"name": r["name"], "id": r["id"]} for r in resultados]
    respuesta = {'maps': registros}
    return jsonify(respuesta)

    # # Ejecutar la consulta y obtener el array de objetos
    # resultado = MapasColeccion.find(filtro, proyeccion)

    # # Obtener la lista de archivos en la carpeta 'diagrams'
    # ruta_carpeta = './diagrams'
    # archivos = os.listdir(ruta_carpeta)
    # if id == "":   
    #     id = request.remote_addr + '-'
    #     patron = re.compile(f'^{re.escape(id)}.*\.txt$')
    # else:
    #     id = str(id) + '-'
    #     patron = re.compile(f'^{re.escape(id)}(.*)\.txt$')


    # # Filtrar los archivos que tienen la extensión .txt
    # archivos_txt = [archivo for archivo in archivos if patron.match(archivo)]
    # archivos_txt = [os.path.splitext(archivo)[0].replace(id, '')  for archivo in archivos_txt]

    # # Consulta
    # condicion = {"userId": "valor_deseado"}
    # resultados = MapasColeccion.find({"iduser": 100}).sort("date", ASCENDING)

    # # Obtener los campos name de los registros que cumplen la condición
    # nombres = [r["name"] for r in resultados]

    # # Construir una respuesta JSON con la lista de archivos .txt
    # respuesta = {'maps': archivos_txt}

    # # Devolver la respuesta en formato JSON
    # return jsonify(respuesta)

@app.route('/<idMap>/<id>', methods=['GET'])
def mapId(idMap, id):
    return map(idMap, id)

@app.route('/<idMap>', methods=['GET'])
def mapName(idMap):
    return map(idMap, None)

def map(idMap, id):
    # Comprobar si el archivo existe
    if name not in os.listdir('./diagrams'):
        return jsonify({'map': {}})

    # Comprobar si el archivo es de tipo .txt
    if not name.endswith('.txt'):
       return jsonify({'map': {}})

    # Leer el contenido del archivo
    with open(f"./diagrams/{name}", 'r') as f:
        contenido = f.read()
    if id:
        resultado = MapasColeccion.find_one({"id": idMap, "idUser": id}).data
    else:
        resultado = MapasColeccion.find_one({"id": idMap}).data
    # Decodificar el contenido JSON
    try:
        json_data = json.loads(contenido)
    except ValueError:
        return jsonify({'map': {}})

    # Construir una respuesta JSON con el contenido del archivo
    respuesta = json_data

    # Devolver la respuesta en formato JSON
    return jsonify(respuesta)

        
def quitar_caracteres_especiales(cadena):
    """
    Esta función elimina los caracteres especiales de una cadena de texto
    y devuelve una nueva cadena sin ellos.
    """
    # Expresión regular para encontrar caracteres especiales
    regex = r'[^\w\s]'
    
    # Sustituir los caracteres especiales por espacios en blanco
    nueva_cadena = re.sub(regex, '', cadena)
    
    return nueva_cadena

def quitar_texto(json_string):
    json_string = json_string.replace('\n', ' ')
    # Utilizar una expresión regular para buscar cualquier texto que esté antes o después del JSON
    regex = r'^[\s\S]*?(\{.*\})[\s\S]*?$'
    match = re.search(regex, json_string)

    # Si se encontró una coincidencia, extraer el JSON y convertirlo a un objeto
    if match:
        return match.group(1) 
    else:
        # Si no se encontró una coincidencia, lanzar un error
        raise ValueError('No se encontró JSON válido en la cadena de texto')
        
def corregir_json(cadena_json):

    # Buscar patrones en la cadena JSON y agregar comas faltantes
    cadena_json_corregida = re.sub(r'(?<=\{)\s*\{', '', cadena_json)
    cadena_json_corregida = re.sub(r'}\s*{', '},{', cadena_json_corregida)
    cadena_json_corregida = re.sub(r'{\s*{', '{', cadena_json_corregida)
    cadena_json_corregida = re.sub(r']\s*{', '],{', cadena_json_corregida)
    cadena_json_corregida = re.sub(r'}\s*{', '},{', cadena_json_corregida)
    cadena_json_corregida = re.sub(r']\s*{', '],{', cadena_json_corregida)
    cadena_json_corregida = re.sub(r'\}\}$', '}', cadena_json_corregida)


    return cadena_json_corregida
        
def eliminar_texto_izquierda_derecha(cadena):
    # Encuentra la posición del primer carácter "{"
    inicio = cadena.find('{')
    # Encuentra la posición del último carácter "}"
    fin = cadena.rfind('}')
    # Si no se encuentra algún carácter, devuelve la cadena original
    if inicio == -1 or fin == -1:
        return cadena
    # Devuelve la subcadena que se encuentra entre el primer carácter "{" y el último carácter "}"
    return cadena[inicio:fin+1]

        
if __name__ == '__main__':
    app.run(debug=True)
    
    
    