#!/bin/bash
# Script de déploiement pour Render

# Installer Poetry
pip install poetry

# Installer les dépendances (sans le groupe dev)
poetry install --without dev

# Si le déploiement échoue, c'est peut-être que votre projet utilise encore une ancienne version de Poetry
# Dans ce cas, essayez cette commande alternative
if [ $? -ne 0 ]; then
    echo "Tentative avec la syntaxe alternative pour une version plus ancienne de Poetry..."
    poetry install --no-interaction --no-ansi --no-dev
fi

# Préparation finale (vous pouvez ajouter d'autres commandes au besoin)
echo "Préparation terminée"
