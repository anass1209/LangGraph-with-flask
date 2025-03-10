# app.py
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
    # Générer un ID de session s'il n'existe pas encore
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    # Créer une nouvelle session si elle n'existe pas
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
            "current_question": None
        }
    
    return render_template('index.html')

@app.route('/api/message', methods=['POST'])
def process_message():
    """Traite les messages du chatbot"""
    data = request.json
    user_message = data.get('message', '')
    session_id = session.get('session_id')
    
    if not session_id or session_id not in active_sessions:
        return jsonify({"error": "Session invalide"}), 400
    
    sess = active_sessions[session_id]
    
    # Ajouter le message de l'utilisateur à la conversation
    sess["conversation"].append({"role": "user", "content": user_message})
    sess["lang_mem"].add_interaction("user", user_message)
    
    try:
        # Si nous n'avons pas encore posé de question, obtenir la première
        if sess["current_field"] is None or sess["current_question"] is None:
            field, question = sess["question_agent"].get_next_question(
                sess["job_details"], 
                sess["lang_mem"].get_summary()
            )
            if field and question:
                sess["current_field"] = field
                sess["current_question"] = question
                # Ajouter la question à la conversation
                sess["conversation"].append({"role": "system", "content": question})
                sess["lang_mem"].add_interaction("system", question)
                return jsonify({
                    "response": question,
                    "field": field,
                    "conversation": sess["conversation"]
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
                sess["current_field"] = field
                sess["current_question"] = question
                response = question
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

# À la fin du fichier app.py
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))