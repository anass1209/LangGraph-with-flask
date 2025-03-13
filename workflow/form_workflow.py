# workflow/form_workflow.py - Version avec traduction dynamique via LLM sans suppression de code

from dataclasses import field
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any, Tuple, Union, Literal
import json
import copy
import traceback
import re
from config.llm_config import llm
from models.job_details import JobDetails
from agents.question_agent import QuestionAgent
from agents.update_agent import UpdateAgent  # Version améliorée
from agents.lang_mem import LangMem

class ConversationTurn(BaseModel):
    role: str  # "user" ou "system"
    content: str

class FormState(BaseModel):
    """Schema pour suivre la progression du formulaire et l'historique."""
    current_field: Optional[str] = Field(default=None, description="Champ actuellement traité")
    current_question: Optional[str] = Field(default=None, description="Question actuelle posée à l'utilisateur")
    last_user_input: Optional[str] = Field(default=None, description="Dernière entrée de l'utilisateur")
    conversation_history: List[ConversationTurn] = Field(default_factory=list, description="Historique des échanges")
    error_message: Optional[str] = Field(default=None, description="Message d'erreur ou d'avertissement")
    is_complete: bool = Field(default=False, description="Indique si le formulaire est complet")
    json_output: Optional[Dict[str, Any]] = Field(default=None, description="Résultat JSON final")
    user_analysis: Optional[Dict[str, Any]] = Field(default=None, description="Analyse de l'entrée utilisateur")
    processed_fields: List[str] = Field(default_factory=list, description="Champs déjà traités")
    skip_modification_detection: bool = Field(default=False, description="Flag pour ignorer la détection de modification")
    failed_attempts: Dict[str, int] = Field(default_factory=dict, description="Compteur d'échecs par champ")
    memory_snapshots: List[Dict[str, Any]] = Field(default_factory=list, description="Instantanés de mémoire pour le suivi des modifications")
    iteration_count: int = Field(default=0, description="Compteur d'itérations pour éviter les boucles infinies")
    is_first_interaction: bool = Field(default=True, description="Indique si c'est la première interaction")

