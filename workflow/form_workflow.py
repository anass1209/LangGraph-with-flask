# workflow/form_workflow.py - Version optimisée avec gestion de mémoire et prompt améliorés

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
        
        # Partager les références nécessaires avec les agents
        self.question_agent.llm = self.llm
        self.question_agent.job_details = self.job_details  # Important - passer la référence
        
        # Configuration du graph avec les nœuds et les transitions
        self.graph = StateGraph(FormState)
        
        self.graph.add_node("determine_next_action", self.determine_next_action)
        self.graph.add_node("ask_question", self.ask_question)
        self.graph.add_node("process_user_input", self.process_user_input)
        self.graph.add_node("handle_error", self.handle_error)
        self.graph.add_node("show_status", self.show_status)
        self.graph.add_node("finalize_form", self.finalize_form)
        
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
                "show_status": "show_status"
            }
        )
        
        self.graph.add_edge("handle_error", "ask_question")
        self.graph.add_edge("show_status", "ask_question")
        self.graph.add_edge("finalize_form", END)
        
        self.graph.set_entry_point("determine_next_action")
        
        import sys
        sys.setrecursionlimit(2000)  # Augmenter la limite globale
        self.executor = self.graph.compile()  # Pas de recursion_limit ici

    def compile(self):
        """Compile le graphe en fixant explicitement une limite de récursion."""
        return self.graph.compile(recursion_limit=1500)

    def process_user_input(self, state: FormState) -> FormState:
        new_state = copy.deepcopy(state)
        
        print(f"DEBUG: Processing input for field: {new_state.current_field}, Input: {new_state.last_user_input}")
        
        # Capturer un instantané de l'état avant modification pour suivi
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
        
        # Vérifier si c'est une réponse à une question de modification
        if new_state.current_question and "Remplacer" in new_state.current_question and new_state.current_field:
            success, update_error = self.job_details.update(new_state.current_field, user_input)
            if success:
                print(f"✅ Champ '{new_state.current_field}' modifié avec succès: {user_input}")
                if new_state.current_field not in new_state.processed_fields:
                    new_state.processed_fields.append(new_state.current_field)
                    if len(new_state.processed_fields) > 10:
                        new_state.processed_fields.pop(0)
                new_state.failed_attempts[new_state.current_field] = 0
                new_state.current_field = None  # Réinitialiser pour avancer
                new_state.current_question = None
                new_state.error_message = None
                new_state.skip_modification_detection = False
                return new_state
            else:
                new_state.error_message = update_error or f"Erreur lors de la mise à jour de '{new_state.current_field}'"
                return new_state
        
        # Détection d'intention classique
        success, message, intention_analysis = self.update_agent.update(
            new_state.current_field, user_input, new_state.current_question, self.question_agent
        )
        new_state.user_analysis = intention_analysis
        
        # Gestion explicite du cas "CHANGE_FIELD:"
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
                unknown_field_messages = {
                    "fr": f"Champ '{field_to_modify}' non reconnu.",
                    "en": f"Field '{field_to_modify}' not recognized.",
                    "es": f"Campo '{field_to_modify}' no reconocido."
                }
                new_state.error_message = unknown_field_messages.get(current_language, unknown_field_messages["fr"])
                return new_state
        
        # Gestion des cas de succès
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
        
        # Gestion des autres cas où la mise à jour échoue
        if message:
            if message.startswith("SHOW_STATUS:"):
                new_state.error_message = message
                return new_state
            elif intention_analysis is not None and intention_analysis.get("intention") == "MODIFY_FIELD":  # Vérification ajoutée
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
                    unknown_field_messages = {
                        "fr": "Je n'ai pas compris quel champ vous souhaitez modifier.",
                        "en": "I didn't understand which field you want to modify.",
                        "es": "No entendí qué campo desea modificar."
                    }
                    new_state.error_message = unknown_field_messages.get(current_language, unknown_field_messages["fr"])
                    return new_state
            elif intention_analysis is None:  # Gestion du cas où intention_analysis est None
                print("⚠️ intention_analysis est None, impossible de déterminer l'intention.")
                new_state.error_message = "Impossible de déterminer l'intention de l'utilisateur."
                return new_state
        
        # Gestion des échecs répétés
        if new_state.current_field:
            new_state.failed_attempts[new_state.current_field] = new_state.failed_attempts.get(new_state.current_field, 0) + 1
            max_attempts = 3
            if new_state.failed_attempts.get(new_state.current_field, 0) >= max_attempts:
                # Logique existante pour valeur par défaut...
                pass
            else:
                new_state.error_message = message
        else:
            no_active_field_messages = {
                "fr": "Aucun champ actif à mettre à jour.",
                "en": "No active field to update.",
                "es": "No hay campo activo para actualizar."
            }
            new_state.error_message = no_active_field_messages.get(current_language, no_active_field_messages["fr"])
        
        return new_state

    def finalize_form(self, state: FormState) -> FormState:
        """
        Finalise le formulaire et affiche le JSON résultant.
        
        Args:
            state: État actuel du formulaire
            
        Returns:
            État final avec le JSON complet
        """
        new_state = copy.deepcopy(state)
        
        final_json = self._clean_json_output(self.job_details.get_state())
        new_state.json_output = final_json
        
        current_language = self.update_agent.user_language or "fr"
        completion_messages = {
            "fr": "\n✅ Offre d'emploi finalisée. Détails :",
            "en": "\n✅ Job posting finalized. Details:",
            "es": "\n✅ Oferta de trabajo finalizada. Detalles:"
        }
            
        print(completion_messages.get(current_language, completion_messages["fr"]))
        print(json.dumps(new_state.json_output, indent=4, ensure_ascii=False))
        
        return new_state

    def format_value_for_display(self, field: str, value: Any) -> str:
        """
        Formate une valeur pour l'affichage de manière claire et concise.
        
        Args:
            field: Nom du champ
            value: Valeur à formater
            
        Returns:
            Valeur formatée pour l'affichage
        """
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
        
        # Pour les longues valeurs textuelles, tronquer avec des points de suspension
        return str(value)[:50] + ("..." if len(str(value)) > 50 else "")

    def _clean_json_output(self, json_data):
        """
        Nettoie et formate le JSON final de façon intelligente.
        
        Args:
            json_data: Données JSON brutes
            
        Returns:
            JSON nettoyé pour l'exportation
        """
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
        """
        Nettoyage manuel du JSON (méthode de secours).
        
        Args:
            json_data: Données JSON à nettoyer
            
        Returns:
            JSON nettoyé manuellement
        """
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
        """
        Démarre le workflow du formulaire avec détection automatique de la langue.
        
        Cette méthode initialise et exécute le workflow complet du formulaire.
        """
        current_language = self.update_agent.user_language or "fr"
        welcome_messages = {
            "fr": "\n🚀 Démarrage du processus de création d'offre d'emploi...\n",
            "en": "\n🚀 Starting the job posting creation process...\n",
            "es": "\n🚀 Iniciando el proceso de creación de oferta de trabajo...\n"
        }
        print(welcome_messages.get(current_language, welcome_messages["fr"]))
        
        # Initialiser l'état avec des valeurs par défaut
        initial_state = FormState(
            current_field=None,
            current_question=None,
            conversation_history=[],
            is_complete=False,
            processed_fields=[],
            skip_modification_detection=True,
            failed_attempts={},
            memory_snapshots=[],
            iteration_count=0
        )
        
        try:
            config = {"recursion_limit": 100}
            self.executor.invoke(initial_state, config=config)
        except Exception as e:
            current_language = self.update_agent.user_language or "fr"
            error_messages = {
                "fr": f"\n❌ Une erreur s'est produite: {str(e)}",
                "en": f"\n❌ An error occurred: {str(e)}",
                "es": f"\n❌ Se produjo un error: {str(e)}"
            }
            print(error_messages.get(current_language, error_messages["fr"]))
            
            try:
                if (self.job_details.data["jobDetails"].get("title") and 
                    self.job_details.data["jobDetails"].get("description")):
                    recovery_messages = {
                        "fr": "\n🔄 Tentative de finalisation malgré l'erreur...",
                        "en": "\n🔄 Attempting to finalize despite the error...",
                        "es": "\n🔄 Intentando finalizar a pesar del error..."
                    }
                    print(recovery_messages.get(current_language, recovery_messages["fr"]))
                    
                    final_state = FormState(
                        is_complete=True,
                        json_output=self.job_details.get_state(),
                        failed_attempts={},
                        memory_snapshots=[],
                        iteration_count=0
                    )
                    self.finalize_form(final_state)
                else:
                    insufficient_messages = {
                        "fr": "⚠️ Pas assez d'informations pour finaliser l'offre d'emploi.",
                        "en": "⚠️ Not enough information to finalize the job posting.",
                        "es": "⚠️ No hay suficiente información para finalizar la oferta de trabajo."
                    }
                    print(insufficient_messages.get(current_language, insufficient_messages["fr"]))
            except Exception as finalize_error:
                finalize_error_messages = {
                    "fr": f"⚠️ Échec de la finalisation: {str(finalize_error)}",
                    "en": f"⚠️ Finalization failed: {str(finalize_error)}",
                    "es": f"⚠️ Error en la finalización: {str(finalize_error)}"
                }
                print(finalize_error_messages.get(current_language, finalize_error_messages["fr"]))
                
            traceback.print_exc()

    def determine_next_action(self, state: FormState) -> FormState:
        """
        Détermine la prochaine action à effectuer dans le workflow.
        Choisit le prochain champ à compléter selon la logique métier.
        
        Args:
            state: État actuel du formulaire
            
        Returns:
            Nouvel état avec le prochain champ à compléter
        """
        new_state = copy.deepcopy(state)
        
        new_state.iteration_count += 1
        print(f"DEBUG: Iteration {new_state.iteration_count}, Current Field: {new_state.current_field}, Is Complete: {new_state.is_complete}")
        
        if new_state.iteration_count >= 100:
            print(f"⚠️ Limite d'itérations ({new_state.iteration_count}) atteinte. Finalisation forcée.")
            new_state.is_complete = True
            new_state.json_output = self.job_details.get_state()
            return new_state
        
        new_state.skip_modification_detection = False
        
        # Traiter les demandes explicites de changement de champ
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
        
        # Vérifier s'il reste des champs à compléter
        missing_fields = self.job_details.get_missing_fields() if hasattr(self.job_details, 'get_missing_fields') else []
        if not missing_fields:
            new_state.is_complete = True
            new_state.json_output = self.job_details.get_state()
            return new_state
        
        # Ordre de priorité pour les champs essentiels
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
            # D'abord traiter les champs prioritaires
            for key in priority_order:
                if key in missing_fields and key not in new_state.processed_fields:
                    question = self.question_agent.generate_question_with_llm(key)
                    new_state.current_field = key
                    new_state.current_question = question
                    return new_state
            
            # Ensuite traiter les champs spécifiques selon le type de contrat et le mode de travail
            job_type = self.job_details.data["jobDetails"].get("jobType")
            job_mode = self.job_details.data["jobDetails"].get("type")

            if job_type and job_mode:
                # Déterminer les champs spécifiques selon le type de contrat
                specific_fields = []
                if job_type == "FREELANCE":
                    specific_fields = ["minHourlyRate", "maxHourlyRate", "weeklyHours", "estimatedWeeks"]
                elif job_type == "FULLTIME":
                    specific_fields = ["minFullTimeSalary", "maxFullTimeSalary"]
                elif job_type == "PARTTIME":
                    specific_fields = ["minPartTimeSalary", "maxPartTimeSalary"]

                # Traiter les champs géographiques selon le mode de travail
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

                # Traiter les champs spécifiques identifiés
                for key in specific_fields:
                    if key in missing_fields and key not in new_state.processed_fields:
                        question = self.question_agent.generate_question_with_llm(key)
                        new_state.current_field = key
                        new_state.current_question = question
                        return new_state
                            
        except Exception as e:
            print(f"⚠️ Erreur lors de la détermination de la prochaine question: {e}")
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
        """
        Détermine la prochaine étape après avoir choisi l'action.
        
        Args:
            state: État actuel du formulaire
            
        Returns:
            Nom de la prochaine action à exécuter
        """
        print(f"DEBUG: Routing - Iteration {state.iteration_count}, Is Complete: {state.is_complete}")
        if state.is_complete or state.iteration_count >= 100:
            return "finalize"
        else:
            return "ask_question"

    def ask_question(self, state: FormState) -> FormState:
        """
        Pose la question à l'utilisateur et enregistre dans l'historique.
        
        Args:
            state: État actuel du formulaire
            
        Returns:
            Nouvel état après avoir posé la question
        """
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
        """
        Détermine la prochaine étape après avoir traité l'entrée utilisateur.
        
        Args:
            state: État actuel du formulaire
            
        Returns:
            Nom de la prochaine action à exécuter
        """
        if state.error_message in ["ERROR_RESET_STATE", "NO_FIELD_SELECTED"]:
            print("🔄 Réinitialisation de l'état pour éviter une boucle")
            return "success"
            
        if state.error_message == "SHOW_STATUS":
            return "show_status"
        elif state.error_message and state.error_message.startswith("SHOW_STATUS:"):
            print(f"ℹ️ Affichage de l'état demandé")
            return "show_status"
        elif state.error_message and state.error_message.startswith("NEED_CLARIFICATION:"):
            return "error"
        elif state.error_message and state.error_message.startswith("CHANGE_FIELD:"):
            return "change_field"
        elif state.error_message:
            current_field = state.current_field
            if current_field and state.failed_attempts.get(current_field, 0) >= 3:
                current_language = self.update_agent.user_language or "fr"
                too_many_errors_messages = {
                    "fr": f"🔄 Trop d'erreurs pour '{current_field}', passage au champ suivant",
                    "en": f"🔄 Too many errors for '{current_field}', moving to next field",
                    "es": f"🔄 Demasiados errores para '{current_field}', pasando al siguiente campo"
                }
                print(too_many_errors_messages.get(current_language, too_many_errors_messages["fr"]))
                return "success"
            return "error"
        else:
            return "success"

    def handle_error(self, state: FormState) -> FormState:
        """
        Gère les erreurs et reformule la question avec analyse contextuelle.
        
        Args:
            state: État actuel du formulaire
            
        Returns:
            Nouvel état avec question reformulée
        """
        new_state = copy.deepcopy(state)
        
        field = new_state.current_field
        prev_question = new_state.current_question
        error_msg = new_state.error_message
        analysis = new_state.user_analysis
        
        if error_msg and error_msg.startswith("NEED_CLARIFICATION:"):
            explanation = error_msg.replace("NEED_CLARIFICATION:", "")
            new_state.current_question = explanation
            
            current_language = self.update_agent.user_language or "fr"
            clarification_messages = {
                "fr": "ℹ️ Voici une explication",
                "en": "ℹ️ Here's an explanation",
                "es": "ℹ️ Aquí hay una explicación"
            }
            print(clarification_messages.get(current_language, clarification_messages["fr"]))
        else:
            # Utiliser l'agent de mise à jour pour reformuler intelligemment la question
            reformulated = self.update_agent.reformulate_question(
                field, 
                prev_question, 
                error_msg,
                analysis
            )
            new_state.current_question = reformulated
            
            current_language = self.update_agent.user_language or "fr"
            debug_messages = {
                "fr": f"🔄 Reformulation suite à: {error_msg}",
                "en": f"🔄 Reformulating due to: {error_msg}",
                "es": f"🔄 Reformulando debido a: {error_msg}"
            }
            print(debug_messages.get(current_language, debug_messages["fr"]))
        
        return new_state
        
    def show_status(self, state: FormState) -> FormState:
        """
        Affiche uniquement les champs remplis du formulaire et revient à la question précédente.
        
        Args:
            state: État actuel du formulaire
            
        Returns:
            Nouvel état avec résumé du statut actuel
        """
        new_state = copy.deepcopy(state)
        
        # Ne récupérer que les champs qui sont remplis
        filled_fields = {}
        for field, value in self.job_details.data["jobDetails"].items():
            if value not in [None, [], {}] and not (isinstance(value, dict) and not value.get("name")):
                filled_fields[field] = value
        
        # Conserver la question précédente pour y revenir après l'affichage
        previous_field = new_state.current_field
        previous_question = new_state.current_question
        
        if new_state.error_message and new_state.error_message.startswith("SHOW_STATUS:"):
            # Extraire le champ de la demande SHOW_STATUS:field
            field_from_request = new_state.error_message.split(":", 1)[1]
            if field_from_request in self.job_details.data["jobDetails"]:
                previous_field = field_from_request
                # Générer une question pour ce champ spécifique
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
            print(f"⚠️ Erreur lors de la génération du statut: {e}")
            
            current_language = self.update_agent.user_language or "fr"
            
            if current_language == "fr":
                status_message = f"Voici les informations fournies :\n• {', '.join([f'{k}: {self.format_value_for_display(k, v)}' for k, v in filled_fields.items()])}"
            elif current_language == "es":
                status_message = f"Aquí está la información proporcionada:\n• {', '.join([f'{k}: {self.format_value_for_display(k, v)}' for k, v in filled_fields.items()])}"
            else:
                status_message = f"Here is the information provided:\n• {', '.join([f'{k}: {self.format_value_for_display(k, v)}' for k, v in filled_fields.items()])}"
    
        # Afficher le résumé
        print(f"\n🤖 Assistant: {status_message}")
        
        # Ajouter le résumé à l'historique
        new_state.conversation_history.append(
            ConversationTurn(role="system", content=status_message)
        )
        self.lang_mem.add_interaction("system", status_message)
        
        # Revenir à la question précédente
        if previous_field and previous_question:
            new_state.current_field = previous_field
            new_state.current_question = previous_question
        else:
            # Fallback si nous n'avons pas de question précédente
            current_language = self.update_agent.user_language or "fr"
            if current_language == "fr":
                new_state.current_question = "Souhaitez-vous continuer à remplir le formulaire ?"
            elif current_language == "es":
                new_state.current_question = "¿Desea continuar completando el formulario?"
            else:
                new_state.current_question = "Would you like to continue filling out the form?"
        
        new_state.error_message = None
        
        return new_state