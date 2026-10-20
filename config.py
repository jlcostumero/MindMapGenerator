import os
import secrets
from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Flask & Session Settings
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
SESSION_TYPE = os.getenv("SESSION_TYPE", "filesystem")
SESSION_FILE_DIR = os.getenv("SESSION_FILE_DIR", os.path.join(BASE_DIR, "data", "sessions"))

# Storage / Database (MongoDB es opcional, si no esta activo se usa data/ local)
MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB = os.getenv("MONGO_DB", "maps")

# LLM Configuration (DeepSeek / OpenAI Compatible API)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", os.getenv("OPENAI_API_KEY", ""))
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# YouTube Proxy (Opcional, dejar vacio para conexion directa)
YOUTUBE_PROXY = os.getenv("YOUTUBE_PROXY", "").strip()

# Application URLs
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:1000").rstrip("/")

# Server Binding
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "1000"))
