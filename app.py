import openai
import io
import json
import os
import re
from markupsafe import escape
from flask import Flask, render_template, request
from pyngrok import ngrok, conf

app = Flask(__name__)

openai.api_key=os.environ['api_key']
ngrokToken=os.environ['ngrokToken']
conf.auth_token = ngrokToken
# ngrok.set_auth_token(ngrokToken)
# Open a TCP ngrok tunnel to the SSH server
# connection_string = ngrok.connect(22, "tcp").public_url

# ssh_url, port = connection_string.strip("tcp://").split(":")
# print(f" * ngrok tunnel available, access with `ssh root@{ssh_url} -p{port}`")

# Open a ngrok tunnel to the HTTP server
public_url = ngrok.connect(port=5000)
print(" * ngrok tunnel \"{}\" -> \"http://127.0.0.1:{}/\"".format(public_url, 5000))

# Update any base URLs to use the public ngrok URL
app.config["BASE_URL"] = public_url

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
    # Utilizar una expresión regular para buscar cualquier texto que esté antes o después del JSON
    regex = r'^[\s\S]*?(\{.*\})[\s\S]*?$'
    match = re.search(regex, json_string)

    # Si se encontró una coincidencia, extraer el JSON y convertirlo a un objeto
    if match:
        return match.group(1) 
    else:
        # Si no se encontró una coincidencia, lanzar un error
        raise ValueError('No se encontró JSON válido en la cadena de texto')
        
if __name__ == '__main__':
    app.run(debug=True)
    
    