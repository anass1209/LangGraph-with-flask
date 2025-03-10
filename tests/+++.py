import os
import sys
import re
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, Dict, Any, List
from langchain_core.runnables.config import RunnableConfig

# Augmenter la limite de récursion globale de Python
sys.setrecursionlimit(2000)

# Charger la clé API depuis le fichier .env
load_dotenv()
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

llm = ChatOpenAI(
    base_url="https://api.together.xyz",
    api_key=TOGETHER_API_KEY,
    model="mistralai/Mistral-7B-Instruct-v0.2",
    temperature=0
)

# Schéma d'état
class State(TypedDict):
    json_data: Annotated[Dict[str, Any], "Données du formulaire"]
    context: Annotated[str, "Contexte courant"]
    last_question: Annotated[str, "Dernière question posée"]
    user_input: Annotated[str, "Dernière réponse de l'utilisateur"]
    question_history: Annotated[List[str], "Historique des questions posées"]
    answer_history: Annotated[List[str], "Historique des réponses de l'utilisateur"]

def extract_json_content(text: str) -> str:
    """Extrait le contenu JSON d'un bloc délimité par ```json si présent."""
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    return match.group(1) if match else text

def extract_numeric(text: str) -> float:
    """Extrait la première occurrence numérique dans le texte."""
    match = re.search(r'\d+', text)
    return float(match.group()) if match else 0.0

def normalize_json(response: str) -> str:
    """
    Si la réponse ne commence pas par '{' ou '[', tente de la convertir en JSON
    en découpant par des virgules.
    """
    response = response.strip()
    if response.startswith("{") or response.startswith("["):
        return response
    parts = [c.strip() for c in response.split(",") if c.strip()]
    if len(parts) >= 3:
        required = True if parts[2].lower() in ["true", "oui", "yes"] else False
        return json.dumps({"name": parts[0], "level": parts[1], "required": required})
    return "{}"

# Définition des questions disponibles
QUESTIONS = {
    "waiting_for_title": "Quel est le titre du poste ?",
    "waiting_for_description": "Veuillez fournir une description du poste.",
    "waiting_for_discipline": "Quelle est la discipline (par ex., Fullstack) ?",
    "waiting_for_availability": "Combien de semaines de disponibilité ? (Répondez par un entier)",
    "waiting_for_seniority": "Quel est le niveau de séniorité (JUNIOR, MID, SENIOR) ?",
    "waiting_for_type": "Quel est le type de poste ? (REMOTE, ONSITE, HYBRID)",
    "waiting_for_jobType": "Quel est le type d'emploi ? (FREELANCE, FULLTIME, PARTTIME)",
    "waiting_for_language": ("Veuillez indiquer la langue en précisant le nom, le niveau et "
                             "si elle est requise. Exemple : Anglais, intermédiaire, required"),
    "asking_if_more_languages": "Voulez-vous ajouter une autre exigence linguistique ? (yes/no)",
    "waiting_for_skill": ("Veuillez indiquer la compétence en précisant le nom et si elle est obligatoire. "
                          "Exemple : Python, mandatory"),
    "asking_if_more_skills": "Voulez-vous ajouter une autre compétence ? (yes/no)",
    "waiting_for_countries": "Veuillez lister les pays (séparés par des virgules).",
    "waiting_for_continents": "Veuillez lister les continents (séparés par des virgules).",
    "waiting_for_regions": "Veuillez lister les régions (séparés par des virgules).",
    "waiting_for_timeZone_name": "Quelle est la zone horaire ?",
    "waiting_for_timeZone_overlap": "Combien d'heures de chevauchement sont nécessaires ? (Répondez par un entier)",
    "waiting_for_country": "Dans quel pays se trouve le poste ?",
    "waiting_for_city": "Dans quelle ville se trouve le poste ?",
    "waiting_for_minHourlyRate": "Quel est le taux horaire minimum ? (Répondez par un nombre)",
    "waiting_for_maxHourlyRate": "Quel est le taux horaire maximum ? (Répondez par un nombre)",
    "waiting_for_weeklyHours": "Combien d'heures par semaine ? (Répondez par un entier)",
    "waiting_for_estimatedWeeks": "Combien de semaines estimées pour le projet ? (Répondez par un entier)",
    "waiting_for_minFullTimeSalary": "Quel est le salaire annuel minimum pour un temps plein ? (Répondez par un nombre)",
    "waiting_for_maxFullTimeSalary": "Quel est le salaire annuel maximum pour un temps plein ? (Répondez par un nombre)",
    "waiting_for_minPartTimeSalary": "Quel est le salaire minimum pour un temps partiel ? (Répondez par un nombre)",
    "waiting_for_maxPartTimeSalary": "Quel est le salaire maximum pour un temps partiel ? (Répondez par un nombre)"
}

