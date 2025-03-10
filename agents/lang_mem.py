# agents/lang_mem.py - Version optimisée pour gestion du contexte et multilinguisme

from config.llm_config import llm, memory
from typing import List, Dict, Any, Optional, Tuple
import json
import re
import traceback

class LangMem:
    """Classe pour la gestion de la mémoire des conversations avec capacités multilinguisme avancées."""
    
    def __init__(self, llm):
        self.llm = llm
        self.short_term_memory = []  # Derniers échanges
        self.long_term_memory = {}   # Faits importants stockés par catégorie
        self.contradictions = []     # Liste des contradictions détectées
        self.langchain_memory = memory  # Utilisation de la mémoire LangChain
        self.user_language = "fr"    # Langue par défaut, sera mise à jour
        
    def add_interaction(self, role: str, content: str):
        """Ajoute une interaction à la mémoire à court terme avec traitement amélioré."""
        self.short_term_memory.append({"role": role, "content": content})
        
        # Ajouter à la mémoire LangChain
        try:
            if role == "user":
                self.langchain_memory.save_context({"input": content}, {"output": ""})
                # Met à jour la mémoire à long terme pour les réponses utilisateur
                self._extract_facts(content)
                # Détecte la langue si ce n'est pas déjà fait
                if len(self.short_term_memory) <= 3:  # Seulement pour les premières interactions
                    detected_language = self._detect_language(content)
                    if detected_language:
                        self.user_language = detected_language
            elif role == "system":
                # Pour les messages système, on les traite comme des réponses
                last_user_input = ""
                if self.short_term_memory and len(self.short_term_memory) > 1:
                    for item in reversed(self.short_term_memory[:-1]):
                        if item["role"] == "user":
                            last_user_input = item["content"]
                            break
                
                if last_user_input:
                    self.langchain_memory.save_context({"input": last_user_input}, {"output": content})
        except Exception as e:
            print(f"⚠️ Erreur lors de l'ajout à la mémoire: {e}")
            traceback.print_exc()
        
        # Limite la taille de la mémoire à court terme
        if len(self.short_term_memory) > 35:
            self.short_term_memory.pop(0)

    def _detect_language(self, text: str) -> str:
        """Détecte n'importe quelle langue utilisée dans le texte en utilisant directement le LLM."""
        if not text.strip():
            return "fr"  # Retourne français par défaut si le texte est vide
        
        try:
            prompt = f"""
            Détectez la langue de ce texte:
            "{text}"
            
            IMPORTANT: 
            - Répondez uniquement par le code ISO 639-1 de la langue (ex: "fr" pour français, "en" pour anglais, etc.)
            - Ne donnez aucune explication, uniquement le code de langue en minuscules.
            - Si vous n'êtes pas sûr, retournez le code qui vous semble le plus probable.
            """
            
            response = self.llm.invoke(prompt)
            result = response.content.strip().lower()
            
            # Vérifier si le résultat ressemble à un code ISO de langue (généralement 2 caractères)
            if re.match(r'^[a-z]{2,3}$', result):
                return result
            else:
                print(f"⚠️ Résultat de détection de langue non reconnu: {result}")
                return "fr"  # Retourne français par défaut en cas de résultat non conforme
                
        except Exception as e:
            print(f"⚠️ Erreur lors de la détection de langue par LLM: {e}")
            return "fr"  # Retourne français par défaut en cas d'erreur

    def _extract_facts(self, content: str):
        """Extrait les faits importants du contenu pour la mémoire à long terme."""
        if not content.strip():
            return
            
        # Prompt optimisé pour l'extraction d'informations clés
        prompt = f"""
        Analysez cette réponse utilisateur concernant une offre d'emploi:
        "{content}"
        
        TÂCHE: Extrayez UNIQUEMENT les informations factuelles clés selon ces catégories:
        - position: titre ou type de poste
        - skills: compétences mentionnées
        - salary: informations sur la rémunération
        - location: lieu de travail
        - contract: type de contrat
        - timing: disponibilité ou délais mentionnés
        
        IMPORTANT:
        1. Extrayez UNIQUEMENT les informations EXPLICITEMENT mentionnées
        2. NE FAITES PAS d'interprétation ou d'inférence
        3. Si aucune information n'est fournie pour une catégorie, omettez-la complètement
        4. Préservez les valeurs exactes (ne normalisez pas)
        
        Retournez un JSON UNIQUEMENT avec les catégories qui contiennent des informations.
        """
        
        try:
            response = self.llm.invoke(prompt)
            # Extraire le JSON de la réponse
            result_text = response.content.strip()
            
            # Nettoyage du résultat pour extraire uniquement le JSON
            if not result_text.startswith("{"):
                result_text = result_text[result_text.find("{"):]
            if not result_text.endswith("}"):
                result_text = result_text[:result_text.rfind("}")+1]
                
            # Parser le JSON
            try:
                facts = json.loads(result_text)
                
                # Mettre à jour la mémoire à long terme avec les nouvelles informations
                for category, value in facts.items():
                    if value and value != "None" and not (isinstance(value, dict) and len(value) == 0):
                        self.long_term_memory[category] = value
            except json.JSONDecodeError:
                print(f"⚠️ Réponse non-JSON pour l'extraction de faits: {result_text[:100]}...")
        except Exception as e:
            print(f"⚠️ Erreur lors de l'extraction des faits: {e}")

    def check_contradiction(self, key: str, value: Any, job_details: Dict) -> Tuple[bool, Optional[str]]:
        """Vérifie les contradictions entre la nouvelle valeur et les données existantes."""
        if not key or value is None:
            return False, None
                
        details = job_details.get("jobDetails", {})
        
        # Vérifications numériques directes sans LLM
        if key == "minHourlyRate" and details.get("maxHourlyRate") is not None:
            if float(value) > float(details["maxHourlyRate"]):
                if self.user_language == "fr":
                    return True, f"Le taux horaire minimum ({value}) est supérieur au maximum ({details['maxHourlyRate']})"
                elif self.user_language == "es":
                    return True, f"La tarifa horaria mínima ({value}) es superior a la máxima ({details['maxHourlyRate']})"
                else:
                    return True, f"The minimum hourly rate ({value}) is higher than the maximum ({details['maxHourlyRate']})"
                
        if key == "maxHourlyRate" and details.get("minHourlyRate") is not None:
            if float(value) < float(details["minHourlyRate"]):
                if self.user_language == "fr":
                    return True, f"Le taux horaire maximum ({value}) est inférieur au minimum ({details['minHourlyRate']})"
                elif self.user_language == "es":
                    return True, f"La tarifa horaria máxima ({value}) es inferior a la mínima ({details['minHourlyRate']})"
                else:
                    return True, f"The maximum hourly rate ({value}) is lower than the minimum ({details['minHourlyRate']})"
        
        if key == "weeklyHours" and float(value) > 168:
            if self.user_language == "fr":
                return True, f"Les heures hebdomadaires ({value}) dépassent le maximum possible (168)"
            elif self.user_language == "es":
                return True, f"Las horas semanales ({value}) superan el máximo posible (168)"
            else:
                return True, f"Weekly hours ({value}) exceed the maximum possible (168)"
        
        # Vérification de cohérence géographique pour les cas complexes
        if key in ["countries", "continents", "regions", "country", "city"]:
            prompt = f"""
            Vérifiez si cette nouvelle valeur contredit les informations existantes:
            
            Nouveau champ: '{key}'
            Nouvelle valeur: {json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)}
            
            Informations existantes:
            {json.dumps(details, ensure_ascii=False, indent=2)}
            
            TÂCHE: Vérifiez UNIQUEMENT les contradictions géographiques évidentes.
            Exemples de contradictions:
            - Un pays qui n'est pas dans les continents spécifiés
            - Une ville qui n'est pas dans le pays indiqué
            - Une région incompatible avec le pays mentionné
            
            Répondez par ce JSON:
            {{
                "contradiction": true/false,
                "message": "explication claire" (seulement si contradiction=true)
            }}
            """
            
            try:
                response = self.llm.invoke(prompt)
                result_text = response.content.strip()
                
                # Nettoyage du résultat
                if not result_text.startswith("{"):
                    result_text = result_text[result_text.find("{"):]
                if not result_text.endswith("}"):
                    result_text = result_text[:result_text.rfind("}")+1]
                    
                result = json.loads(result_text)
                
                if result.get("contradiction", False):
                    message = result.get("message", f"Contradiction géographique détectée avec {key}")
                    # Mémoriser la contradiction
                    self.contradictions.append({
                        "field": key,
                        "value": value,
                        "message": message
                    })
                    return True, message
            except Exception as e:
                print(f"⚠️ Erreur lors de la vérification de contradiction: {e}")
        
        return False, None

    def get_summary(self) -> str:
        """Génère un résumé contextuel des interactions passées dans la langue de l'utilisateur."""
        if not self.short_term_memory:
            # Message minimal selon la langue
            if self.user_language == "fr":
                return "Début de la conversation."
            elif self.user_language == "es":
                return "Inicio de la conversación."
            else:
                return "Start of conversation."
            
        # Utiliser la mémoire LangChain pour le résumé si disponible
        try:
            memory_messages = self.langchain_memory.load_memory_variables({})
            if memory_messages and "history" in memory_messages and memory_messages["history"]:
                history_summary = str(memory_messages["history"])
                
                # Améliorer le résumé avec un prompt concis et focalisé
                prompt = f"""
                Basé sur cette conversation:
                {history_summary}
                
                Créez un résumé BREF qui se concentre sur:
                1. Les principales INFORMATIONS DE L'OFFRE D'EMPLOI déjà fournies
                2. Les PRÉFÉRENCES exprimées par le recruteur
                3. Les POINTS AMBIGUS ou CONTRADICTIONS éventuelles
                
                RÈGLES:
                - Maximum 5 phrases
                - Style direct et factuel
                - Langue: {self.user_language}
                - AUCUNE introduction ou conclusion
                """
                
                try:
                    response = self.llm.invoke(prompt)
                    return response.content.strip()
                except Exception as e:
                    print(f"⚠️ Erreur lors de la création du résumé: {e}")
                    # Fallback - utiliser le résumé de base
                    return history_summary
            
            # Fallback avec mémoire à court terme si la mémoire LangChain échoue
            # Utiliser seulement les 5 derniers tours pour limiter la taille
            history_text = "\n".join([f"{turn['role']}: {turn['content']}" for turn in self.short_term_memory[-5:]])
            
            # Résumé simple des faits mémorisés
            facts_summary = ""
            if self.long_term_memory:
                if self.user_language == "fr":
                    facts_summary = "Informations mémorisées: " + ", ".join([f"{k}: {v}" for k, v in self.long_term_memory.items()])
                elif self.user_language == "es":
                    facts_summary = "Información memorizada: " + ", ".join([f"{k}: {v}" for k, v in self.long_term_memory.items()])
                else:
                    facts_summary = "Memorized information: " + ", ".join([f"{k}: {v}" for k, v in self.long_term_memory.items()])
            
            prompt = f"""
            Résumez brièvement cette conversation sur une offre d'emploi:
            
            {history_text}
            
            {facts_summary if facts_summary else ""}
            
            Créez un résumé CONCIS qui identifie les informations principales déjà fournies.
            Maximum 3 phrases. Langue: {self.user_language}.
            """
            
            response = self.llm.invoke(prompt)
            return response.content.strip()
            
        except Exception as e:
            print(f"⚠️ Erreur lors de la génération du résumé: {e}")
            
            # Message minimal selon la langue
            if self.user_language == "fr":
                return "Conversation en cours sur une offre d'emploi."
            elif self.user_language == "es":
                return "Conversación en curso sobre una oferta de trabajo."
            else:
                return "Ongoing conversation about a job posting."