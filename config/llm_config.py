# config/llm_config.py - Mise à jour pour utiliser Together API avec LangGraph et ChatMessageHistory corrigé
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from typing import Annotated, TypedDict
from langchain_community.chat_message_histories import ChatMessageHistory  # Import corrigé

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

# Définir l'état du graphe
class State(TypedDict):
    messages: Annotated[list, "add_messages"]

# Fonction pour résumer les messages si nécessaire
def summarize_conversation(state: State) -> State:
    messages = state["messages"]
    total_tokens = sum(len(str(msg.content).split()) for msg in messages)  # Estimation simple des tokens
    if total_tokens > 500:  # Respecter votre max_token_limit
        # Garder les messages récents et résumer le reste
        to_summarize = []
        recent_messages = []
        current_tokens = 0
        
        # Parcourir les messages en sens inverse pour prioriser les récents
        for msg in reversed(messages):
            msg_tokens = len(str(msg.content).split())
            if current_tokens + msg_tokens <= 250:  # Garder environ la moitié des tokens
                recent_messages.insert(0, msg)
                current_tokens += msg_tokens
            else:
                to_summarize.insert(0, msg)

        if to_summarize:
            # Générer un résumé avec le LLM
            summary_prompt = (
                "Résumez la conversation suivante en une phrase concise :\n" +
                "\n".join([f"{msg.type}: {msg.content}" for msg in to_summarize])
            )
            summary = llm.invoke([SystemMessage(content=summary_prompt)]).content
            state["messages"] = [SystemMessage(content=f"Résumé: {summary}")] + recent_messages
    return state

# Fonction pour appeler le LLM avec l'état actuel
def call_model(state: State) -> State:
    response = llm.invoke(state["messages"])
    state["messages"].append(response)
    return state

# Construire le graphe
workflow = StateGraph(State)
workflow.add_node("summarize", summarize_conversation)
workflow.add_node("chat", call_model)
workflow.set_entry_point("summarize")
workflow.add_edge("summarize", "chat")
workflow.add_edge("chat", END)

# Compiler le graphe
graph = workflow.compile()

# Fonction utilitaire pour interagir avec le graphe
def get_response(user_input: str, history: ChatMessageHistory = None):
    if history is None:
        history = ChatMessageHistory()
    state = {"messages": history.messages}
    state["messages"].append(HumanMessage(content=user_input))
    output = graph.invoke(state)
    history.messages = output["messages"]
    return output["messages"][-1].content, history