# Extraire une réponse selon le type de données attendu
class ResponseExtractor:
    def __init__(self, llm):
        self.llm = llm
        self.parse_prompts = {
            "waiting_for_title": PromptTemplate.from_template(
                "Extrait le titre du poste de la réponse suivante : '{response}'. Réponds uniquement par le titre."
            ),
            "waiting_for_description": PromptTemplate.from_template(
                "Extrait la description du poste de la réponse suivante : '{response}'. Réponds uniquement par la description."
            ),
            "waiting_for_discipline": PromptTemplate.from_template(
                "Extrait la discipline de la réponse suivante : '{response}'. Réponds uniquement par la discipline."
            ),
            "waiting_for_availability": PromptTemplate.from_template(
                "Extrait et retourne uniquement un entier indiquant le nombre de semaines de disponibilité de la réponse : '{response}'."
            ),
            "waiting_for_seniority": PromptTemplate.from_template(
                "Extrait le niveau de séniorité (JUNIOR, MID, SENIOR) de la réponse suivante : '{response}'. Réponds uniquement par ce niveau."
            ),
            "waiting_for_type": PromptTemplate.from_template(
                "Extrait le type de poste de la réponse suivante : '{response}'. Réponds uniquement par REMOTE, ONSITE ou HYBRID."
            ),
            "waiting_for_jobType": PromptTemplate.from_template(
                "Extrait le type d'emploi de la réponse suivante : '{response}'. Réponds uniquement par FREELANCE, FULLTIME ou PARTTIME."
            ),
            "waiting_for_language": PromptTemplate.from_template(
                "Extrait les informations sur la langue de la réponse suivante : '{response}'. "
                "Retourne un objet JSON contenant 'name', 'level' et 'required'."
            ),
            "asking_if_more_languages": PromptTemplate.from_template(
                "Détermine si l'utilisateur souhaite ajouter une autre exigence linguistique. Réponds par 'yes' ou 'no'."
            ),
            "waiting_for_skill": PromptTemplate.from_template(
                "Extrait les informations sur la compétence de la réponse suivante : '{response}'. "
                "Retourne un objet JSON contenant 'name' et 'mandatory'."
            ),
            "asking_if_more_skills": PromptTemplate.from_template(
                "Détermine si l'utilisateur souhaite ajouter une autre compétence. Réponds par 'yes' ou 'no'."
            ),
            "waiting_for_timeZone_overlap": PromptTemplate.from_template(
                "Extrait et retourne uniquement un entier indiquant le nombre d'heures de chevauchement de la réponse : '{response}'."
            ),
            "waiting_for_minHourlyRate": PromptTemplate.from_template(
                "Extrait et retourne uniquement un nombre indiquant le taux horaire minimum de la réponse : '{response}'."
            ),
            "waiting_for_maxHourlyRate": PromptTemplate.from_template(
                "Extrait et retourne uniquement un nombre indiquant le taux horaire maximum de la réponse : '{response}'."
            ),
            "waiting_for_weeklyHours": PromptTemplate.from_template(
                "Extrait et retourne uniquement un entier indiquant le nombre d'heures par semaine de la réponse : '{response}'."
            ),
            "waiting_for_estimatedWeeks": PromptTemplate.from_template(
                "Extrait et retourne uniquement un entier indiquant le nombre de semaines estimées de la réponse : '{response}'."
            ),
            "waiting_for_minFullTimeSalary": PromptTemplate.from_template(
                "Extrait et retourne uniquement un nombre indiquant le salaire annuel minimum de la réponse : '{response}'."
            ),
            "waiting_for_maxFullTimeSalary": PromptTemplate.from_template(
                "Extrait et retourne uniquement un nombre indiquant le salaire annuel maximum de la réponse : '{response}'."
            ),
            "waiting_for_minPartTimeSalary": PromptTemplate.from_template(
                "Extrait et retourne uniquement un nombre indiquant le salaire minimum pour un temps partiel de la réponse : '{response}'."
            ),
            "waiting_for_maxPartTimeSalary": PromptTemplate.from_template(
                "Extrait et retourne uniquement un nombre indiquant le salaire maximum pour un temps partiel de la réponse : '{response}'."
            ),
        }
        
    def parse_response(self, context: str, response: str) -> Any:
        if context in self.parse_prompts:
            prompt = self.parse_prompts[context].format(response=response)
            parsed = self.llm.invoke(prompt).content.strip()
            print(f"[DEBUG] Context: {context}, Response: {response}, Parsed: {parsed}")
            
            if context == "waiting_for_type":
                parsed = parsed.strip("'").split()[0].upper()
                if parsed not in ["REMOTE", "ONSITE", "HYBRID"]:
                    parsed = "REMOTE"
                    
            if context in ["waiting_for_language", "waiting_for_skill"]:
                if not parsed.startswith("{"):
                    parsed = normalize_json(parsed)
                    
            return parsed
        return response

