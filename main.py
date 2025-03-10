# main.py - Point d'entrée principal optimisé
import traceback
import sys
from workflow.form_workflow import FormWorkflow

def main():
    # Message d'accueil orienté recruteurs
    print("""
╔═════════════════════════════════════════════════════════════════╗
║               ASSISTANT CRÉATION D'OFFRES D'EMPLOI              ║
╠═════════════════════════════════════════════════════════════════╣
║ Cet assistant va vous aider à créer une offre d'emploi          ║
║ complète en conversant naturellement avec vous.                 ║
║                                                                 ║
║ En tant que recruteur, spécifiez :                              ║
║ - Le titre et la description du poste                           ║
║ - Les compétences requises et le niveau d'expérience            ║
║ - Le type de contrat et la localisation                         ║
║ - Les conditions salariales                                     ║
║                                                                 ║
║ L'assistant s'adaptera à vos besoins et gérera automatiquement  ║
║ les contraintes conditionnelles et la cohérence des données.    ║
╚═════════════════════════════════════════════════════════════════╝
    """)
    
    # Augmenter la limite de récursion de Python
    sys.setrecursionlimit(1500)  # Valeur par défaut: 1000
    
    try:
        # Création et démarrage du workflow
        form = FormWorkflow()
        form.start()
    except Exception as e:
        print(f"\n❌ Une erreur s'est produite: {str(e)}")
        print("\nDétail de l'erreur:")
        traceback.print_exc()
        print("\nVeuillez vérifier votre configuration et réessayer.")

if __name__ == "__main__":
    main()
    