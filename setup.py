#!/usr/bin/env python
# setup.py - Script pour configurer l'environnement FastHTML

import os
import sys
import shutil
from pathlib import Path

def create_directory_structure():
    """Crée la structure de répertoires nécessaire"""
    directories = [
        "static",
        "static/css",
        "static/js",
        "templates",
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✅ Dossier créé: {directory}")

def check_requirements():
    """Vérifie si les modules requis sont installés"""
    try:
        import flask
        print("✅ Flask est déjà installé")
    except ImportError:
        print("⚠️ Flask n'est pas installé. Installez-le avec: pip install flask")
        sys.exit(1)

def main():
    """Fonction principale"""
    print("🚀 Configuration de l'environnement FastHTML pour le chatbot...")
    
    # Vérifier les prérequis
    check_requirements()
    
    # Créer la structure de répertoires
    create_directory_structure()
    
    print("\n✅ Configuration terminée! Vous pouvez maintenant lancer l'application avec:")
    print("   python app.py")

if __name__ == "__main__":
    main()