# Agent de mise à jour de données intelligent
class SmartUpdateAgent:
    def __init__(self, llm, extractor):
        self.llm = llm
        self.extractor = extractor
        
    def update_json_data(self, state: State) -> State:
        """Met à jour les données JSON en fonction du contexte et de la réponse de l'utilisateur"""
        context = state["context"]
        response = state["user_input"]
        parsed = self.extractor.parse_response(context, response)
        
        try:
            if context == "waiting_for_title":
                state["json_data"].setdefault("jobDetails", {})["title"] = parsed
            elif context == "waiting_for_description":
                state["json_data"]["jobDetails"]["description"] = parsed
            elif context == "waiting_for_discipline":
                state["json_data"]["jobDetails"]["discipline"] = parsed
            elif context == "waiting_for_availability":
                state["json_data"]["jobDetails"]["availability"] = int(extract_numeric(parsed))
            elif context == "waiting_for_seniority":
                state["json_data"]["jobDetails"]["seniority"] = parsed.upper()
            elif context == "waiting_for_type":
                state["json_data"]["jobDetails"]["type"] = parsed
            elif context == "waiting_for_jobType":
                state["json_data"]["jobDetails"]["jobType"] = parsed.upper()
            elif context == "waiting_for_language":
                language = json.loads(parsed)
                state["json_data"]["jobDetails"].setdefault("languages", []).append(language)
            elif context == "waiting_for_skill":
                skill = json.loads(parsed)
                state["json_data"]["jobDetails"].setdefault("skills", []).append(skill)
            elif context in ["waiting_for_countries", "waiting_for_continents", "waiting_for_regions"]:
                extracted = extract_json_content(parsed)
                try:
                    value = json.loads(extracted)
                except json.JSONDecodeError:
                    value = [{"name": c.strip()} for c in parsed.split(",") if c.strip()]
                key = "countries" if context == "waiting_for_countries" else (
                      "continents" if context == "waiting_for_continents" else "regions")
                state["json_data"][key] = value
            elif context == "waiting_for_timeZone_name":
                state["json_data"].setdefault("timeZone", {})["name"] = parsed
            elif context == "waiting_for_timeZone_overlap":
                state["json_data"].setdefault("timeZone", {})["overlap"] = int(extract_numeric(parsed))
            elif context == "waiting_for_country":
                state["json_data"]["country"] = {"name": parsed}
            elif context == "waiting_for_city":
                state["json_data"]["city"] = parsed
            elif context == "waiting_for_minHourlyRate":
                state["json_data"]["minHourlyRate"] = float(extract_numeric(parsed))
            elif context == "waiting_for_maxHourlyRate":
                state["json_data"]["maxHourlyRate"] = float(extract_numeric(parsed))
            elif context == "waiting_for_weeklyHours":
                state["json_data"]["weeklyHours"] = int(extract_numeric(parsed))
            elif context == "waiting_for_estimatedWeeks":
                state["json_data"]["estimatedWeeks"] = int(extract_numeric(parsed))
            elif context == "waiting_for_minFullTimeSalary":
                state["json_data"]["minFullTimeSalary"] = float(extract_numeric(parsed))
            elif context == "waiting_for_maxFullTimeSalary":
                state["json_data"]["maxFullTimeSalary"] = float(extract_numeric(parsed))
            elif context == "waiting_for_minPartTimeSalary":
                state["json_data"]["minPartTimeSalary"] = float(extract_numeric(parsed))
            elif context == "waiting_for_maxPartTimeSalary":
                state["json_data"]["maxPartTimeSalary"] = float(extract_numeric(parsed))
                
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[ERROR] Erreur pour le contexte '{context}': {e}")
            
        state["question_history"].append(QUESTIONS.get(context, ""))
        state["answer_history"].append(response)
        
        return state
        
    def determine_next_question(self, state: State) -> State:
        """Détermine la prochaine question à poser de manière intelligente"""
        
        next_question_prompt = PromptTemplate.from_template("""
Analyse l'état actuel du formulaire d'embauche et détermine la prochaine question à poser logiquement.

Informations actuelles sur le poste:
{json_data}

Questions déjà posées:
{questions_history}

Réponses obtenues:
{answers_history}

Dernière question posée: {last_question}
Dernière réponse: {last_answer}

Champs possibles à remplir:
- waiting_for_title: Titre du poste
- waiting_for_description: Description du poste
- waiting_for_discipline: Discipline (ex: Fullstack)
- waiting_for_availability: Semaines de disponibilité
- waiting_for_seniority: Niveau de séniorité (JUNIOR, MID, SENIOR)
- waiting_for_type: Type de poste (REMOTE, ONSITE, HYBRID)
- waiting_for_jobType: Type d'emploi (FREELANCE, FULLTIME, PARTTIME)
- waiting_for_language: Exigence linguistique
- asking_if_more_languages: Demander s'il y a plus de langues
- waiting_for_skill: Compétence
- asking_if_more_skills: Demander s'il y a plus de compétences
- waiting_for_countries: Pays (pour REMOTE)
- waiting_for_continents: Continents (pour REMOTE)
- waiting_for_regions: Régions (pour REMOTE)
- waiting_for_timeZone_name: Nom de la zone horaire (pour REMOTE)
- waiting_for_timeZone_overlap: Heures de chevauchement (pour REMOTE)
- waiting_for_country: Pays (pour ONSITE/HYBRID)
- waiting_for_city: Ville (pour ONSITE/HYBRID)
- waiting_for_minHourlyRate: Taux horaire minimum (pour FREELANCE)
- waiting_for_maxHourlyRate: Taux horaire maximum (pour FREELANCE)
- waiting_for_weeklyHours: Heures par semaine (pour FREELANCE)
- waiting_for_estimatedWeeks: Semaines estimées (pour FREELANCE)
- waiting_for_minFullTimeSalary: Salaire annuel minimum (pour FULLTIME)
- waiting_for_maxFullTimeSalary: Salaire annuel maximum (pour FULLTIME)
- waiting_for_minPartTimeSalary: Salaire minimum (pour PARTTIME)
- waiting_for_maxPartTimeSalary: Salaire maximum (pour PARTTIME)
- done: Si toutes les informations nécessaires sont recueillies

Basé sur cette analyse, quel est l'identifiant de la prochaine question la plus logique à poser? Retourne UNIQUEMENT l'identifiant sans explication.
""")
        
        questions_history = "\n".join([f"- {q}" for q in state["question_history"] if q])
        answers_history = "\n".join([f"- {a}" for a in state["answer_history"] if a])
        
        context_prompt = next_question_prompt.format(
            json_data=json.dumps(state["json_data"], indent=2, ensure_ascii=False),
            questions_history=questions_history,
            answers_history=answers_history,
            last_question=state["last_question"],
            last_answer=state["user_input"]
        )
        
        next_context = self.llm.invoke(context_prompt).content.strip()
        print(f"[DEBUG] LLM a déterminé le prochain contexte: {next_context}")
        
        if next_context not in QUESTIONS and next_context != "done":
            print(f"[WARN] Contexte invalide '{next_context}', utilisation de la logique par défaut")
            next_context = self.default_next_question(state)
            
        state["context"] = next_context
        return state
    
    def default_next_question(self, state: State) -> str:
        """Logique par défaut pour déterminer la prochaine question (fallback)"""
        jd = state["json_data"].get("jobDetails", {})
        if "title" not in jd:
            return "waiting_for_title"
        elif "description" not in jd:
            return "waiting_for_description"
        elif "discipline" not in jd:
            return "waiting_for_discipline"
        elif "availability" not in jd:
            return "waiting_for_availability"
        elif "seniority" not in jd:
            return "waiting_for_seniority"
        elif "type" not in jd:
            return "waiting_for_type"
        elif "jobType" not in jd:
            return "waiting_for_jobType"
        # Logique conditionnelle basée sur le type de poste
        if jd.get("type") == "REMOTE":
            if "countries" not in state["json_data"]:
                return "waiting_for_countries"
            elif "continents" not in state["json_data"]:
                return "waiting_for_continents"
            elif "regions" not in state["json_data"]:
                return "waiting_for_regions"
            elif "timeZone" not in state["json_data"] or "name" not in state["json_data"]["timeZone"]:
                return "waiting_for_timeZone_name"
            elif "overlap" not in state["json_data"].get("timeZone", {}):
                return "waiting_for_timeZone_overlap"
        elif jd.get("type") in ["ONSITE", "HYBRID"]:
            if "country" not in state["json_data"]:
                return "waiting_for_country"
            elif "city" not in state["json_data"]:
                return "waiting_for_city"
        # Logique pour les types d'emploi
        if jd.get("jobType") == "FREELANCE":
            if "minHourlyRate" not in state["json_data"]:
                return "waiting_for_minHourlyRate"
            elif "maxHourlyRate" not in state["json_data"]:
                return "waiting_for_maxHourlyRate"
            elif "weeklyHours" not in state["json_data"]:
                return "waiting_for_weeklyHours"
            elif "estimatedWeeks" not in state["json_data"]:
                return "waiting_for_estimatedWeeks"
        elif jd.get("jobType") == "FULLTIME":
            if "minFullTimeSalary" not in state["json_data"]:
                return "waiting_for_minFullTimeSalary"
            elif "maxFullTimeSalary" not in state["json_data"]:
                return "waiting_for_maxFullTimeSalary"
        elif jd.get("jobType") == "PARTTIME":
            if "minPartTimeSalary" not in state["json_data"]:
                return "waiting_for_minPartTimeSalary"
            elif "maxPartTimeSalary" not in state["json_data"]:
                return "waiting_for_maxPartTimeSalary"
        # Pour langues et compétences
        if "languages" not in jd:
            return "waiting_for_language"
        elif state["context"] == "waiting_for_language":
            return "asking_if_more_languages"
        elif state["context"] == "asking_if_more_languages" and state["user_input"].lower() == "yes":
            return "waiting_for_language"
        if "skills" not in jd:
            return "waiting_for_skill"
        elif state["context"] == "waiting_for_skill":
            return "asking_if_more_skills"
        elif state["context"] == "asking_if_more_skills" and state["user_input"].lower() == "yes":
            return "waiting_for_skill"
        return "done"
    
    def update_state(self, state: State) -> State:
        """Met à jour les données et détermine la prochaine question"""
        state = self.update_json_data(state)
        state = self.determine_next_question(state)
        return state

