# app.py - Version corrigée pour gérer la langue des questions

from flask import Flask, render_template, request, jsonify, session
import uuid
import json
import sys
import traceback
import os
from workflow.form_workflow import FormWorkflow
from agents.lang_mem import LangMem
from agents.question_agent import QuestionAgent
from agents.update_agent import UpdateAgent
from config.llm_config import llm
from models.job_details import JobDetails

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Dictionnaire pour stocker les sessions actives
active_sessions = {}

@app.route('/')
def index():
    """Affiche la page d'accueil"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    session_id = session['session_id']
    if session_id not in active_sessions:
        job_details = JobDetails()
        lang_mem = LangMem(llm)
        question_agent = QuestionAgent()
        question_agent.job_details = job_details
        update_agent = UpdateAgent(job_details, lang_mem)
        
        active_sessions[session_id] = {
            "job_details": job_details,
            "lang_mem": lang_mem,
            "question_agent": question_agent,
            "update_agent": update_agent,
            "conversation": [],
            "current_field": None,
            "current_question": None,
            "is_first_interaction": True
        }
    
    sess = active_sessions[session_id]
    if sess["is_first_interaction"] and not sess["conversation"]:
        initial_message = "Envoyez un premier message (ex. Bonjour) pour commencer."
        sess["conversation"].append({"role": "system", "content": initial_message})
        sess["lang_mem"].add_interaction("system", initial_message)
    
    return render_template('index.html', initial_conversation=sess["conversation"])

def translate_question(question, target_lang, llm):
    """Traduit une question dans la langue cible à l'aide de l'LLM."""
    if target_lang == 'en':
        prompt = f"""
        Traduisez la question suivante en anglais de manière naturelle et professionnelle:
        "{question}"
        Retournez UNIQUEMENT la traduction, sans JSON ni commentaire.
        """
    elif target_lang == 'fr':
        prompt = f"""
        Traduisez la question suivante en français de manière naturelle et professionnelle:
        "{question}"
        Retournez UNIQUEMENT la traduction, sans JSON ni commentaire.
        """
    else:
        return question  # Langue non prise en charge, retourner la question originale
    
    try:
        response = llm.invoke(prompt)
        return response.content.strip()
    except Exception as e:
        print(f"⚠️ Erreur lors de la traduction: {e}")
        return question  # En cas d'erreur, retourner la question originale

def generate_welcome_response(user_input, lang_mem, llm):
    """Génère une réponse de bienvenue en fonction de la langue détectée."""
    lang = lang_mem._detect_language(user_input)
    lang_mem.user_language = lang
    
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
        response = llm.invoke(prompt)
        return response.content.strip()
    except Exception as e:
        print(f"⚠️ Erreur lors de la génération de la réponse: {e}")
        return "Bonjour ! Je suis un assistant intelligent qui aide les recruteurs à créer des offres d'emploi."

@app.route('/api/message', methods=['POST'])
def process_message():
    """Traite les messages du chatbot"""
    data = request.json
    user_message = data.get('message', '').strip()
    session_id = session.get('session_id')
    
    if not session_id or session_id not in active_sessions:
        return jsonify({"error": "Session invalide"}), 400
    
    sess = active_sessions[session_id]
    
    # Gestion spéciale pour le message 'START'
    if user_message == 'START' and sess["is_first_interaction"]:
        initial_message = "Envoyez un premier message (ex. Bonjour) pour commencer."
        if not sess["conversation"]:
            sess["conversation"].append({"role": "system", "content": initial_message})
            sess["lang_mem"].add_interaction("system", initial_message)
        return jsonify({
            "response": initial_message,
            "field": None,
            "conversation": sess["conversation"]
        })
    
    # Si aucun message n'est envoyé et c'est la première interaction, renvoyer l'invite initiale
    if not user_message and sess["is_first_interaction"]:
        initial_message = "Envoyez un premier message (ex. Bonjour) pour commencer."
        if not sess["conversation"]:
            sess["conversation"].append({"role": "system", "content": initial_message})
            sess["lang_mem"].add_interaction("system", initial_message)
        return jsonify({
            "response": initial_message,
            "field": None,
            "conversation": sess["conversation"]
        })
    
    # Ajouter le message de l'utilisateur à la conversation (si non vide)
    if user_message:
        sess["conversation"].append({"role": "user", "content": user_message})
        sess["lang_mem"].add_interaction("user", user_message)
    
    try:
        # Gestion de la première interaction
        if sess["is_first_interaction"] and user_message:
            welcome_response = generate_welcome_response(user_message, sess["lang_mem"], llm)
            sess["conversation"].append({"role": "system", "content": welcome_response})
            sess["lang_mem"].add_interaction("system", welcome_response)
            
            # Poser la première question
            field, question = sess["question_agent"].get_next_question(
                sess["job_details"], 
                sess["lang_mem"].get_summary()
            )
            if field and question:
                # Traduire la question selon la langue détectée
                translated_question = translate_question(question, sess["lang_mem"].user_language, llm)
                sess["current_field"] = field
                sess["current_question"] = translated_question
                sess["conversation"].append({"role": "system", "content": translated_question})
                sess["lang_mem"].add_interaction("system", translated_question)
                sess["is_first_interaction"] = False
                return jsonify({
                    "response": f"{welcome_response}\n\n{translated_question}",
                    "field": field,
                    "conversation": sess["conversation"],
                    "success": True,
                    "current_state": sess["job_details"].get_state()
                })
            else:
                sess["is_first_interaction"] = False
                return jsonify({
                    "response": welcome_response,
                    "field": None,
                    "conversation": sess["conversation"],
                    "success": True,
                    "current_state": sess["job_details"].get_state()
                })
        
        # Si ce n'est pas la première interaction, traiter la réponse de l'utilisateur
        # Vérifier si une question est en attente avant de traiter la réponse
        if sess["current_field"] is None or sess["current_question"] is None:
            # Si aucune question n'est en attente, poser la prochaine question
            field, question = sess["question_agent"].get_next_question(
                sess["job_details"], 
                sess["lang_mem"].get_summary()
            )
            if field and question:
                # Traduire la question selon la langue détectée
                translated_question = translate_question(question, sess["lang_mem"].user_language, llm)
                sess["current_field"] = field
                sess["current_question"] = translated_question
                sess["conversation"].append({"role": "system", "content": translated_question})
                sess["lang_mem"].add_interaction("system", translated_question)
                return jsonify({
                    "response": translated_question,
                    "field": field,
                    "conversation": sess["conversation"],
                    "success": True,
                    "current_state": sess["job_details"].get_state()
                })
            else:
                response = "Merci! Toutes les informations nécessaires ont été recueillies."
                json_result = sess["job_details"].get_state()
                response += f"\n\nVoici le résultat de l'offre d'emploi:\n{json.dumps(json_result, indent=2, ensure_ascii=False)}"
                sess["current_field"] = None
                sess["current_question"] = None
                sess["conversation"].append({"role": "system", "content": response})
                sess["lang_mem"].add_interaction("system", response)
                return jsonify({
                    "response": response,
                    "field": None,
                    "conversation": sess["conversation"],
                    "success": True,
                    "current_state": sess["job_details"].get_state()
                })

        # Traiter la réponse de l'utilisateur
        success, message, intention_analysis = sess["update_agent"].update(
            sess["current_field"], 
            user_message, 
            sess["current_question"],
            sess["question_agent"]
        )
        
        # Analyser le résultat
        if success:
            # Si mise à jour réussie, passer à la question suivante
            field, question = sess["question_agent"].get_next_question(
                sess["job_details"],
                sess["lang_mem"].get_summary()
            )
            if field and question:
                # Traduire la question selon la langue détectée
                translated_question = translate_question(question, sess["lang_mem"].user_language, llm)
                sess["current_field"] = field
                sess["current_question"] = translated_question
                response = translated_question
            else:
                # Formulaire complet!
                response = "Merci! Toutes les informations nécessaires ont été recueillies."
                json_result = sess["job_details"].get_state()
                response += f"\n\nVoici le résultat de l'offre d'emploi:\n{json.dumps(json_result, indent=2, ensure_ascii=False)}"
                sess["current_field"] = None
                sess["current_question"] = None
        elif message and message.startswith("SHOW_STATUS:"):
            # Afficher le statut actuel
            filled_fields = {}
            for field, value in sess["job_details"].data["jobDetails"].items():
                if value not in [None, [], {}] and not (isinstance(value, dict) and not value.get("name")):
                    filled_fields[field] = value
            
            response = "Voici l'état actuel de l'offre d'emploi:\n"
            for k, v in filled_fields.items():
                if isinstance(v, (list, dict)):
                    response += f"• {k}: {json.dumps(v, ensure_ascii=False)}\n"
                else:
                    response += f"• {k}: {v}\n"
            
            # Continuer avec la question actuelle
            response += f"\n{sess['current_question']}"
        elif message and message.startswith("CHANGE_FIELD:"):
            # Changer de champ
            field_to_modify = message.split("CHANGE_FIELD:")[1]
            if field_to_modify in sess["job_details"].data["jobDetails"]:
                sess["current_field"] = field_to_modify
                current_value = sess["job_details"].data["jobDetails"].get(field_to_modify, "Non spécifié")
                if isinstance(current_value, (list, dict)):
                    formatted_value = json.dumps(current_value, ensure_ascii=False)
                else:
                    formatted_value = str(current_value)
                response = f"Valeur actuelle pour '{field_to_modify}': {formatted_value}. Nouvelle valeur?"
                sess["current_question"] = response
            else:
                response = f"Champ '{field_to_modify}' non reconnu. {sess['current_question']}"
        else:
            # Erreur, reformuler la question
            if message:
                response = message
            else:
                response = sess["update_agent"].reformulate_question(
                    sess["current_field"],
                    sess["current_question"],
                    "Réponse non valide",
                    intention_analysis
                )
                sess["current_question"] = response
        
        # Ajouter la réponse à la conversation
        sess["conversation"].append({"role": "system", "content": response})
        sess["lang_mem"].add_interaction("system", response)
        
        # Obtenir l'état actuel
        current_state = sess["job_details"].get_state()
        
        return jsonify({
            "response": response,
            "field": sess["current_field"],
            "success": success,
            "conversation": sess["conversation"],
            "current_state": current_state
        })
        
    except Exception as e:
        error_msg = f"Erreur: {str(e)}"
        traceback.print_exc()
        return jsonify({"error": error_msg}), 500

@app.route('/api/reset', methods=['POST'])
def reset_session():
    """Réinitialise la session actuelle"""
    session_id = session.get('session_id')
    if session_id in active_sessions:
        del active_sessions[session_id]
    session['session_id'] = str(uuid.uuid4())
    return jsonify({"success": True, "message": "Session réinitialisée"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))