# settings.py
import os
from dotenv import load_dotenv

load_dotenv()

# Obrigatório
TOKEN = os.getenv("DISCORD_TOKEN")

# Operação (opcional via env)
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
# Intervalo do scanner: 6 em 6 horas (360 minutos)
try:
    LOOP_MINUTES = int(os.getenv("LOOP_MINUTES", "360"))
except ValueError:
    LOOP_MINUTES = 360

# Logging Level (INFO, DEBUG, WARNING, ERROR)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
