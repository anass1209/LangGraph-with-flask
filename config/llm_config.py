# config/llm_config.py - Mise à jour pour utiliser Together API avec un modèle récent
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.memory import ConversationSummaryMemory

# Charger la clé API depuis le fichier .env
load_dotenv()
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

if not TOGETHER_API_KEY:
    raise ValueError("⚠️ TOGETHER_API_KEY est manquant. Vérifie ton fichier .env !")

# Configuration du modèle LLM
llm = ChatOpenAI(
    base_url="https://api.together.xyz",
    api_key=TOGETHER_API_KEY,
    model="meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
    temperature=0.0
)

# Initialiser la mémoire de résumé de conversation
memory = ConversationSummaryMemory(
    llm=llm,
    max_token_limit=500,
    return_messages=True
)