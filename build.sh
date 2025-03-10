#!/bin/bash
pip install poetry
poetry install --without dev --no-interaction --no-ansi
if [ $? -ne 0 ]; then
    echo "Erreur : l'installation des dépendances a échoué."
    exit 1
fi
echo "Préparation terminée"