# Initialisation des agents
response_extractor = ResponseExtractor(llm)
smart_agent = SmartUpdateAgent(llm, response_extractor)

def question_node(state: State) -> State:
    print(f"[DEBUG] Entering question_node with context: {state['context']}")
    state["last_question"] = QUESTIONS.get(state["context"], "Question inconnue")
    print(state["last_question"])
    state["user_input"] = input("Utilisateur : ")
    return state

def update_node(state: State) -> State:
    print(f"[DEBUG] Entering update_node with context: {state['context']}")
    return smart_agent.update_state(state)

# Configuration du graphe de conversation
graph = StateGraph(state_schema=State)
graph.add_node("question_node", question_node)
graph.add_node("update_node", update_node)

graph.add_edge("question_node", "update_node")
graph.add_conditional_edges(
    "update_node",
    lambda state: state["context"],
    {
        "done": END,
        **{k: "question_node" for k in QUESTIONS.keys()}
    }
)

graph.set_entry_point("question_node")
app = graph.compile()

def main():
    initial_state = {
        "json_data": {"jobDetails": {}},
        "context": "waiting_for_title",
        "last_question": "",
        "user_input": "",
        "question_history": [],
        "answer_history": []
    }
    config = RunnableConfig(recursion_limit=500)
    for output in app.stream(initial_state, config):
        print(f"[DEBUG] Stream output: {output}")
        if "done" in output.get("update_node", {}).get("context", ""):
            break
    print("\nFormulaire complété ! Voici le JSON final :")
    print(json.dumps(initial_state["json_data"], indent=2, ensure_ascii=False))
    
    with open("job_form_data.json", "w", encoding="utf-8") as f:
        json.dump(initial_state["json_data"], f, indent=2, ensure_ascii=False)
    print("Les données ont été sauvegardées dans job_form_data.json")

if __name__ == "__main__":
    main()