class FormWorkflow:
    """
    Classe principale pour gérer le flux de travail de création d'offre d'emploi.
    Utilise LangGraph pour orchestrer les différentes étapes du processus.
    """
    
    def __init__(self):
        """Initialise le workflow du formulaire avec LangGraph et les différents agents."""
        self.job_details = JobDetails()
        self.llm = llm  # Importer directement depuis config.llm_config
        self.lang_mem = LangMem(self.llm)  # Utiliser cette référence pour la mémoire conversationnelle
        self.question_agent = QuestionAgent()
        self.update_agent = UpdateAgent(self.job_details, self.lang_mem)
        
        self.question_agent.llm = self.llm
        self.question_agent.job_details = self.job_details
        
        self.graph = StateGraph(FormState)
        
        self.graph.add_node("wait_for_first_input", self.wait_for_first_input)
        self.graph.add_node("determine_next_action", self.determine_next_action)
        self.graph.add_node("ask_question", self.ask_question)
        self.graph.add_node("process_user_input", self.process_user_input)
        self.graph.add_node("handle_error", self.handle_error)
        self.graph.add_node("show_status", self.show_status)
        self.graph.add_node("finalize_form", self.finalize_form)
        
        self.graph.add_edge("wait_for_first_input", "process_user_input")
        
        self.graph.add_conditional_edges(
            "determine_next_action",
            self.route_next_action,
            {
                "ask_question": "ask_question",
                "finalize": "finalize_form"
            }
        )
        
        self.graph.add_edge("ask_question", "process_user_input")
        
        self.graph.add_conditional_edges(
            "process_user_input",
            self.route_after_input,
            {
                "success": "determine_next_action",
                "error": "handle_error",
                "change_field": "determine_next_action",
                "show_status": "show_status",
                "wait": "wait_for_first_input"
            }
        )
        
        self.graph.add_edge("handle_error", "ask_question")
        self.graph.add_edge("show_status", "ask_question")
        self.graph.add_edge("finalize_form", END)
        
        self.graph.set_entry_point("wait_for_first_input")
        
        import sys
        sys.setrecursionlimit(2000)
        self.executor = self.graph.compile()

    def compile(self):
        """Compile le graphe en fixant explicitement une limite de récursion."""
        return self.graph.compile(recursion_limit=1500)

    def wait_for_first_input(self, state: FormState) -> FormState:
        """Attend le premier message de l'utilisateur et affiche une invite."""
        new_state = copy.deepcopy(state)
        if new_state.is_first_interaction:
            print("\n🤖 Assistant: Envoyez un premier message (ex. Bonjour) pour commencer.")
        return new_state

    def generate_welcome_response(self, user_input: str) -> str:
        """Génère une réponse de bienvenue en fonction de la langue détectée."""
        lang = self.lang_mem._detect_language(user_input)
        self.lang_mem.user_language = lang
        self.update_agent.user_language = lang
        
        prompt = f"""
        L'utilisateur a envoyé ce premier message: "{user_input}"
        Langue détectée: {lang}
        
        TÂCHE: Générez une réponse de bienvenue adaptée à la langue:
        1. Répondez dans la langue détectée ({lang}).
        2. Répétez le salut initial (ex. "Bonjour" → "Bonjour").
        3. Présentez-vous comme un assistant intelligent aidant les recruteurs à créer des offres d'emploi.
        4. Ton amical et professionnel, maximum 2-3 phrases.
        
        EXEMPLES:
        - Input: "Bonjour", Langue: fr → "Bonjour ! Je suis un assistant intelligent qui aide les recruteurs à créer des offres d'emploi."
        - Input: "Hello", Langue: en → "Hello! I’m an intelligent assistant helping recruiters craft job postings."
        - Input: "Hola", Langue: es → "¡Hola! Soy un asistente inteligente que ayuda a los reclutadores a crear ofertas de empleo."
        
        Retournez UNIQUEMENT la réponse, sans JSON ni commentaire.
        """
        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"⚠️ Erreur lors de la génération de la réponse: {e}")
            return "Bonjour ! Je suis un assistant intelligent qui aide les recruteurs à créer des offres d'emploi."

    # Nouvelle méthode pour traduire dynamiquement les messages
    def translate_message(self, message: str, target_lang: str) -> str:
        """Traduit un message en anglais vers la langue cible via LLM si différente de 'en'."""
        if target_lang == "en":
            return message
        prompt = f"""
        Traduisez ce message en {target_lang} :
        "{message}"
        Retournez UNIQUEMENT la traduction, sans commentaire ni JSON.
        """
        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"⚠️ Erreur lors de la traduction en {target_lang}: {e}")
            return message  # Retourner le message original en cas d'erreur

    def process_user_input(self, state: FormState) -> FormState:
        new_state = copy.deepcopy(state)
        
        print(f"DEBUG: Processing input for field: {new_state.current_field}, Input: {new_state.last_user_input}")
        
        if len(new_state.memory_snapshots) < 10:
            new_state.memory_snapshots.append({
                "field": new_state.current_field,
                "job_details": copy.deepcopy(self.job_details.get_state())
            })
        else:
            new_state.memory_snapshots.pop(0)
            new_state.memory_snapshots.append({
                "field": new_state.current_field,
                "job_details": copy.deepcopy(self.job_details.get_state())
            })
        
        current_language = self.update_agent.user_language or "fr"
        prompt_text = {"fr": "👨‍💼 Recruteur: ", "en": "👨‍💼 Recruiter: ", "es": "👨‍💼 Reclutador: "}
        
        user_input = input(prompt_text.get(current_language, prompt_text["fr"]))
        new_state.last_user_input = user_input
        
        new_state.conversation_history.append(ConversationTurn(role="user", content=user_input))
        self.lang_mem.add_interaction("user", user_input)
        
        if new_state.is_first_interaction:
            welcome_response = self.generate_welcome_response(user_input)
            print(f"\n🤖 Assistant: {welcome_response}")
            new_state.conversation_history.append(ConversationTurn(role="system", content=welcome_response))
            self.lang_mem.add_interaction("system", welcome_response)
            new_state.is_first_interaction = False
            
            memory_summary = self.lang_mem.get_summary()
            field, question = self.question_agent.get_next_question(self.job_details, memory_summary)
            if field and question:
                new_state.current_field = field
                new_state.current_question = question
                print(f"\n🤖 Assistant: {question}")
                new_state.conversation_history.append(ConversationTurn(role="system", content=question))
                self.lang_mem.add_interaction("system", question)
            return new_state
        
        if new_state.current_question and "Remplacer" in new_state.current_question and new_state.current_field:
            success, update_error = self.job_details.update(new_state.current_field, user_input)
            if success:
                print(f"✅ Champ '{new_state.current_field}' modifié avec succès: {user_input}")
                if new_state.current_field not in new_state.processed_fields:
                    new_state.processed_fields.append(new_state.current_field)
                    if len(new_state.processed_fields) > 10:
                        new_state.processed_fields.pop(0)
                new_state.failed_attempts[new_state.current_field] = 0
                new_state.current_field = None
                new_state.current_question = None
                new_state.error_message = None
                new_state.skip_modification_detection = False
                return new_state
            else:
                new_state.error_message = update_error or f"Erreur lors de la mise à jour de '{new_state.current_field}'"
                return new_state
        
        success, message, intention_analysis = self.update_agent.update(
            new_state.current_field, user_input, new_state.current_question, self.question_agent
        )
        new_state.user_analysis = intention_analysis
        
        if message and message.startswith("CHANGE_FIELD:"):
            field_to_modify = message.split("CHANGE_FIELD:")[1]
            if field_to_modify in self.job_details.data["jobDetails"]:
                new_state.current_field = field_to_modify
                current_value = self.job_details.data["jobDetails"].get(field_to_modify, "Non spécifié")
                formatted_value = self.format_value_for_display(field_to_modify, current_value)
                modification_prompts = {
                    "fr": f"Remplacer '{formatted_value}' par quoi pour '{field_to_modify}' ?",
                    "en": f"Replace '{formatted_value}' with what for '{field_to_modify}'?",
                    "es": f"¿Reemplazar '{formatted_value}' por qué para '{field_to_modify}'?"
                }
                new_state.current_question = modification_prompts.get(current_language, modification_prompts["fr"])
                new_state.error_message = message
                new_state.skip_modification_detection = True
                print(f"DEBUG Changement de champ vers: {field_to_modify}")
                return new_state
            else:
                default_message = f"Field '{field_to_modify}' not recognized."
                translated_message = self.translate_message(default_message, current_language)
                new_state.error_message = translated_message
                return new_state
        
        if success:
            if new_state.current_field and new_state.current_field not in new_state.processed_fields:
                new_state.processed_fields.append(new_state.current_field)
                if len(new_state.processed_fields) > 10:
                    new_state.processed_fields.pop(0)
            if new_state.current_field:
                new_state.failed_attempts[new_state.current_field] = 0
            new_state.current_field = None
            new_state.current_question = None
            new_state.error_message = None
            new_state.skip_modification_detection = False
            return new_state
        
        if message:
            if message.startswith("SHOW_STATUS:"):
                new_state.error_message = message
                return new_state
            elif intention_analysis is not None and intention_analysis.get("intention") == "MODIFY_FIELD":
                field_to_modify = intention_analysis.get("field_to_modify")
                if field_to_modify and field_to_modify in self.job_details.data["jobDetails"]:
                    current_value = self.job_details.data["jobDetails"].get(field_to_modify, "Non spécifié")
                    formatted_value = self.format_value_for_display(field_to_modify, current_value)
                    modification_prompts = {
                        "fr": f"Quelle nouvelle valeur souhaitez-vous pour '{field_to_modify}' (actuellement: {formatted_value}) ?",
                        "en": f"What new value would you like for '{field_to_modify}' (currently: {formatted_value})?",
                        "es": f"¿Qué nuevo valor desea para '{field_to_modify}' (actualmente: {formatted_value})?"
                    }
                    new_state.current_question = modification_prompts.get(current_language, modification_prompts["fr"])
                    new_state.error_message = None
                    return new_state
                else:
                    default_message = "I didn't understand which field you want to modify."
                    translated_message = self.translate_message(default_message, current_language)
                    new_state.error_message = translated_message
                    return new_state
            elif intention_analysis is None:
                print("⚠️ intention_analysis est None, impossible de déterminer l'intention.")
                default_message = "Unable to determine the user's intention."
                translated_message = self.translate_message(default_message, current_language)
                new_state.error_message = translated_message
                return new_state
        
        if new_state.current_field:
            new_state.failed_attempts[new_state.current_field] = new_state.failed_attempts.get(new_state.current_field, 0) + 1
            max_attempts = 3
            if new_state.failed_attempts.get(new_state.current_field, 0) >= max_attempts:
                pass
            else:
                new_state.error_message = message
        else:
            default_message = "No active field to update."
            translated_message = self.translate_message(default_message, current_language)
            new_state.error_message = translated_message
        
        return new_state

    def finalize_form(self, state: FormState) -> FormState:
        new_state = copy.deepcopy(state)
        
        final_json = self._clean_json_output(self.job_details.get_state())
        new_state.json_output = final_json
        
        current_language = self.update_agent.user_language or "fr"
        default_message = "\n✅ Job posting finalized. Details:"
        translated_message = self.translate_message(default_message, current_language)
        print(translated_message)
        print(json.dumps(new_state.json_output, indent=4, ensure_ascii=False))
        
        return new_state

    def format_value_for_display(self, field: str, value: Any) -> str:
        if value is None:
            current_language = self.update_agent.user_language or "fr"
            if current_language == "fr":
                return "Non spécifié"
            elif current_language == "es":
                return "No especificado"
            else:
                return "Not specified"
        
        if isinstance(value, list) and not value:
            return "[]"
                
        if isinstance(value, dict) and not value:
            return "{}"
        
        if isinstance(value, (int, float)):
            if field == "availability":
                if value == 0:
                    return "Immédiat" if self.update_agent.user_language == "fr" else "Immediate"
                elif value == 1:
                    return "1 semaine" if self.update_agent.user_language == "fr" else "1 week"
                else:
                    if self.update_agent.user_language == "fr":
                        return f"{value} semaines"
                    elif self.update_agent.user_language == "es":
                        return f"{value} semanas"
                    else:
                        return f"{value} weeks"
            elif "Salary" in field:
                current_language = self.update_agent.user_language or "fr"
                if current_language == "fr":
                    return f"{value}€"
                elif current_language == "es":
                    return f"{value}€"
                else:
                    return f"${value}"
            elif "HourlyRate" in field:
                current_language = self.update_agent.user_language or "fr"
                if current_language == "fr":
                    return f"{value}€/h"
                elif current_language == "es":
                    return f"{value}€/h"
                else:
                    return f"${value}/h"
            return str(value)
        
        if isinstance(value, str) and len(value) < 50:
            return value
            
        if isinstance(value, list):
            if all(isinstance(item, str) for item in value):
                return ", ".join(value)
            elif all(isinstance(item, dict) and "name" in item for item in value):
                if field == "languages" and all("level" in item for item in value):
                    return ", ".join([f"{item['name']} ({item['level']})" for item in value])
                elif field == "skills" and all("mandatory" in item for item in value):
                    return ", ".join([f"{item['name']}{' (requis)' if item['mandatory'] else ' (optionnel)'}" for item in value])
                return ", ".join([item["name"] for item in value])
        
        if isinstance(value, dict) and "name" in value:
            if field == "timeZone" and "overlap" in value:
                return f"{value['name']} (chevauchement: {value['overlap']}h)"
            return value["name"]
        
        return str(value)[:50] + ("..." if len(str(value)) > 50 else "")

    def _clean_json_output(self, json_data):
        try:
            cleaned_json = {}
            for key, value in json_data.get("jobDetails", {}).items():
                if value not in [None, [], {}] and not (isinstance(value, dict) and not value.get("name")):
                    cleaned_json[key] = value
            return {"jobDetails": cleaned_json}
        except Exception as e:
            print(f"⚠️ Erreur lors du nettoyage du JSON: {e}")
        return self._manual_clean_json(json_data)

    def _manual_clean_json(self, json_data):
        if isinstance(json_data, dict):
            result = {}
            for key, value in json_data.items():
                cleaned_value = self._manual_clean_json(value)
                if cleaned_value not in [None, {}, []]:
                    result[key] = cleaned_value
            return result
        elif isinstance(json_data, list):
            cleaned_list = [self._manual_clean_json(item) for item in json_data if item is not None]
            return [item for item in cleaned_list if item != {} and item is not None]
        elif isinstance(json_data, str):
            if json_data.startswith('"') and json_data.endswith('"'):
                try:
                    parsed = json.loads(json_data)
                    if isinstance(parsed, (str, int, float, bool)):
                        return parsed
                except:
                    pass
            return json_data
        else:
            return json_data
            
    def start(self):
        current_language = self.update_agent.user_language or "fr"
        default_message = "\n🚀 Starting the job posting creation process...\n"
        translated_message = self.translate_message(default_message, current_language)
        print(translated_message)
        
        initial_state = FormState(
            current_field=None,
            current_question=None,
            conversation_history=[],
            is_complete=False,
            processed_fields=[],
            skip_modification_detection=True,
            failed_attempts={},
            memory_snapshots=[],
            iteration_count=0,
            is_first_interaction=True
        )
        
        try:
            config = {"recursion_limit": 100}
            self.executor.invoke(initial_state, config=config)
        except Exception as e:
            current_language = self.update_agent.user_language or "fr"
            default_message = f"\n❌ An error occurred: {str(e)}"
            translated_message = self.translate_message(default_message, current_language)
            print(translated_message)
            
            try:
                if (self.job_details.data["jobDetails"].get("title") and 
                    self.job_details.data["jobDetails"].get("description")):
                    default_message = "\n🔄 Attempting to finalize despite the error..."
                    translated_message = self.translate_message(default_message, current_language)
                    print(translated_message)
                    
                    final_state = FormState(
                        is_complete=True,
                        json_output=self.job_details.get_state(),
                        failed_attempts={},
                        memory_snapshots=[],
                        iteration_count=0
                    )
                    self.finalize_form(final_state)
                else:
                    default_message = "⚠️ Not enough information to finalize the job posting."
                    translated_message = self.translate_message(default_message, current_language)
                    print(translated_message)
            except Exception as finalize_error:
                default_message = f"⚠️ Finalization failed: {str(finalize_error)}"
                translated_message = self.translate_message(default_message, current_language)
                print(translated_message)
                
            traceback.print_exc()

    def determine_next_action(self, state: FormState) -> FormState:
        new_state = copy.deepcopy(state)
        
        new_state.iteration_count += 1
        print(f"DEBUG: Iteration {new_state.iteration_count}, Current Field: {new_state.current_field}, Is Complete: {new_state.is_complete}")
        
        if new_state.iteration_count >= 100:
            default_message = f"⚠️ Iteration limit ({new_state.iteration_count}) reached. Forcing finalization."
            translated_message = self.translate_message(default_message, self.update_agent.user_language or "fr")
            print(translated_message)
            new_state.is_complete = True
            new_state.json_output = self.job_details.get_state()
            return new_state
        
        new_state.skip_modification_detection = False
        
        if new_state.error_message and new_state.error_message.startswith("CHANGE_FIELD:"):
            field_to_change = new_state.error_message.split(":", 1)[1]
            
            if field_to_change in self.job_details.data["jobDetails"]:
                new_state.current_field = field_to_change
                
                current_value = self.job_details.data["jobDetails"].get(field_to_change)
                formatted_value = self.format_value_for_display(field_to_change, current_value)
                
                prompt = f"""
                Générez une question brève et directe pour modifier une valeur de champ.
                
                Champ: '{field_to_change}'
                Valeur actuelle: "{formatted_value}"
                Langue: {self.update_agent.user_language or 'fr'}
                
                EXEMPLES:
                - Pour 'title' → "Le titre actuel est 'Développeur Java'. Quelle nouvelle valeur souhaitez-vous?"
                - Pour 'skills' → "Les compétences actuelles sont 'Java, Python'. Quelles compétences souhaitez-vous maintenant?"
                - Pour 'jobType' → "Le type de contrat est actuellement 'FULLTIME'. Souhaitez-vous le modifier?"
                
                RÈGLES STRICTES:
                1. Style CONVERSATIONNEL direct et naturel
                2. JAMAIS de formules de politesse comme "Bonjour", "Cordialement", etc.
                3. MAXIMUM 15 mots (hors valeur actuelle)
                4. Montrer clairement la valeur actuelle
                5. Demander quelle nouvelle valeur utiliser
                
                Retournez uniquement la question, sans commentaires.
                """
                
                try:
                    response = self.llm.invoke(prompt)
                    new_state.current_question = response.content.strip()
                except Exception as e:
                    print(f"⚠️ Erreur lors de la génération de la question de modification: {e}")
                    current_language = self.update_agent.user_language or "fr"
                    if current_language == "fr":
                        new_state.current_question = f"Valeur actuelle pour '{field_to_change}': {formatted_value}. Nouvelle valeur?"
                    elif current_language == "es":
                        new_state.current_question = f"Valor actual para '{field_to_change}': {formatted_value}. ¿Nuevo valor?"
                    else:
                        new_state.current_question = f"Current value for '{field_to_change}': {formatted_value}. New value?"
                
                new_state.error_message = None
                new_state.skip_modification_detection = True
                return new_state
        
        missing_fields = self.job_details.get_missing_fields() if hasattr(self.job_details, 'get_missing_fields') else []
        if not missing_fields:
            new_state.is_complete = True
            new_state.json_output = self.job_details.get_state()
            return new_state
        
        priority_order = [
            "title",
            "description", 
            "discipline", 
            "availability", 
            "seniority", 
            "languages", 
            "skills", 
            "jobType", 
            "type"
        ]
        
        try:
            for key in priority_order:
                if key in missing_fields and key not in new_state.processed_fields:
                    question = self.question_agent.generate_question_with_llm(key)
                    new_state.current_field = key
                    new_state.current_question = question
                    return new_state
            
            job_type = self.job_details.data["jobDetails"].get("jobType")
            job_mode = self.job_details.data["jobDetails"].get("type")

            if job_type and job_mode:
                specific_fields = []
                if job_type == "FREELANCE":
                    specific_fields = ["minHourlyRate", "maxHourlyRate", "weeklyHours", "estimatedWeeks"]
                elif job_type == "FULLTIME":
                    specific_fields = ["minFullTimeSalary", "maxFullTimeSalary"]
                elif job_type == "PARTTIME":
                    specific_fields = ["minPartTimeSalary", "maxPartTimeSalary"]

                if job_mode == "REMOTE":
                    geo_hierarchy = ["continents", "countries", "regions", "timeZone"]
                    for key in geo_hierarchy:
                        if key in missing_fields and key not in new_state.processed_fields:
                            question = self.question_agent.generate_question_with_llm(key)
                            new_state.current_field = key
                            new_state.current_question = question
                            return new_state
                            
                elif job_mode in ["ONSITE", "HYBRID"]:
                    directing = ["country", "city"]
                    specific_fields.extend(directing)

                for key in specific_fields:
                    if key in missing_fields and key not in new_state.processed_fields:
                        question = self.question_agent.generate_question_with_llm(key)
                        new_state.current_field = key
                        new_state.current_question = question
                        return new_state
                            
        except Exception as e:
            default_message = f"⚠️ Error determining next question: {e}"
            translated_message = self.translate_message(default_message, self.update_agent.user_language or "fr")
            print(translated_message)
            if missing_fields:
                field = missing_fields[0]
                new_state.current_field = field
                current_language = self.update_agent.user_language or "fr"
                if current_language == "fr":
                    new_state.current_question = f"Précisez {field} pour cette offre d'emploi."
                elif current_language == "es":
                    new_state.current_question = f"Especifique {field} para esta oferta de trabajo."
                else:
                    new_state.current_question = f"Specify {field} for this job posting."
            else:
                new_state.is_complete = True
                new_state.json_output = self.job_details.get_state()
                    
        return new_state

    def route_next_action(self, state: FormState) -> str:
        print(f"DEBUG: Routing - Iteration {state.iteration_count}, Is Complete: {state.is_complete}")
        if state.is_complete or state.iteration_count >= 100:
            return "finalize"
        else:
            return "ask_question"

    def ask_question(self, state: FormState) -> FormState:
        new_state = copy.deepcopy(state)
        
        if not new_state.current_question:
            memory_summary = self.lang_mem.get_summary()
            field, question = self.question_agent.get_next_question(self.job_details, memory_summary)
            if field and question:
                new_state.current_field = field
                new_state.current_question = question
            else:
                current_language = self.update_agent.user_language or "fr"
                if current_language == "fr":
                    new_state.current_question = "Quelle information souhaitez-vous ajouter?"
                elif current_language == "es":
                    new_state.current_question = "¿Qué información desea añadir?"
                else:
                    new_state.current_question = "What information would you like to add?"
                
        print(f"\n🤖 Assistant: {new_state.current_question}")
        
        new_state.conversation_history.append(
            ConversationTurn(role="system", content=new_state.current_question)
        )
        
        self.lang_mem.add_interaction("system", new_state.current_question)
        
        return new_state

    def route_after_input(self, state: FormState) -> str:
        if state.is_first_interaction:
            return "wait"
            
        if state.error_message in ["ERROR_RESET_STATE", "NO_FIELD_SELECTED"]:
            default_message = "🔄 Resetting state to avoid loop"
            translated_message = self.translate_message(default_message, self.update_agent.user_language or "fr")
            print(translated_message)
            return "success"
            
        if state.error_message == "SHOW_STATUS":
            return "show_status"
        elif state.error_message and state.error_message.startswith("SHOW_STATUS:"):
            default_message = "ℹ️ Displaying requested status"
            translated_message = self.translate_message(default_message, self.update_agent.user_language or "fr")
            print(translated_message)
            return "show_status"
        elif state.error_message and state.error_message.startswith("NEED_CLARIFICATION:"):
            return "error"
        elif state.error_message and state.error_message.startswith("CHANGE_FIELD:"):
            return "change_field"
        elif state.error_message:
            current_field = state.current_field
            if current_field and state.failed_attempts.get(current_field, 0) >= 3:
                default_message = f"🔄 Too many errors for '{current_field}', moving to next field"
                translated_message = self.translate_message(default_message, self.update_agent.user_language or "fr")
                print(translated_message)
                return "success"
            return "error"
        else:
            return "success"

    def handle_error(self, state: FormState) -> FormState:
        new_state = copy.deepcopy(state)
        
        field = new_state.current_field
        prev_question = new_state.current_question
        error_msg = new_state.error_message
        analysis = new_state.user_analysis
        
        if error_msg and error_msg.startswith("NEED_CLARIFICATION:"):
            explanation = error_msg.replace("NEED_CLARIFICATION:", "")
            new_state.current_question = explanation
            
            default_message = "ℹ️ Here's an explanation"
            translated_message = self.translate_message(default_message, self.update_agent.user_language or "fr")
            print(translated_message)
        else:
            reformulated = self.update_agent.reformulate_question(
                field, 
                prev_question, 
                error_msg,
                analysis
            )
            new_state.current_question = reformulated
            
            default_message = f"🔄 Reformulating due to: {error_msg}"
            translated_message = self.translate_message(default_message, self.update_agent.user_language or "fr")
            print(translated_message)
        
        return new_state
        
    def show_status(self, state: FormState) -> FormState:
        new_state = copy.deepcopy(state)
        
        filled_fields = {}
        for field, value in self.job_details.data["jobDetails"].items():
            if value not in [None, [], {}] and not (isinstance(value, dict) and not value.get("name")):
                filled_fields[field] = value
        
        previous_field = new_state.current_field
        previous_question = new_state.current_question
        
        if new_state.error_message and new_state.error_message.startswith("SHOW_STATUS:"):
            field_from_request = new_state.error_message.split(":", 1)[1]
            if field_from_request in self.job_details.data["jobDetails"]:
                previous_field = field_from_request
                previous_question = self.question_agent.generate_question_with_llm(field_from_request)
        
        prompt = f"""
        Créez un résumé concis UNIQUEMENT des détails de l'offre d'emploi DÉJÀ FOURNIS:
        
        {json.dumps(filled_fields, ensure_ascii=False, indent=2)}
        
        RÈGLES STRICTES:
        1. Format direct et structuré
        2. Utilisez des puces (•) pour chaque information
        3. Langue: {self.update_agent.user_language or 'fr'}
        4. Ne mentionnez AUCUN champ manquant ou restant à remplir
        5. N'incluez PAS de question à la fin
        6. N'utilisez PAS de formules de politesse
        
        Retournez uniquement le résumé structuré des informations fournies, sans conclusion ni question finale.
        """
        
        try:
            response = self.llm.invoke(prompt)
            status_message = response.content.strip()
        except Exception as e:
            default_message = f"⚠️ Error generating status: {e}"
            translated_message = self.translate_message(default_message, self.update_agent.user_language or "fr")
            print(translated_message)
            
            current_language = self.update_agent.user_language or "fr"
            if current_language == "fr":
                status_message = f"Voici les informations fournies :\n• {', '.join([f'{k}: {self.format_value_for_display(k, v)}' for k, v in filled_fields.items()])}"
            elif current_language == "es":
                status_message = f"Aquí está la información proporcionada:\n• {', '.join([f'{k}: {self.format_value_for_display(k, v)}' for k, v in filled_fields.items()])}"
            else:
                status_message = f"Here is the information provided:\n• {', '.join([f'{k}: {self.format_value_for_display(k, v)}' for k, v in filled_fields.items()])}"
    
        print(f"\n🤖 Assistant: {status_message}")
        
        new_state.conversation_history.append(
            ConversationTurn(role="system", content=status_message)
        )
        self.lang_mem.add_interaction("system", status_message)
        
        if previous_field and previous_question:
            new_state.current_field = previous_field
            new_state.current_question = previous_question
        else:
            current_language = self.update_agent.user_language or "fr"
            if current_language == "fr":
                new_state.current_question = "Souhaitez-vous continuer à remplir le formulaire ?"
            elif current_language == "es":
                new_state.current_question = "¿Desea continuar completando el formulario?"
            else:
                new_state.current_question = "Would you like to continue filling out the form?"
        
        new_state.error_message = None
        
        return new_state

