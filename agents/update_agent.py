# agents/update_agent.py - Version améliorée avec fonctions spécifiques par champ et mémoire optimisée

from config.llm_config import llm
import json
import re
from typing import Optional, List, Tuple, Dict, Any, Union
import traceback
import time
import pycountry  # Ajout de l'importation de pycountry

class UpdateAgent:
    """
    Agent pour traiter et valider les réponses utilisateur avec analyse LLM centralisée.
    Détection automatique de la langue par le LLM sans sélection manuelle initiale.
    Version améliorée avec gestion par type de champ et exemples dans les prompts.
    """
    
    def __init__(self, job_details, lang_mem):
        self.job_details = job_details
        self.lang_mem = lang_mem
        self.llm = llm
        
        self.list_fields = {"countries", "continents", "regions", "skills", "languages"}
        self.numeric_fields = {
            "minHourlyRate", "maxHourlyRate", "weeklyHours", "estimatedWeeks",
            "minFullTimeSalary", "maxFullTimeSalary", "minPartTimeSalary", "maxPartTimeSalary",
            "availability"
        }
        self.dict_fields = {"timeZone", "country"}
        self.enum_fields = {
            "jobType": {"FREELANCE", "FULLTIME", "PARTTIME"},
            "type": {"REMOTE", "ONSITE", "HYBRID"},
            "seniority": {"JUNIOR", "MID", "SENIOR"}
        }
        self.text_fields = {"title", "description", "discipline", "city"}
        self.user_language = None
        self.field_update_handlers = {
            "title": self._update_title,
            "description": self._update_description,
            "discipline": self._update_discipline,
            "availability": self._update_availability,
            "languages": self._update_languages,
            "skills": self._update_skills,
            "jobType": self._update_enum_field,
            "type": self._update_enum_field,
            "seniority": self._update_enum_field,
            "country": self._update_dict_field,
            "timeZone": self._update_dict_field,
            "countries": self._update_list_field,
            "continents": self._update_list_field,
            "regions": self._update_list_field,
            "city": self._update_text_field,
            "minHourlyRate": self._update_numeric_field,
            "maxHourlyRate": self._update_numeric_field,
            "weeklyHours": self._update_numeric_field,
            "estimatedWeeks": self._update_numeric_field,
            "minFullTimeSalary": self._update_numeric_field,
            "maxFullTimeSalary": self._update_numeric_field,
            "minPartTimeSalary": self._update_numeric_field,
            "maxPartTimeSalary": self._update_numeric_field
        }

    def detect_language(self, user_input: str) -> str:
        # Code existant inchangé
        if self.user_language:
            return self.user_language
        
        prompt = f"""
        Analysez cette réponse: "{user_input}"
        Déterminez la langue principale utilisée parmi:
        - Français (fr)
        - Anglais (en)
        - Espagnol (es)
        
        Exemples:
        - "Je cherche un développeur" → fr
        - "I need a developer" → en
        - "Necesito un desarrollador" → es
        
        Retournez uniquement le code de langue (fr, en, es).
        """
        try:
            response = self.llm.invoke(prompt)
            lang = response.content.strip().lower()
            if lang in ["fr", "en", "es"]:
                self.user_language = lang
                print(f"✅ Langue détectée: {lang}")
                return lang
            print(f"⚠️ Langue non reconnue: {lang}, par défaut: fr")
            self.user_language = "fr"
            return "fr"
        except Exception as e:
            print(f"⚠️ Erreur lors de la détection de la langue: {e}, par défaut: fr")
            self.user_language = "fr"
            return "fr"

    def detect_intention(self, user_input: str, current_field: str, form_state: Dict) -> Dict[str, Any]:
        # Code existant inchangé
        if not user_input or user_input.strip() == "":
            return {"intention": "EMPTY", "field": current_field, "confidence": 1.0}
            
        filled_fields = {field: value for field, value in form_state.get("jobDetails", {}).items() if value not in [None, [], {}] and not (isinstance(value, dict) and not value.get("name"))}
        all_fields_info = [f"{field} ({'énumération (' + ', '.join(self.enum_fields[field]) + ')' if field in self.enum_fields else 'nombre' if field in self.numeric_fields else 'liste' if field in self.list_fields else 'objet' if field in self.dict_fields else 'texte'})" for field in self.job_details.data["jobDetails"].keys()]
        
        conversation_summary = self.lang_mem.get_summary() if self.lang_mem else "Aucun historique"
        
        prompt = f"""
        Analysez cette réponse d'un **recruteur** remplissant un formulaire d'offre d'emploi:
        "{user_input}"

        Contexte:
        - Champ actuel: '{current_field}'
        - Champs remplis: {json.dumps(filled_fields, ensure_ascii=False)}
        - Champs disponibles: {", ".join(all_fields_info)}
        - Résumé conversationnel: {conversation_summary}

        TÂCHE: Déterminez l'intention principale du recruteur. Intentions possibles:
        1. "DIRECT_ANSWER" - Répond directement à la question posée
        2. "MODIFY_FIELD" - Souhaite modifier un champ spécifique
        3. "SHOW_STATUS" - Demande de voir l'état actuel du formulaire
        4. "CLARIFICATION" - Demande des précisions sur la question
        5. "NO_PREFERENCE" - N'a pas de préférence, accepte valeur par défaut
        6. "REFUSE" - Refuse de répondre à cette question
        7. "EMPTY" - Réponse vide ou non informative
        8. "CONFUSION" - Réponse confuse ou hors sujet

        EXEMPLES:
        - "Je souhaite un développeur Java senior" → {{"intention": "DIRECT_ANSWER", "confidence": 0.9}}
        - "Pour le salaire, mettons 5000€" → {{"intention": "DIRECT_ANSWER", "confidence": 0.95}}
        - "Modifier le poste par Développeur Frontend" → {{"intention": "MODIFY_FIELD", "field_to_modify": "title", "confidence": 0.85}}
        - "Je veux changer la valeur du champ Titre" → {{"intention": "MODIFY_FIELD", "field_to_modify": "title", "confidence": 0.9}}
        - "Où en sommes-nous?" → {{"intention": "SHOW_STATUS", "confidence": 0.9}}
        - "Qu'est-ce que vous entendez par taux horaire?" → {{"intention": "CLARIFICATION", "confidence": 0.85}}
        - "Peu importe, comme vous voulez" → {{"intention": "NO_PREFERENCE", "confidence": 0.8}}
        - "Je préfère ne pas préciser" → {{"intention": "REFUSE", "confidence": 0.9}}
        - "" → {{"intention": "EMPTY", "confidence": 1.0}}
        - "Parlez-moi de votre entreprise" → {{"intention": "CONFUSION", "confidence": 0.7}}
        - "France, Allemagne, Canada" pour 'countries' → {{"intention": "DIRECT_ANSWER", "confidence": 0.95}}
        - "Casablanca pour Maroc et pour les autres pays j’ai pas de problème" pour 'regions' → {{"intention": "DIRECT_ANSWER", "confidence": 0.9}}

        RÈGLES:
        - Si "MODIFY_FIELD", identifiez le champ à modifier (normalisez en minuscules, ex: "Titre" → "title").
        - Si le champ mentionné est ambigu, essayez de le mapper au plus proche dans les champs disponibles.
        - Si la réponse contient une liste de valeurs (ex. pays, compétences) pour le champ actuel '{current_field}', privilégiez "DIRECT_ANSWER".
        - Si l’utilisateur spécifie une valeur pour un pays/région et indique "pas de problème" ou "peu importe" pour les autres, traitez comme "DIRECT_ANSWER".
        - Tolérez les fautes d’orthographe courantes (ex. "Affrique" → "Afrique", "payes" → "pays") et interprétez le sens intended.
        - Ajoutez un log de débogage avec: "DEBUG Intention détectée: <intention>, Champ: <field_to_modify>"

        Retournez UNIQUEMENT un JSON valide: {{"intention": "INTENTION", "field_to_modify": "CHAMP" (si applicable), "confidence": 0.8}}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Aucun JSON valide trouvé")
            result = json.loads(result_text[json_start:json_end])
            
            if "intention" not in result:
                result["intention"] = "DIRECT_ANSWER"
            if "confidence" not in result:
                result["confidence"] = 0.7
                
            if result["intention"] == "MODIFY_FIELD":
                if "field_to_modify" not in result or not result["field_to_modify"]:
                    result["intention"] = "CONFUSION"
                    result["confidence"] = 0.6
                else:
                    # Normaliser le champ en minuscules
                    result["field_to_modify"] = result["field_to_modify"].lower()
                    if result["field_to_modify"] not in self.job_details.data["jobDetails"]:
                        result = self._map_to_existing_field(result, user_input)
            print(f"DEBUG Intention détectée: {result['intention']}, Champ: {result.get('field_to_modify', 'N/A')}")
            return result
            
        except Exception as e:
            print(f"⚠️ Erreur lors de l'analyse d'intention: {e}")
            traceback.print_exc()
            return {"intention": "DIRECT_ANSWER", "field": current_field, "confidence": 0.5}

    def _map_to_existing_field(self, result: Dict, user_input: str) -> Dict:
        # Code existant inchangé
        field_to_map = result.get("field_to_modify", "")
        if "salaire" in field_to_map.lower() or "salary" in field_to_map.lower() or "rémunération" in field_to_map.lower():
            job_type = self.job_details.data["jobDetails"].get("jobType")
            result["field_to_modify"] = {"FREELANCE": "minHourlyRate", "FULLTIME": "minFullTimeSalary", "PARTTIME": "minPartTimeSalary"}.get(job_type, "minFullTimeSalary")
            return result
                
        elif "lieu" in field_to_map.lower() or "location" in field_to_map.lower() or "emplacement" in field_to_map.lower():
            work_type = self.job_details.data["jobDetails"].get("type")
            result["field_to_modify"] = "continents" if work_type == "REMOTE" else "country"
            return result
        
        prompt = f"""
        L'utilisateur (recruteur) souhaite modifier "{field_to_map}" mais ce champ n'existe pas.
        Champs disponibles: {list(self.job_details.data["jobDetails"].keys())}
        Phrase: "{user_input}"
        
        EXEMPLES:
        - "Changer la techno" quand les champs sont ["title", "skills", "languages"] → "skills"
        - "Ajuster le prix" quand les champs sont ["minHourlyRate", "title"] → "minHourlyRate"
        - "Mettre à jour le niveau" quand les champs sont ["seniority", "languages"] → "seniority"
        
        Retournez le nom exact d'un champ existant en minuscules.
        """
        try:
            response = self.llm.invoke(prompt)
            mapped_field = response.content.strip().lower()
            if mapped_field in self.job_details.data["jobDetails"]:
                result["field_to_modify"] = mapped_field
                result["confidence"] = 0.6
                return result
        except Exception:
            pass
        
        result["intention"] = "CONFUSION"
        result["confidence"] = 0.5
        result.pop("field_to_modify", None)
        return result

    def update(self, key: str, user_input: str, original_question: str, question_agent=None) -> Tuple[bool, Optional[str], Optional[Dict]]:
        # Code existant inchangé
        if not user_input or user_input.strip() == "":
            error_messages = {"fr": "Réponse vide", "en": "Empty response", "es": "Respuesta vacía"}
            return False, error_messages.get(self.user_language or "fr", error_messages["fr"]), None
        
        if not self.user_language:
            self.detect_language(user_input)
        
        intention_analysis = self.detect_intention(user_input, key, self.job_details.get_state())
        intention = intention_analysis.get("intention")
        
        if intention == "SHOW_STATUS":
            return False, f"SHOW_STATUS:{key}", intention_analysis
        
        elif intention == "MODIFY_FIELD":
            field_to_modify = intention_analysis.get("field_to_modify")
            if field_to_modify and field_to_modify in self.job_details.data["jobDetails"]:
                current_value = self.job_details.data["jobDetails"].get(field_to_modify, "Non spécifié")
                if "par" in user_input.lower() or "to" in user_input.lower() or "por" in user_input.lower():
                    new_value = user_input.split("par")[-1].strip() if "par" in user_input.lower() else \
                                user_input.split("to")[-1].strip() if "to" in user_input.lower() else \
                                user_input.split("por")[-1].strip()
                    success, update_error = self.job_details.update(field_to_modify, new_value)
                    if success:
                        print(f"✅ Champ '{field_to_modify}' modifié avec succès: {new_value}")
                        return True, None, intention_analysis
                    return False, update_error or f"Erreur lors de la modification de '{field_to_modify}'", intention_analysis
                question_templates = {
                    "fr": f"Remplacer '{current_value}' par quoi pour '{field_to_modify}' ?",
                    "en": f"Replace '{current_value}' with what for '{field_to_modify}'?",
                    "es": f"¿Reemplazar '{current_value}' por qué para '{field_to_modify}'?"
                }
                print(f"DEBUG Demande de modification: {field_to_modify}, Question générée: {question_templates.get(self.user_language or 'fr')}")
                return False, f"CHANGE_FIELD:{field_to_modify}", intention_analysis
            else:
                error_messages = {
                    "fr": "Je n'ai pas compris quel champ vous souhaitez modifier.",
                    "en": "I didn't understand which field you want to modify.",
                    "es": "No entendí qué campo desea modificar."
                }
                print(f"DEBUG Champ non reconnu: {field_to_modify}")
                return False, error_messages.get(self.user_language or "fr"), intention_analysis
        
        elif intention == "CLARIFICATION":
            explanation = self.reformulate_question(key, original_question, None, intention_analysis)
            return False, explanation, intention_analysis
        
        elif intention == "REFUSE":
            message = f"Valeur actuelle conservée pour '{key}'"
            print(f"✅ {message}")
            return True, None, intention_analysis
        
        elif intention == "NO_PREFERENCE":
            default_value = self._suggest_auto_value(key) if hasattr(self, '_suggest_auto_value') else None
            if default_value is not None:
                result = self.job_details.update(key, default_value)
                success = result[0] if isinstance(result, tuple) else result
                update_error = result[1] if isinstance(result, tuple) and not success else None
                if success:
                    print(f"✅ Valeur par défaut appliquée pour '{key}': {default_value}")
                    return True, None, intention_analysis
                return False, update_error or "Erreur lors de l'application de la valeur par défaut", intention_analysis
            return False, "AUTO_VALUE_IMPOSSIBLE", intention_analysis
        
        elif intention == "CONFUSION":
            return False, self.reformulate_question(key, original_question, "Confusion détectée", intention_analysis), intention_analysis
        
        if key in self.field_update_handlers:
            return self.field_update_handlers[key](key, user_input, original_question, intention_analysis)
        
        return self.update_field_value(key, user_input, original_question, intention_analysis)

    def update_field_value(self, key: str, user_input: str, original_question: str, intention_analysis: Dict) -> Tuple[bool, Optional[str], Dict]:
        # Code existant inchangé
        conversation_summary = self.lang_mem.get_summary() if self.lang_mem else "Aucun historique"
        
        prompt_validation = f"""
        Analysez cette réponse d'un **recruteur** pour le champ '{key}' d'une offre d'emploi:
        "{user_input}"
        
        Contexte:
        - Question posée: "{original_question}"
        - Type attendu: {self._get_field_type_description(key)}
        - Champs déjà remplis: {json.dumps(self.job_details.get_state().get("jobDetails", {}), ensure_ascii=False)}
        - Résumé conversationnel: {conversation_summary}
        
        TÂCHE: Validez et normalisez la réponse pour '{key}' selon le format attendu.
        - **Extraire UNIQUEMENT la partie pertinente** liée à '{key}'.
        - Si '{key}' est 'title', extrayez le titre spécifique (ex. "Data Scientist" depuis "Je souhaite publier une offre d'emploi pour un poste de Data Scientist").
        - Si '{key}' est 'discipline' et que la réponse décrit des tâches liées à l'analyse de données (ex. "analyser de grandes quantités de données"), déduisez "Data Science".
        - Ignorer les informations non pertinentes au champ demandé.
        - Si valide, retournez la valeur normalisée au format correct.
        - Si invalide, retournez "INVALID" avec une explication.
        
        EXEMPLES:
        - Pour 'title' avec "Nous recherchons un développeur Java" → {{"value": "Développeur Java"}}
        - Pour 'description' avec "Le candidat devra gérer une équipe" → {{"value": "Gestion d'équipe et coordination des projets."}}
        - Pour 'jobType' avec "C'est un contrat freelance" → {{"value": "FREELANCE"}}
        - Pour 'skills' avec "Java et Python requis" → {{"value": [{{"name": "Java", "mandatory": true}}, {{"name": "Python", "mandatory": true}}]}}
        
        RÈGLES:
        1. Pour 'languages', retournez une liste: [{{"name": "string", "level": "string", "required": boolean}}]
        2. Pour 'skills', retournez une liste: [{{"name": "string", "mandatory": boolean}}]
        3. Pour énumérations ('jobType', 'type', 'seniority'), utilisez: {self.enum_fields.get(key, [])}.
        4. Pour nombres, retournez un float.
        5. Pour objets ('timeZone', 'country'), retournez un dictionnaire.
        6. Retournez TOUJOURS un JSON valide: {{"value": "VALEUR ou INVALID", "error": "EXPLICATION" (si invalide)}}
        """
        try:
            response = self.llm.invoke(prompt_validation)
            result_text = response.content.strip()
            json_start = result_text.find('{"value":')
            if json_start == -1:
                json_start = result_text.find('{ "value":')
            if json_start != -1:
                json_end = result_text.rfind('}') + 1
                result_text = result_text[json_start:json_end]
            result = json.loads(result_text)
            if result["value"] == "INVALID":
                reformulated = self.reformulate_question(key, original_question, result["error"], intention_analysis)
                return False, reformulated, intention_analysis
            cleaned_value = result["value"]
        except json.JSONDecodeError as e:
            print(f"⚠️ Erreur JSON dans la validation de '{key}': {e} - Réponse brute: {response.content}")
            reformulated = self.reformulate_question(key, original_question, f"Erreur de format JSON: {str(e)}. Veuillez préciser {key}.", intention_analysis)
            return False, reformulated, intention_analysis
        except Exception as e:
            print(f"⚠️ Erreur inattendue dans la validation de '{key}': {e}")
            reformulated = self.reformulate_question(key, original_question, f"Erreur de traitement: {str(e)}. Veuillez préciser {key}.", intention_analysis)
            return False, reformulated, intention_analysis

        if key in self.text_fields:
            result = self.job_details.update(key, cleaned_value)
            success = result[0] if isinstance(result, tuple) else result
            update_error = result[1] if isinstance(result, tuple) and not success else None
            if success:
                print(f"✅ Mise à jour réussie: {key} = {cleaned_value}")
                return True, None, intention_analysis
            return False, update_error or f"Erreur lors de la mise à jour de '{key}'", intention_analysis
            
        elif key in self.enum_fields:
            enum_value = str(cleaned_value).upper()
            if enum_value in self.enum_fields[key]:
                result = self.job_details.update(key, enum_value)
                success = result[0] if isinstance(result, tuple) else result
                update_error = result[1] if isinstance(result, tuple) and not success else None
                if success:
                    print(f"✅ Mise à jour réussie: {key} = {enum_value}")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour de '{key}'", intention_analysis
            return False, f"Valeur non reconnue pour {key}. Options: {', '.join(self.enum_fields[key])}", intention_analysis
        
        elif key in self.numeric_fields:
            try:
                value = float(cleaned_value)
                result = self.job_details.update(key, value)
                success = result[0] if isinstance(result, tuple) else result
                update_error = result[1] if isinstance(result, tuple) and not success else None
                if success:
                    print(f"✅ Mise à jour réussie: {key} = {value}")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour de '{key}'", intention_analysis
            except (ValueError, TypeError):
                return False, f"Valeur numérique attendue pour {key}.", intention_analysis
        
        elif key in self.dict_fields:
            if isinstance(cleaned_value, dict) and "name" in cleaned_value:
                result = self.job_details.update(key, cleaned_value)
                success = result[0] if isinstance(result, tuple) else result
                update_error = result[1] if isinstance(result, tuple) and not success else None
                if success:
                    print(f"✅ Mise à jour réussie: {key} = {json.dumps(cleaned_value)}")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour de '{key}'", intention_analysis
            return False, f"Format invalide pour {key}. Exemple: {{'name': 'France'}}", intention_analysis
        
        elif key in self.list_fields:
            if isinstance(cleaned_value, list) and all(isinstance(item, dict) and "name" in item for item in cleaned_value):
                result = self.job_details.update(key, cleaned_value)
                success = result[0] if isinstance(result, tuple) else result
                update_error = result[1] if isinstance(result, tuple) and not success else None
                if success:
                    print(f"✅ Mise à jour réussie: {key} = {json.dumps(cleaned_value)}")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour de '{key}'", intention_analysis
            return False, f"Format invalide pour {key}. Exemple: [{{'name': 'Europe'}}]", intention_analysis
        
        else:
            result = self.job_details.update(key, cleaned_value)
            success = result[0] if isinstance(result, tuple) else result
            update_error = result[1] if isinstance(result, tuple) and not success else None
            if success:
                print(f"✅ Mise à jour réussie: {key} = {cleaned_value}")
                return True, None, intention_analysis
            return False, update_error or f"Erreur lors de la mise à jour de '{key}'", intention_analysis

    def reformulate_question(self, key: str, previous_question: str, error_msg: Optional[str] = None, analysis: Optional[Dict] = None) -> str:
        # Code existant inchangé
        if error_msg and error_msg.startswith("NEED_CLARIFICATION:"):
            return error_msg.replace("NEED_CLARIFICATION:", "")
        
        conversation_summary = self.lang_mem.get_summary() if self.lang_mem else "Aucun historique"
        
        if analysis and analysis.get("intention") == "CLARIFICATION":
            prompt = f"""
            Reformulez cette question pour '{key}' en une version concise et claire:
            Question précédente: "{previous_question}"
            Type: {self._get_field_type_description(key)}
            Résumé conversationnel: {conversation_summary}
            RÈGLES:
            1. Une phrase directe
            2. Incluez 2-3 exemples brefs
            3. Langue: {self.user_language or 'fr'}
            Retournez la question.
            """
            try:
                response = self.llm.invoke(prompt)
                return response.content.strip()
            except Exception as e:
                print(f"⚠️ Erreur lors de la reformulation: {e}")
                return f"Pour '{key}', précisez une valeur (ex. {'Informatique, Data Science' if key == 'discipline' else 'Développeur logiciel, Data Scientist' if key == 'title' else 'description courte, responsabilités'}) ?"
        
        error_context = f"Erreur: {error_msg}" if error_msg else f"Analyse: {json.dumps(analysis, ensure_ascii=False)}" if analysis else "Réponse non claire"
        prompt = f"""
        Reformulez cette question pour '{key}' après une confusion ou erreur:
        Question précédente: "{previous_question}"
        {error_context}
        Type: {self._get_field_type_description(key)}
        Résumé conversationnel: {conversation_summary}
        RÈGLES:
        1. Une phrase concise expliquant l'erreur
        2. Proposez 2-3 choix clairs
        3. Langue: {self.user_language or 'fr'}
        Retournez la question.
        """
        try:
            response = self.llm.invoke(prompt)
            reformulated = response.content.strip()
            return reformulated
        except Exception as e:
            print(f"⚠️ Erreur lors de la reformulation: {e}")
            return f"Votre réponse pour '{key}' n'était pas claire. Choisissez par ex. {'Informatique, Data Science' if key == 'discipline' else 'description courte, tâches précises' if key == 'description' else 'Développeur logiciel, Data Scientist'} ?"

    def _update_text_field(self, key: str, user_input: str, original_question: str, intention_analysis: Dict) -> Tuple[bool, Optional[str], Dict]:
        # Code existant inchangé
        prompt = f"""
        Analysez cette réponse pour le champ textuel '{key}':
        "{user_input}"
        
        Contexte:
        - Question: "{original_question}"
        - Type: Texte simple
        - Autres champs pertinents: {json.dumps({k: v for k, v in self.job_details.data["jobDetails"].items() if k in ['country', 'type', 'jobType'] and v}, ensure_ascii=False)}
        
        TÂCHE: Extraire la valeur textuelle pertinente pour '{key}'.
        
        EXEMPLES POUR '{key}':
        """
        
        if key == "city":
            prompt += """
            - "Le poste est basé à Lyon" → {"value": "Lyon"}
            - "Bureaux à Paris, près de la Défense" → {"value": "Paris"}
            - "Marseille et sa région" → {"value": "Marseille"}
            """
        else:
            prompt += """
            - "La valeur est X" → {"value": "X"}
            - "Nous cherchons dans la région Y" → {"value": "Y"}
            """
        
        prompt += f"""
        Retournez uniquement: {{"value": "VALEUR_EXTRAITE", "error": "EXPLICATION" (si invalide)}}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Aucun JSON valide trouvé")
            result = json.loads(result_text[json_start:json_end])
            
            if "error" in result and result["error"]:
                return False, result["error"], intention_analysis
                
            if "value" in result:
                text_value = result["value"]
                
                update_result = self.job_details.update(key, text_value)
                success = update_result[0] if isinstance(update_result, tuple) else update_result
                update_error = update_result[1] if isinstance(update_result, tuple) and not success else None
                
                if success:
                    print(f"✅ {key} mis à jour: {text_value}")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour de '{key}'", intention_analysis
            
            return False, f"Impossible d'extraire une valeur textuelle pour {key}", intention_analysis
            
        except Exception as e:
            print(f"⚠️ Erreur lors de la mise à jour de '{key}': {e}")
            return False, f"Erreur de traitement: {str(e)}", intention_analysis

    def _update_title(self, key: str, user_input: str, original_question: str, intention_analysis: Dict) -> Tuple[bool, Optional[str], Dict]:
        # Code existant inchangé
        prompt = f"""
        Analysez cette réponse pour le titre d'une offre d'emploi:
        "{user_input}"
        
        Contexte:
        - Question: "{original_question}"
        - Autres champs: {json.dumps(self.job_details.get_state().get("jobDetails", {}), ensure_ascii=False)}
        - Résumé conversationnel: {self.lang_mem.get_summary() if self.lang_mem else "Aucun historique"}
        
        TÂCHE: Extraire uniquement le titre du poste, de manière concise et professionnelle.
        
        EXEMPLES:
        - "Je cherche un développeur pour mon équipe" → "Développeur"
        - "Nous recrutons un Data Scientist confirmé" → "Data Scientist confirmé"
        - "Le poste concerne un chef de projet IT" → "Chef de Projet IT"
        
        Retournez uniquement: {{"value": "TITRE_EXTRAIT", "error": "EXPLICATION" (si invalide)}}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Aucun JSON valide trouvé")
            result = json.loads(result_text[json_start:json_end])
            
            if "error" in result and result["error"]:
                return False, result["error"], intention_analysis
                
            if "value" in result and result["value"]:
                title_value = result["value"]
                update_result = self.job_details.update(key, title_value)
                success = update_result[0] if isinstance(update_result, tuple) else update_result
                update_error = update_result[1] if isinstance(update_result, tuple) and not success else None
                
                if success:
                    print(f"✅ Titre mis à jour: {title_value}")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour du titre", intention_analysis
            
            return False, "Impossible d'extraire un titre valide", intention_analysis
            
        except Exception as e:
            print(f"⚠️ Erreur lors de la mise à jour du titre: {e}")
            return False, f"Erreur de traitement: {str(e)}", intention_analysis

    def _update_description(self, key: str, user_input: str, original_question: str, intention_analysis: Dict) -> Tuple[bool, Optional[str], Dict]:
        # Code existant inchangé
        prompt = f"""
        Analysez cette réponse pour la description d'une offre d'emploi:
        "{user_input}"
        
        Contexte:
        - Question: "{original_question}"
        - Titre du poste: {self.job_details.data["jobDetails"].get("title", "Non spécifié")}
        - Résumé conversationnel: {self.lang_mem.get_summary() if self.lang_mem else "Aucun historique"}
        
        TÂCHE: Extraire ou reformuler la description du poste de manière professionnelle.
        - Conservez un style concis mais informatif
        - Gardez le ton professionnel
        - Vérifiez la cohérence avec le titre du poste
        
        EXEMPLES:
        - "Le poste consiste à développer des applications web" → "Développement d'applications web pour répondre aux besoins des clients."
        - "Analyser les données clients et créer des rapports" → "Analyse des données clients et création de rapports pour soutenir la prise de décision."
        
        Retournez uniquement: {{"value": "DESCRIPTION_FORMATÉE", "error": "EXPLICATION" (si invalide)}}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Aucun JSON valide trouvé")
            result = json.loads(result_text[json_start:json_end])
            
            if "error" in result and result["error"]:
                return False, result["error"], intention_analysis
                
            if "value" in result and result["value"]:
                description_value = result["value"]
                update_result = self.job_details.update(key, description_value)
                success = update_result[0] if isinstance(update_result, tuple) else update_result
                update_error = update_result[1] if isinstance(update_result, tuple) and not success else None
                
                if success:
                    print(f"✅ Description mise à jour: {description_value[:30]}...")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour de la description", intention_analysis
            
            return False, "Impossible d'extraire une description valide", intention_analysis
            
        except Exception as e:
            print(f"⚠️ Erreur lors de la mise à jour de la description: {e}")
            return False, f"Erreur de traitement: {str(e)}", intention_analysis

    def _update_discipline(self, key: str, user_input: str, original_question: str, intention_analysis: Dict) -> Tuple[bool, Optional[str], Dict]:
        # Code existant inchangé
        prompt = f"""
        Analysez cette réponse pour la discipline d'une offre d'emploi:
        "{user_input}"
        
        Contexte:
        - Question: "{original_question}"
        - Titre: {self.job_details.data["jobDetails"].get("title", "Non spécifié")}
        - Description: {self.job_details.data["jobDetails"].get("description", "Non spécifiée")}
        
        TÂCHE: Identifier la discipline principale du poste (ex: Informatique, Finance, Marketing, etc.)
        
        EXEMPLES:
        - "Le poste est dans le développement web avec du JS" → "Informatique"
        - "Nous cherchons quelqu'un pour gérer nos comptes" → "Finance"
        - "Le candidat devra analyser des données" → "Data Science"
        
        Retournez uniquement: {{"value": "DISCIPLINE", "error": "EXPLICATION" (si invalide)}}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Aucun JSON valide trouvé")
            result = json.loads(result_text[json_start:json_end])
            
            if "error" in result and result["error"]:
                return False, result["error"], intention_analysis
                
            if "value" in result and result["value"]:
                discipline_value = result["value"]
                update_result = self.job_details.update(key, discipline_value)
                success = update_result[0] if isinstance(update_result, tuple) else update_result
                update_error = update_result[1] if isinstance(update_result, tuple) and not success else None
                
                if success:
                    print(f"✅ Discipline mise à jour: {discipline_value}")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour de la discipline", intention_analysis
            
            return False, "Impossible d'identifier une discipline valide", intention_analysis
            
        except Exception as e:
            print(f"⚠️ Erreur lors de la mise à jour de la discipline: {e}")
            return False, f"Erreur de traitement: {str(e)}", intention_analysis

    def _update_availability(self, key: str, user_input: str, original_question: str, intention_analysis: Dict) -> Tuple[bool, Optional[str], Dict]:
        # Code existant inchangé
        prompt = f"""
        Analysez cette réponse concernant la disponibilité pour un poste:
        "{user_input}"
        
        Contexte:
        - Question: "{original_question}"
        - Cette valeur représente le délai avant disponibilité, en semaines.
        
        TÂCHE: Convertir en nombre de semaines (valeur numérique).
        
        EXEMPLES:
        - "Immédiatement" → {{"value": 0}}
        - "Dès que possible" → {{"value": 0}}
        - "Dans une semaine" → {{"value": 1}}
        - "2 semaines" → {{"value": 2}}
        - "Un mois" → {{"value": 4}} car un mois contient 4 semaines 
        - "3 mois" → {{"value": 12}} car 3 mois ≈ 12 semaines
        - "2-3 semaines" → {{"value": 2.5}}
        Donc si utilisateur donner nombre de mois, convertir en semaines.
        RÈGLES:
        - "immédiatement", "dès que possible" = 0 semaine
        - 1 jour ≈ 0 semaine (faire une approximation soit majoration soit minoration)
        - 1 mois ≈ 4 semaines
        - Si 45 jours donc on doit convertire a 6 semaine car 45/7 = 6.42 semaine on choisit minoration si nous avons 6.85 semaine on choisit majoration
        - entre 2 semaine et 3 semaine prendre 3 semaine
        
        Retournez uniquement: {{"value": NOMBRE_SEMAINES, "error": "EXPLICATION" (si invalide)}}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Aucun JSON valide trouvé")
            result = json.loads(result_text[json_start:json_end])
            
            if "error" in result and result["error"]:
                return False, result["error"], intention_analysis
                
            if "value" in result:
                availability_value = float(result["value"])
                if availability_value < 0:
                    availability_value = 0.0
                    
                update_result = self.job_details.update(key, availability_value)
                success = update_result[0] if isinstance(update_result, tuple) else update_result
                update_error = update_result[1] if isinstance(update_result, tuple) and not success else None
                
                if success:
                    print(f"✅ Disponibilité mise à jour: {availability_value} semaines")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour de la disponibilité", intention_analysis
            
            return False, "Impossible d'extraire une valeur numérique de disponibilité", intention_analysis
            
        except Exception as e:
            print(f"⚠️ Erreur lors de la mise à jour de la disponibilité: {e}")
            return False, f"Erreur de traitement: {str(e)}", intention_analysis

    def _update_languages(self, key: str, user_input: str, original_question: str, intention_analysis: Dict) -> Tuple[bool, Optional[str], Dict]:
        # Code existant inchangé
        prompt = f"""
        Analysez cette réponse concernant les langues requises pour le poste:
        "{user_input}"
        
        Contexte:
        - Question: "{original_question}"
        - Format attendu: Liste d'objets: [{{"name": "string", "level": "string", "required": boolean}}]
        
        TÂCHE: Extraire les langues mentionnées avec leur niveau et leur caractère obligatoire.
        
        EXEMPLES:
        - "Anglais obligatoire, français apprécié" → 
          [{{"name": "Anglais", "level": "intermediate", "required": true}}, 
           {{"name": "Français", "level": "basic", "required": false}}]
        - "Espagnol courant et allemand basique" → 
          [{{"name": "Espagnol", "level": "fluent", "required": true}}, 
           {{"name": "Allemand", "level": "basic", "required": false}}]
        
        Niveaux possibles: "native", "fluent", "advanced", "intermediate", "basic" ou bien si autre niveaux a vous de choisir le niveux a travers contexte.
        
        Retournez uniquement: {{"value": [LANGUES_FORMATÉES], "error": "EXPLICATION" (si invalide)}}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Aucun JSON valide trouvé")
            result = json.loads(result_text[json_start:json_end])
            
            if "error" in result and result["error"]:
                return False, result["error"], intention_analysis
                
            if "value" in result and isinstance(result["value"], list):
                languages_value = result["value"]
                
                for lang in languages_value:
                    if not isinstance(lang, dict):
                        continue
                    lang.setdefault("level", "intermediate")
                    lang.setdefault("required", True)
                
                update_result = self.job_details.update(key, languages_value)
                success = update_result[0] if isinstance(update_result, tuple) else update_result
                update_error = update_result[1] if isinstance(update_result, tuple) and not success else None
                
                if success:
                    print(f"✅ Langues mises à jour: {', '.join([l.get('name', 'Unknown') for l in languages_value])}")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour des langues", intention_analysis
            
            return False, "Format de langues invalide. Exemple attendu: [{\"name\": \"Anglais\", \"level\": \"intermediate\", \"required\": true}]", intention_analysis
            
        except Exception as e:
            print(f"⚠️ Erreur lors de la mise à jour des langues: {e}")
            return False, f"Erreur de traitement: {str(e)}", intention_analysis

    def _update_enum_field(self, key: str, user_input: str, original_question: str, intention_analysis: Dict) -> Tuple[bool, Optional[str], Dict]:
        # Code existant inchangé
        valid_values = self.enum_fields.get(key, set())
        
        prompt = f"""
        Analysez cette réponse pour le champ '{key}' de type énumération:
        "{user_input}"
        
        Contexte:
        - Question: "{original_question}"
        - Valeurs autorisées: {', '.join(valid_values)}
        - Type: Énumération (choix parmi valeurs prédéfinies)
        
        TÂCHE: Identifier la valeur appropriée parmi les choix disponibles.
        
        EXEMPLES POUR '{key}':
        """
        
        if key == "jobType":
            prompt += """
            - "Je cherche un freelance" → {"value": "FREELANCE"}
            - "C'est pour un CDI" → {"value": "FULLTIME"}
            - "À temps partiel" → {"value": "PARTTIME"}
            """
        elif key == "type":
            prompt += """
            - "Le travail sera à distance" → {"value": "REMOTE"}
            - "Présence au bureau requise" → {"value": "ONSITE"}
            - "Possibilité de faire du télétravail parfois" → {"value": "HYBRID"}
            """
        elif key == "seniority":
            prompt += """
            - "Débutant accepté" → {"value": "JUNIOR"}
            - "Quelques années d'expérience" → {"value": "MID"}
            - "Expert avec solide expérience" → {"value": "SENIOR"}
            """
        
        prompt += f"""
        Retournez uniquement: {{"value": "VALEUR_ENUM", "error": "EXPLICATION" (si invalide)}}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Aucun JSON valide trouvé")
            result = json.loads(result_text[json_start:json_end])
            
            if "error" in result and result["error"]:
                return False, result["error"], intention_analysis
                
            if "value" in result:
                enum_value = str(result["value"]).upper()
                
                if enum_value not in valid_values:
                    return False, f"Valeur non reconnue pour {key}. Options: {', '.join(valid_values)}", intention_analysis
                
                update_result = self.job_details.update(key, enum_value)
                success = update_result[0] if isinstance(update_result, tuple) else update_result
                update_error = update_result[1] if isinstance(update_result, tuple) and not success else None
                
                if success:
                    print(f"✅ {key} mis à jour: {enum_value}")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour de '{key}'", intention_analysis
            
            return False, f"Impossible d'identifier une valeur valide pour {key}", intention_analysis
            
        except Exception as e:
            print(f"⚠️ Erreur lors de la mise à jour de '{key}': {e}")
            return False, f"Erreur de traitement: {str(e)}", intention_analysis

    def _update_numeric_field(self, key: str, user_input: str, original_question: str, intention_analysis: Dict) -> Tuple[bool, Optional[str], Dict]:
        # Code existant inchangé
        prompt = f"""
        Analysez cette réponse pour le champ numérique '{key}':
        "{user_input}"
        
        Contexte:
        - Question: "{original_question}"
        - Type: Valeur numérique (nombre)
        - Autres champs pertinents: {json.dumps({k: v for k, v in self.job_details.data["jobDetails"].items() if k.startswith('min') or k.startswith('max')}, ensure_ascii=False)}
        
        TÂCHE: Extraire la valeur numérique pertinente.
        
        EXEMPLES POUR '{key}':
        """
        
        if "Salary" in key:
            prompt += """
            - "Environ 45000 euros par an" → {"value": 45000}
            - "Entre 50K et 60K" → {"value": 50000} pour minSalary ou {"value": 60000} pour maxSalary
            - "5000 euros mensuels brut" → {"value": 60000} (annualisé)
            """
        elif "HourlyRate" in key:
            prompt += """
            - "400 euros par jour" → {"value": 50} (pour un jour de 8h)
            - "70 euros de l'heure" → {"value": 70}
            - "Entre 60 et 80 euros" → {"value": 60} pour minHourlyRate ou {"value": 80} pour maxHourlyRate
            """
        elif key == "weeklyHours":
            prompt += """
            - "40h par semaine" → {"value": 40}
            - "Mi-temps, 20h" → {"value": 20}
            - "Temps plein" → {"value": 35} (standard)
            """
        elif key == "estimatedWeeks":
            prompt += """
            - "Projet de 3 mois" → {"value": 13}
            - "6 semaines" → {"value": 6}
            - "Jusqu'à la fin de l'année" → {"value": estimation du nombre de semaines restantes}
            """
        
        prompt += f"""
        Retournez uniquement: {{"value": VALEUR_NUMÉRIQUE, "error": "EXPLICATION" (si invalide)}}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Aucun JSON valide trouvé")
            result = json.loads(result_text[json_start:json_end])
            
            if "error" in result and result["error"]:
                return False, result["error"], intention_analysis
                
            if "value" in result:
                try:
                    numeric_value = float(result["value"])
                    
                    update_result = self.job_details.update(key, numeric_value)
                    success = update_result[0] if isinstance(update_result, tuple) else update_result
                    update_error = update_result[1] if isinstance(update_result, tuple) and not success else None
                    
                    if success:
                        print(f"✅ {key} mis à jour: {numeric_value}")
                        return True, None, intention_analysis
                    return False, update_error or f"Erreur lors de la mise à jour de '{key}'", intention_analysis
                except (ValueError, TypeError):
                    return False, f"La valeur fournie n'est pas un nombre valide", intention_analysis
            
            return False, f"Impossible d'extraire une valeur numérique pour {key}", intention_analysis
            
        except Exception as e:
            print(f"⚠️ Erreur lors de la mise à jour de '{key}': {e}")
            return False, f"Erreur de traitement: {str(e)}", intention_analysis

    def _update_dict_field(self, key: str, user_input: str, original_question: str, intention_analysis: Dict) -> Tuple[bool, Optional[str], Dict]:
        # Code existant inchangé
        prompt = f"""
        Analysez cette réponse pour le champ '{key}' de type objet:
        "{user_input}"
        
        Contexte:
        - Question: "{original_question}"
        - Type: Objet dictionnaire avec propriété 'name'
        
        TÂCHE: Extraire la valeur et formater en objet JSON.
        
        EXEMPLES POUR '{key}':
        """
        
        if key == "country":
            prompt += """
            - "France" → {"value": {"name": "France"}}
            - "Basé en Allemagne" → {"value": {"name": "Allemagne"}}
            - "Nos bureaux sont en Espagne" → {"value": {"name": "Espagne"}}
            """
        elif key == "timeZone":
            prompt += """
            - "CET, GMT+1" → {"value": {"name": "CET", "overlap": 4}}
            - "Europe/Paris" → {"value": {"name": "Europe/Paris", "overlap": 4}}
            - "EST" → {"value": {"name": "EST", "overlap": 5}}
            """
        
        prompt += f"""
        Format requis pour '{key}': {{"name": "string"{', "overlap": number' if key == "timeZone" else ''}}}
        
        Retournez uniquement: {{"value": OBJET_FORMATÉ, "error": "EXPLICATION" (si invalide)}}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Aucun JSON valide trouvé")
            result = json.loads(result_text[json_start:json_end])
            
            if "error" in result and result["error"]:
                return False, result["error"], intention_analysis
                
            if "value" in result and isinstance(result["value"], dict) and "name" in result["value"]:
                dict_value = result["value"]
                
                if key == "timeZone" and "overlap" not in dict_value:
                    dict_value["overlap"] = 4
                
                update_result = self.job_details.update(key, dict_value)
                success = update_result[0] if isinstance(update_result, tuple) else update_result
                update_error = update_result[1] if isinstance(update_result, tuple) and not success else None
                
                if success:
                    print(f"✅ {key} mis à jour: {dict_value['name']}")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour de '{key}'", intention_analysis
            
            example = {"name": "France"}
            if key == "timeZone":
                example["overlap"] = 4
            return False, f"Format invalide pour {key}. Exemple: {example}", intention_analysis
        except Exception as e:
            print(f"⚠️ Erreur lors de la mise à jour de '{key}': {e}")
            return False, f"Erreur de traitement: {str(e)}", intention_analysis

    def _update_list_field(self, key: str, user_input: str, original_question: str, intention_analysis: Dict) -> Tuple[bool, Optional[str], Dict]:
        """
        Mise à jour spécifique pour les champs de type liste (continents, countries, regions).
        Utilise le LLM pour identifier les entités géographiques et pycountry pour valider.
        """
        prompt = f"""
        Analysez cette réponse pour le champ '{key}' de type liste:
        "{user_input}"
        
        Contexte:
        - Question: "{original_question}"
        - Type: Liste d'objets avec propriété 'name'
        - État actuel du formulaire: {json.dumps(self.job_details.get_state().get("jobDetails", {}), ensure_ascii=False)}
        
        TÂCHE: Identifiez les entités géographiques mentionnées (continents, pays, régions) et retournez-les sous forme de liste formatée.
        - Pour '{key}', extrayez uniquement les valeurs pertinentes au type demandé (continents, pays ou régions).
        - Tolérez les fautes d’orthographe (ex. "Affrique" → "Afrique", "payes" → "pays") et corrigez-les.
        - Si l’utilisateur indique "peu importe" ou "pas de problème" pour certains éléments, incluez une entrée spéciale comme "Toutes".
        
        EXEMPLES POUR '{key}':
        """
        
        if key == "continents":
            prompt += """
            - "Europe et Asie" → {"value": [{"name": "Europe"}, {"name": "Asie"}]}
            - "Limité à l'Europe" → {"value": [{"name": "Europe"}]}
            - "Partout dans le monde" → {"value": [{"name": "Europe"}, {"name": "Asie"}, {"name": "Amérique du Nord"}, {"name": "Amérique du Sud"}, {"name": "Afrique"}, {"name": "Océanie"}]}
            """
        elif key == "countries":
            prompt += """
            - "France, Belgique et Suisse" → {"value": [{"name": "France"}, {"name": "Belgique"}, {"name": "Suisse"}]}
            - "Pays francophones uniquement" → {"value": [{"name": "France"}, {"name": "Belgique"}, {"name": "Suisse"}, {"name": "Canada"}, {"name": "Luxembourg"}]}
            """
        elif key == "regions":
            prompt += """
            - "Île-de-France" → {"value": [{"name": "Île-de-France"}]}
            - "Paris et sa région" → {"value": [{"name": "Île-de-France"}]}
            - "Casablanca pour Maroc et peu importe pour les autres" → {"value": [{"name": "Casablanca-Settat"}, {"name": "Toutes"}]}
            """
        
        prompt += f"""
        Format requis pour '{key}': [{{"name": "string"}}]
        
        RÈGLES SUPPLÉMENTAIRES:
        - Retournez UNIQUEMENT un JSON valide, sans texte supplémentaire avant ou après.
        - Corrigez les fautes d’orthographe dans les valeurs retournées (ex. "Affrique" → "Afrique").
        
        Retournez uniquement: {{"value": LISTE_OBJETS_FORMATÉS, "error": "EXPLICATION" (si invalide)}}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Aucun JSON valide trouvé")
            result = json.loads(result_text[json_start:json_end])
            
            if "error" in result and result["error"]:
                return False, result["error"], intention_analysis
                
            if "value" in result and isinstance(result["value"], list):
                list_value = result["value"]
                
                # Vérifier que chaque élément a un format valide
                if not all(isinstance(item, dict) and "name" in item for item in list_value):
                    return False, f"Format invalide pour {key}. Exemple: [{{'name': 'Europe'}}, {{'name': 'Asie'}}]", intention_analysis
                
                # Validation avec pycountry
                validated_list = []
                errors = []
                
                if key == "countries":
                    continents = [c["name"] for c in self.job_details.data["jobDetails"].get("continents", [])]
                    for item in list_value:
                        name = item["name"]
                        country = pycountry.countries.search_fuzzy(name)[0] if name != "Toutes" else None
                        if country:
                            # Vérifier si le pays appartient à un continent déjà choisi (si continents est rempli)
                            if continents:
                                continent_map = {
                                    "Europe": "EU",
                                    "Asie": "AS",
                                    "Amérique du Nord": "NA",
                                    "Amérique du Sud": "SA",
                                    "Afrique": "AF",
                                    "Océanie": "OC"
                                }
                                country_continent = pycountry.countries.get(alpha_2=country.alpha_2).continent if hasattr(pycountry.countries.get(alpha_2=country.alpha_2), 'continent') else None
                                if country_continent and continent_map.get(continents[0]) != country_continent:
                                    errors.append(f"{name} n'appartient pas aux continents choisis ({', '.join(continents)}).")
                                    continue
                            validated_list.append({"name": country.name})
                        elif name == "Toutes":
                            validated_list.append({"name": "Toutes"})
                        else:
                            errors.append(f"{name} n'est pas un pays valide.")
                
                elif key == "continents":
                    valid_continents = ["Europe", "Asie", "Amérique du Nord", "Amérique du Sud", "Afrique", "Océanie"]
                    for item in list_value:
                        name = item["name"]
                        if name in valid_continents:
                            validated_list.append({"name": name})
                        elif name == "Toutes":
                            validated_list.extend([{"name": c} for c in valid_continents])
                        else:
                            try:
                                # Essayer de corriger avec pycountry si c'est un nom proche
                                country = pycountry.countries.search_fuzzy(name)[0]
                                errors.append(f"{name} semble être un pays, pas un continent. Voulez-vous dire un continent ?")
                            except LookupError:
                                errors.append(f"{name} n'est pas un continent valide.")
                
                elif key == "regions":
                    countries = [c["name"] for c in self.job_details.data["jobDetails"].get("countries", [])]
                    for item in list_value:
                        name = item["name"]
                        if name == "Toutes":
                            if countries:
                                validated_list.append({"name": f"Toutes ({', '.join(countries)})"})
                            else:
                                validated_list.append({"name": "Toutes"})
                        else:
                            # Vérifier si la région appartient à un pays déjà choisi
                            if countries:
                                found = False
                                for country_name in countries:
                                    country = pycountry.countries.search_fuzzy(country_name)[0]
                                    subdivisions = list(pycountry.subdivisions.get(country_code=country.alpha_2))
                                    for subdiv in subdivisions:
                                        if name.lower() in subdiv.name.lower():
                                            validated_list.append({"name": subdiv.name})
                                            found = True
                                            break
                                    if found:
                                        break
                                if not found:
                                    errors.append(f"{name} n'est pas une région valide pour les pays choisis ({', '.join(countries)}).")
                            else:
                                # Si aucun pays n'est spécifié, accepter la région telle quelle
                                validated_list.append({"name": name})
                
                if errors:
                    return False, "Erreurs de validation : " + "; ".join(errors), intention_analysis
                
                # Mise à jour avec la liste validée
                update_result = self.job_details.update(key, validated_list)
                success = update_result[0] if isinstance(update_result, tuple) else update_result
                update_error = update_result[1] if isinstance(update_result, tuple) and not success else None
                
                if success:
                    print(f"✅ {key} mis à jour: {', '.join([item['name'] for item in validated_list])}")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour de '{key}'", intention_analysis
            
            return False, f"Format invalide pour {key}. Exemple: [{{'name': 'Europe'}}, {{'name': 'Asie'}}]", intention_analysis
        
        except Exception as e:
            print(f"⚠️ Erreur lors de la mise à jour de '{key}': {e}")
            return False, f"Erreur de traitement: {str(e)}", intention_analysis

    def _update_skills(self, key: str, user_input: str, original_question: str, intention_analysis: Dict) -> Tuple[bool, Optional[str], Dict]:
        # Code existant inchangé
        prompt = f"""
        Analysez cette réponse concernant les compétences requises pour le poste:
        "{user_input}"
        
        Contexte:
        - Question: "{original_question}"
        - Titre: {self.job_details.data["jobDetails"].get("title", "Non spécifié")}
        - Discipline: {self.job_details.data["jobDetails"].get("discipline", "Non spécifiée")}
        - Format attendu: Liste d'objets: [{{"name": "string", "mandatory": boolean}}]
        
        TÂCHE: Extraire les compétences mentionnées avec leur caractère obligatoire.
        
        EXEMPLES:
        - "Java, Python et idéalement React" → 
          [{{"name": "Java", "mandatory": true}}, 
           {{"name": "Python", "mandatory": true}}, 
           {{"name": "React", "mandatory": false}}]
        - "Expérience en gestion de projet requise" → 
          [{{"name": "Gestion de projet", "mandatory": true}}]
        
        Retournez uniquement: {{"value": [COMPÉTENCES_FORMATÉES], "error": "EXPLICATION" (si invalide)}}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Aucun JSON valide trouvé")
            result = json.loads(result_text[json_start:json_end])
            
            if "error" in result and result["error"]:
                return False, result["error"], intention_analysis
                
            if "value" in result and isinstance(result["value"], list):
                skills_value = result["value"]
                
                for skill in skills_value:
                    if not isinstance(skill, dict):
                        continue
                    skill.setdefault("mandatory", True)
                
                update_result = self.job_details.update(key, skills_value)
                success = update_result[0] if isinstance(update_result, tuple) else update_result
                update_error = update_result[1] if isinstance(update_result, tuple) and not success else None
                
                if success:
                    print(f"✅ Compétences mises à jour: {', '.join([s.get('name', 'Unknown') for s in skills_value])}")
                    return True, None, intention_analysis
                return False, update_error or f"Erreur lors de la mise à jour des compétences", intention_analysis
            
            return False, "Format de compétences invalide. Exemple attendu: [{\"name\": \"Java\", \"mandatory\": true}]", intention_analysis
            
        except Exception as e:
            print(f"⚠️ Erreur lors de la mise à jour des compétences: {e}")
            return False, f"Erreur de traitement: {str(e)}", intention_analysis
    
    def _get_field_type_description(self, key: str) -> str:
        # Code existant inchangé
        if key in self.text_fields:
            return "Texte simple (chaîne de caractères)"
        elif key in self.numeric_fields:
            return "Nombre (valeur numérique)"
        elif key in self.enum_fields:
            return f"Énumération (options: {', '.join(self.enum_fields[key])})"
        elif key in self.list_fields:
            return "Liste d'éléments (ex: [{'name': 'valeur'}])"
        elif key in self.dict_fields:
            return "Objet dictionnaire (ex: {'name': 'valeur'})"
        return "Type inconnu"