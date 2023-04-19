import openai
import io
import json
import os
import re
from markupsafe import escape
from flask import Flask, render_template, request, jsonify
from flask_ngrok import run_with_ngrok

app = Flask(__name__)
run_with_ngrok(app)

openai.api_key=os.environ['api_key']


contenido = ""
with open('query.txt', 'r', encoding='utf-8') as archivo:
    contenido = archivo.read()

@app.route('/')
def index():
    return render_template('index.html')
    

@app.route('/generar', methods=['POST'])
def generar():
    texto = request.form['texto']
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
        objeto_json = json.loads(texto_generado)
        nombreFichero = request.remote_addr + '-' + quitar_caracteres_especiales(objeto_json['map']['name']) + ".txt"
        with open("diagrams/" + nombreFichero, "w") as file:
            file.write(texto_generado)
        return render_template('map.html', texto_generado=texto_generado)

    except OSError as err:
        print("OS error:", err)
    except ValueError:
        print("Could not convert data to an integer.")
    except Exception as err:
        print(f"Unexpected {err=}, {type(err)=}")
        raise

@app.route('/load/<name>', methods=['GET'])
def load(name):
    # Comprobar si el archivo existe
    name = request.remote_addr + '-' + name + ".txt"
    if name not in os.listdir('./diagrams'):
        contenido = "{'map': {}})"

    # Comprobar si el archivo es de tipo .txt
    if not name.endswith('.txt'):
       contenido = "{'map': {}})"

    # Leer el contenido del archivo
    with open(f"./diagrams/{name}", 'r') as f:
        contenido = f.read()
    contenido = corregir_json(contenido)
    return render_template('map.html', texto_generado=contenido)


@app.route('/maps', methods=['GET'])
def maps():
    # Obtener la lista de archivos en la carpeta 'diagrams'
    ruta_carpeta = './diagrams'
    archivos = os.listdir(ruta_carpeta)
    ip = request.remote_addr + '-'
    patron = re.compile(f'^{re.escape(ip)}.*\.txt$')

    # Filtrar los archivos que tienen la extensión .txt
    archivos_txt = [archivo for archivo in archivos if patron.match(archivo)]
    archivos_txt = [os.path.splitext(archivo)[0].replace(ip, '')  for archivo in archivos_txt]

    # Construir una respuesta JSON con la lista de archivos .txt
    respuesta = {'maps': archivos_txt}

    # Devolver la respuesta en formato JSON
    return jsonify(respuesta)

@app.route('/map/<name>', methods=['GET'])
def map(name):
    # Comprobar si el archivo existe
    if name not in os.listdir('./diagrams'):
        return jsonify({'map': {}})

    # Comprobar si el archivo es de tipo .txt
    if not name.endswith('.txt'):
       return jsonify({'map': {}})

    # Leer el contenido del archivo
    with open(f"./diagrams/{name}", 'r') as f:
        contenido = f.read()

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
    cadena_json_corregida = re.sub(r'}\s*\]', '}]', cadena_json_corregida)
    cadena_json_corregida = re.sub(r'}\s*{', '},{', cadena_json_corregida)
    cadena_json_corregida = re.sub(r']\s*{', '],{', cadena_json_corregida)
    cadena_json_corregida = re.sub(r'}\s*\]', '}]', cadena_json_corregida)

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
    app.run()
    
    