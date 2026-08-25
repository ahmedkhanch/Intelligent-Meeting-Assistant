"""Seed the fallback store with sample PV data so the UI is not empty on first load."""
import asyncio
import sys
from datetime import datetime, date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import fallback_store


SAMPLE_PVS = [
    {
        "pv_id": "pv-tech-infra-001",
        "call_date": "2026-06-20T17:30:00",
        "call_type": "#appel-tech",
        "left": {
            "name": "kh",
            "phone_number": "+216 55 987 654",
            "role": "Ora Telecom — Dev",
            "side": "left",
        },
        "right": {
            "name": "Oussema",
            "phone_number": "+216 55 000 111",
            "role": "Ora Studio — Infra",
            "side": "right",
        },
        "subject": "Point infra Ora CRM — environnements + API contract",
        "compte_rendu": """Appel technique entre kh (Ora Telecom) et Oussema (Ora Studio) pour faire le point sur l'infrastructure du projet CRM Vocal.

Points abordés :
1. Création des environnements dev et prod sur GitLab. Le dev est prioritaire et facile — clonage du template GitLab CI avec configuration des variables. Le prod nécessite les credentials AWS de l'encadrant (VPC, IAM roles, sécurité).

2. API Contract pour POST /api/crm/tasks — payload JSON avec pv_id, call_date, subject, participants, et liste de tasks (title, owner, deadline, difficulty).

3. Authentification — débat entre API Key (simplicité) et JWT (plus standard, gestion expiration). Décision : Oussema recommande JWT avec un document comparatif.

4. Implémentation du endpoint POST /api/crm/tasks — prévue pour le 25 juin, tâche difficile nécessitant validation, error handling et tests.

5. Prochaine réunion : mercredi 25 juin à 10h.

Résumé : Oussema s'occupe de l'environnement dev (deadline vendredi), de la recommandation auth (demain), et du endpoint (25 juin). kh envoie les specs et le payload JSON aujourd'hui.""",
        "actions": [
            {
                "title": "Créer l'environnement dev sur GitLab (template CI + variables)",
                "owner": "Oussema",
                "deadline": "2026-06-23",
                "difficulty": "facile",
                "model_hint": "gpt-4o-mini",
            },
            {
                "title": "Rédiger la recommandation auth (API Key vs JWT)",
                "owner": "Oussema",
                "deadline": "2026-06-21",
                "difficulty": "facile",
                "model_hint": "gpt-4o-mini",
            },
            {
                "title": "Envoyer les specs complètes et le payload JSON pour POST /api/crm/tasks",
                "owner": "kh",
                "deadline": "2026-06-20",
                "difficulty": "facile",
                "model_hint": "gpt-4o-mini",
            },
            {
                "title": "Implémenter le endpoint POST /api/crm/tasks (validation, erreurs, tests)",
                "owner": "Oussema",
                "deadline": "2026-06-25",
                "difficulty": "difficile",
                "model_hint": "claude-sonnet-4-6",
            },
            {
                "title": "Obtenir les credentials AWS auprès de l'encadrant pour l'environnement prod",
                "owner": "Oussema",
                "deadline": None,
                "difficulty": "très difficile",
                "model_hint": "claude-opus-4-6",
            },
        ],
        "meeting_created": True,
        "meeting_datetime": "2026-06-25T10:00:00",
    },
    {
        "pv_id": "pv-tech-db-002",
        "call_date": "2026-06-22T14:00:00",
        "call_type": "#appel-tech",
        "left": {
            "name": "kh",
            "phone_number": "+216 55 987 654",
            "role": "Ora Telecom — Dev",
            "side": "left",
        },
        "right": {
            "name": "Sarra",
            "phone_number": "+216 55 111 222",
            "role": "Ora Studio — DBA",
            "side": "right",
        },
        "subject": "Mise en place base de données PostgreSQL + Redis",
        "compte_rendu": """Appel technique entre kh et Sarra concernant la mise en place de l'infrastructure de données pour CRM Vocal.

Points abordés :
1. PostgreSQL — schéma initial avec les tables calls, pvs, tasks, contacts. Sarra propose d'utiliser les migrations Alembic pour le versioning.

2. Redis — utilisé pour le cache des sessions d'appel et la file d'attente des transcriptions. Configuration cluster pour la prod recommandée.

3. Backup strategy — pg_dump quotidien avec rétention 30 jours. Point de restauration à définir.

4. Monitoring — connexion à Grafana pour les métriques DB. Alertes sur le disk usage et le nombre de connexions.

Prochaine réunion dans 2 semaines pour valider la recette.""",
        "actions": [
            {
                "title": "Créer le schéma PostgreSQL initial (calls, pvs, tasks, contacts)",
                "owner": "Sarra",
                "deadline": "2026-06-28",
                "difficulty": "facile",
                "model_hint": "gpt-4o-mini",
            },
            {
                "title": "Configurer Alembic pour les migrations",
                "owner": "Sarra",
                "deadline": "2026-06-28",
                "difficulty": "difficile",
                "model_hint": "claude-sonnet-4-6",
            },
            {
                "title": "Mettre en place le cluster Redis pour la prod",
                "owner": "Sarra",
                "deadline": "2026-07-05",
                "difficulty": "très difficile",
                "model_hint": "claude-opus-4-6",
            },
            {
                "title": "Configurer les backups pg_dump avec rétention 30j",
                "owner": "Sarra",
                "deadline": "2026-07-01",
                "difficulty": "facile",
                "model_hint": "gpt-4o-mini",
            },
            {
                "title": "Brancher les métriques DB sur Grafana",
                "owner": "kh",
                "deadline": "2026-07-08",
                "difficulty": "difficile",
                "model_hint": "claude-sonnet-4-6",
            },
        ],
        "meeting_created": False,
        "meeting_datetime": None,
    },
]


async def main():
    print("Seeding fallback store...")
    for pv_data in SAMPLE_PVS:
        pv_id = await fallback_store.save_pv(pv_data)
        subject = pv_data['subject'][:60]
        print(f"  [OK] {pv_id} - {subject}")
    print(f"\nDone! {len(SAMPLE_PVS)} PVs seeded.")
    print(f"Start the UI: cd ui-next && npm run dev")
    print(f"Then open http://localhost:3000")


if __name__ == "__main__":
    asyncio.run(main())
