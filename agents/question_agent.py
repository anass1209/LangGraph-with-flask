# agents/question_agent.py - Version améliorée avec contexte recruteur et gestion dynamique

from config.llm_config import llm
import json
from typing import List, Tuple, Optional, Dict, Any
import re

class QuestionAgent:
    def __init__(self):
        self.llm = llm
        self.job_details = None
        
        # Questions pré-définies par défaut avec support multilingue
        self.example_questions = {
            "title": {
                "fr": "Quel est le titre du poste pour cette offre d'emploi ?",
            },
            "description": {
                "fr": "Pouvez-vous décrire les responsabilités du poste ?",
            },
            "discipline": {
                "fr": "Dans quelle discipline ce poste s'inscrit-il (ex. Informatique, Marketing) ?",
            },
            "availability": {
                "fr": "Quand le candidat doit-il être disponible (ex. immédiatement, 2 semaines) ?",
            },
            "seniority": {
                "fr": "Quel niveau d'expérience recherchez-vous (Junior, Mid, Senior) ?",
            },
            "languages": {
                "fr": "Quelles langues sont requises (ex. Français avancé, Anglais intermédiaire) ?",
            },
            "skills": {
                "fr": "Quelles compétences sont nécessaires (ex. Python, Gestion de projet) ?",
            },
            "jobType": {
                "fr": "S'agit-il d'un poste Freelance, Temps plein ou Temps partiel ?",
            },
            "type": {
                "fr": "Le travail est-il à distance, sur site ou hybride ?",
            },
            "minHourlyRate": {
                "fr": "Quel est le taux horaire minimum pour ce poste freelance ?",
            },
            "maxHourlyRate": {
                "fr": "Quel est le taux horaire maximum pour ce poste freelance ?",
            },
            "weeklyHours": {
                "fr": "Combien d'heures par semaine sont prévues ?",
            },
            "estimatedWeeks": {
                "fr": "Combien de semaines durera ce projet freelance ?",
            },
            "minFullTimeSalary": {
                "fr": "Quel est le salaire annuel minimum pour ce poste à temps plein ?",
            },
            "maxFullTimeSalary": {
                "fr": "Quel est le salaire annuel maximum pour ce poste à temps plein ?",
            },
            "minPartTimeSalary": {
                "fr": "Quel est le salaire minimum pour ce poste à temps partiel ?",
            },
            "maxPartTimeSalary": {
                "fr": "Quel est le salaire maximum pour ce poste à temps partiel ?",
            },
            "continents": {
                "fr": "Sur quels continents recherchez-vous des candidats (ex. Europe, Asie) ?",
            },
            "countries": {
                "fr": "Dans quels pays le poste est-il ouvert (ex. France, Maroc) ?",
            },
            "regions": {
                "fr": "Dans quelles régions spécifiques (ex. Île-de-France, Casablanca) ?",
            },
            "timeZone": {
                "fr": "Quel fuseau horaire est requis (ex. CET, EST) ?",
            },
            "country": {
                "fr": "Dans quel pays le poste est-il basé (ex. France) ?",
            },
            "city": {
                "fr": "Dans quelle ville le poste est-il situé (ex. Paris) ?",
            }
        }

    def get_field_type_description(self, field: str) -> str:
        """Retourne une description du type attendu pour un champ donné."""
        list_fields = {"countries", "continents", "regions", "skills", "languages"}
        numeric_fields = {
            "minHourlyRate", "maxHourlyRate", "weeklyHours", "estimatedWeeks",
            "minFullTimeSalary", "maxFullTimeSalary", "minPartTimeSalary", "maxPartTimeSalary",
            "availability"
        }
        dict_fields = {"timeZone", "country"}
        enum_fields = {
            "jobType": {"FREELANCE", "FULLTIME", "PARTTIME"},
            "type": {"REMOTE", "ONSITE", "HYBRID"},
            "seniority": {"JUNIOR", "MID", "SENIOR"}
        }

        if field in list_fields:
            if field == "languages":
                return "Liste d'objets: [{name: string, level: string, required: boolean}]"
            elif field == "skills":
                return "Liste d'objets: [{name: string, mandatory: boolean}]"
            else:
                return "Liste d'objets: [{name: string}]"
        elif field in dict_fields:
            if field == "timeZone":
                return "Objet: {name: string, overlap: number}"
            else:
                return "Objet: {name: string}"
        elif field in enum_fields:
            return f"Énumération: {', '.join(enum_fields[field])}"
        elif field in numeric_fields:
            return "Nombre: valeur numérique"
        else:
            return "Texte: chaîne de caractères"

    def get_next_question(self, job_details, memory_summary: str) -> Tuple[Optional[str], Optional[str]]:
        """Détermine la prochaine question à poser en fonction des champs manquants."""
        if not self.job_details:
            self.job_details = job_details

        missing_fields = self.job_details.get_missing_fields()
        if not missing_fields:
            return None, None

        # Ordre de priorité pour les champs essentiels
        priority_order = ["title", "description", "discipline", "availability", "seniority", "languages", "skills", "jobType", "type"]
        for field in priority_order:
            if field in missing_fields:
                question = self.generate_question_with_llm(field, memory_summary)
                return field, question

        # Champs spécifiques selon jobType et type
        job_type = self.job_details.data["jobDetails"].get("jobType")
        work_type = self.job_details.data["jobDetails"].get("type")
        
        if job_type:
            specific_fields = []
            if job_type == "FREELANCE":
                specific_fields = ["minHourlyRate", "maxHourlyRate", "weeklyHours", "estimatedWeeks"]
            elif job_type == "FULLTIME":
                specific_fields = ["minFullTimeSalary", "maxFullTimeSalary"]
            elif job_type == "PARTTIME":
                specific_fields = ["minPartTimeSalary", "maxPartTimeSalary"]
            for field in specific_fields:
                if field in missing_fields:
                    question = self.generate_question_with_llm(field, memory_summary)
                    return field, question

        if work_type:
            if work_type == "REMOTE":
                geo_fields = ["continents", "countries", "regions", "timeZone"]
                for field in geo_fields:
                    if field in missing_fields:
                        question = self.generate_question_with_llm(field, memory_summary)
                        return field, question
            elif work_type in ["ONSITE", "HYBRID"]:
                location_fields = ["country", "city"]
                for field in location_fields:
                    if field in missing_fields:
                        question = self.generate_question_with_llm(field, memory_summary)
                        return field, question

        # Si aucun champ prioritaire, prendre le premier manquant
        field = missing_fields[0]
        question = self.generate_question_with_llm(field, memory_summary)
        return field, question

    def generate_question_with_llm(self, field: str, memory_summary: str = "Aucun historique") -> str:
        """Génère une question dynamique avec le LLM en tenant compte du contexte."""
        if not self.job_details:
            return self.example_questions.get(field, {}).get("fr", f"Précisez {field} pour cette offre.")

        current_state = self.job_details.get_state().get("jobDetails", {})
        filled_fields = {k: v for k, v in current_state.items() if v not in [None, [], {}] and not (isinstance(v, dict) and not v.get("name"))}

        prompt = f"""
        Générez une question concise pour un recruteur sur le champ '{field}' d'une offre d'emploi.

        **Contexte global**:
        - Champs déjà remplis: {json.dumps(filled_fields, ensure_ascii=False)}
        - Résumé conversationnel: {memory_summary}
        - Type attendu pour '{field}': {self.get_field_type_description(field)}

        **Description des champs**:
        - 'title': Titre du poste (ex. Développeur Full Stack, Data Scientist).
        - 'description': Responsabilités et missions principales du poste.
        - 'discipline': Domaine professionnel (ex. Informatique, Finance, Marketing).
        - 'availability': Délai avant que le candidat ne commence (ex. immédiat, 2 semaines).
        - 'seniority': Niveau d'expérience requis (ex. Junior, Mid, Senior).
        - 'languages': Langues nécessaires avec niveau (ex. Français avancé, Anglais B2).
        - 'skills': Compétences techniques ou soft skills (ex. Python, Leadership).
        - 'jobType': Type de contrat (Freelance, Temps plein, Temps partiel).
        - 'type': Mode de travail (Remote, Onsite, Hybride).
        - 'minHourlyRate', 'maxHourlyRate': Fourchette de taux horaire pour freelance.
        - 'weeklyHours': Heures par semaine pour freelance.
        - 'estimatedWeeks': Durée estimée du projet freelance.
        - 'minFullTimeSalary', 'maxFullTimeSalary': Fourchette salariale annuelle pour temps plein.
        - 'minPartTimeSalary', 'maxPartTimeSalary': Fourchette salariale pour temps partiel.
        - 'continents', 'countries', 'regions': Zones géographiques pour candidats ou poste.
        - 'timeZone': Fuseau horaire requis pour travail à distance.
        - 'country', 'city': Localisation physique pour onsite/hybride.

        **RÈGLES STRICTES**:
        1. Style CONVERSATIONNEL et naturel, adapté à un recruteur.
        2. Maximum 15 mots (hors exemples).
        3. Inclure 2-3 exemples pertinents au champ '{field}'.
        4. Langue: fr (par défaut).
        5. Poser une question sur '{field}', pas sur autre chose (ex. pas sur le nombre de postes).

        **EXEMPLES ATTENDUS**:
        - Pour 'availability': "Quand le candidat doit-il commencer (ex. immédiat, 1 mois) ?"
        - Pour 'skills': "Quelles compétences sont clés (ex. Java, Communication) ?"

        Retournez UNIQUEMENT la question.
        """
        try:
            response = self.llm.invoke(prompt)
            question = response.content.strip()
            # Limiter à 15 mots hors exemples pour respecter la contrainte
            parts = question.split(" (")
            main_part = parts[0].split()
            if len(main_part) > 15:
                question = " ".join(main_part[:15]) + (" (" + " (".join(parts[1:]) if len(parts) > 1 else "")
            return question
        except Exception as e:
            print(f"⚠️ Erreur génération question LLM pour '{field}': {e}")
            return self.example_questions.get(field, {}).get("fr", f"Précisez {field} pour cette offre.")