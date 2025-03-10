#!/bin/bash
# Script de déploiement pour Render

# Installer Poetry
pip install poetry

# Installer les dépendances (sans le groupe dev)
poetry install --without dev --no-interaction --no-ansi

# Vérifier si l'installation a réussi
if [ $? -ne 0 ]; then
    echo "Erreur : l'installation des dépendances a échoué."
    exit 1
fi

# Préparation finale
echo "Préparation terminée"
