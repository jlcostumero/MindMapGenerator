import openai
import io
import json
import os
import re
from markupsafe import escape
from flask import Flask, render_template, request
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
    messages.append({"role":"system","content":"assistant"})
    messages.append({"role":"user","content": texto})
    print("LLAMADA API")
    response=openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=messages
    )

    reply = response["choices"][0]["message"]["content"]
    
    texto_generado = reply  
    print(reply)
    texto_generado = quitar_texto(reply)
    return render_template('map.html', texto_generado=texto_generado)

def quitar_texto(json_string):
    json_string = json_string.replace('\n', ' ')
    json_string = corregir_json(json_string)
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
    # Analizar la cadena JSON en un objeto Python
    objeto_json = json.loads(cadena_json)

    # Convertir el objeto Python en una cadena JSON nuevamente
    cadena_json_corregida = json.dumps(objeto_json)

    # Buscar patrones en la cadena JSON y agregar comas faltantes
    cadena_json_corregida = re.sub(r'}\s*{', '},{', cadena_json_corregida)
    cadena_json_corregida = re.sub(r']\s*{', '],{', cadena_json_corregida)
    cadena_json_corregida = re.sub(r'}\s*\]', '}]', cadena_json_corregida)

    return cadena_json_corregida
        
if __name__ == '__main__':
    app.run()
    
    