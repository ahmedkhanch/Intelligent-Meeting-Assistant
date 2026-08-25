"""Summarizer — the core AI agent. Sends transcript to DeepSeek and receives structured PV JSON."""

import json
import logging
import re
import uuid

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# ── Prompt template ──────────────────────────────────────────────────
# This is the most important string in the project.
# It tells DeepSeek exactly how to structure the output.
# ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
Tu es un assistant CRM vocal pour Ora Telecom. Tu analyses des transcriptions d'appels \
téléphoniques et tu produis un Procès-Verbal (PV) structuré en JSON.

## Règles métier

1. **Type d'appel** : détecte automatiquement à partir du contenu :
   - `#appel-commercial` : parle de deals, contrats, partenariats, devis, propositions commerciales, clients
   - `#appel-tech` : parle de développement, infra, API, base de données, déploiement, bugs, environnement, GitLab

2. **Participants** :
   - `left` : l'interlocuteur principal côté Ora Telecom (celui qui parle au nom d'Ora)
   - `right` : l'interlocuteur principal externe (client, partenaire, prestataire)
   - `additional_participants` : toutes les AUTRES personnes présentes à l'appel ou à la
     réunion. Chacune doit avoir un champ `side` : `"left"` si elle est côté Ora Telecom,
     `"right"` si elle est externe.
   - IMPORTANT : ne perds aucun participant. S'il y a plus de deux personnes, mets les
     personnes supplémentaires dans `additional_participants`. S'il n'y en a que deux,
     laisse la liste vide `[]`.
   - Si la transcription contient des étiquettes de locuteur (format `[HH:MM:SS] Nom : texte`),
     ces noms sont fiables : utilise-les directement pour remplir `name` et pour déterminer
     `side` (celui qui parle au nom d'Ora → `left`, l'externe → `right`).
   - Si la transcription commence par une ligne « PARTICIPANTS: ... », c'est une vérité de
     terrain : utilise-la pour fixer le `side` de chacun. « X (côté Ora Telecom) » → `left`,
     « X (externe) » → `right`. Ne devine pas à partir du seul nom.

3. **Compte rendu** : résumé narratif de 3 à 6 phrases en français. Capture :
   - Le contexte de l'appel
   - Ce qui a été discuté
   - Les décisions prises
   - Les points en suspens

4. **Actions / Todos** :
   - Pour un appel commercial : extrais les actions avec un propriétaire et une deadline. Pas de difficulté.
   - Pour un appel tech : extrais les todos avec propriétaire, deadline, ET difficulté.

5. **Difficulté** (appels tech uniquement) :
   - `facile` : tâche simple (config, doc, update mineur)
   - `difficile` : tâche complexe (implémentation, intégration, refactoring)
   - `très difficile` : tâche très complexe (architecture, design système, bug critique, migration)

6. **Réunion planifiée** : détecte si un appel de suivi ou une réunion a été programmé.

7. **Dates** : aujourd'hui est le {today}. Utilise le format ISO 8601 (YYYY-MM-DD).

Retourne UNIQUEMENT du JSON valide, sans texte avant ni après. Le JSON doit correspondre exactement à cette structure :

```json
{{
  "call_type": "#appel-commercial ou #appel-tech",
  "left": {{
    "name": "...",
    "phone_number": "...",
    "role": "...",
    "side": "left"
  }},
  "right": {{
    "name": "...",
    "phone_number": "...",
    "role": "...",
    "side": "right"
  }},
  "additional_participants": [
    {{
      "name": "...",
      "phone_number": "...",
      "role": "...",
      "side": "left ou right"
    }}
  ],
  "subject": "Titre de l'appel",
  "compte_rendu": "Résumé narratif de 3 à 6 phrases en français.",
  "actions": [
    {{
      "title": "Description de l'action",
      "owner": "Prénom de la personne responsable",
      "deadline": "YYYY-MM-DD ou null",
      "difficulty": "facile | difficile | très difficile | null"
    }}
  ],
  "meeting_created": true ou false,
  "meeting_datetime": "YYYY-MM-DDTHH:MM:SSZ ou null"
}}
```
"""

USER_PROMPT = """\
Voici la transcription d'un appel téléphonique. Analyse-la et produis le PV structuré.

---

{transcript}

---
Retourne uniquement le JSON du PV."""


# ── Client ───────────────────────────────────────────────────────────


def _get_client() -> AsyncOpenAI:
    """Create a DeepSeek client from settings."""
    return AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )


# ── Public API ───────────────────────────────────────────────────────


async def summarize(
    transcript: str,
    call_date: str | None = None,
    model: str | None = None,
) -> dict:
    """Send a transcript to DeepSeek and return the structured PV as a dict.

    Args:
        transcript: The raw call transcript text.
        call_date: ISO date string for the call (defaults to today).
        model: DeepSeek model override (defaults to settings.deepseek_model).

    Returns:
        dict matching the PV Pydantic schema.
    """
    from datetime import date

    today = call_date or date.today().isoformat()
    model = model or settings.deepseek_model

    client = _get_client()

    logger.info("Summarizing transcript via DeepSeek (%s) — %d chars", model, len(transcript))

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(today=today)},
            {"role": "user", "content": USER_PROMPT.format(transcript=transcript)},
        ],
        max_tokens=4500,
        temperature=0.3,  # low temp for structured output
    )

    raw = response.choices[0].message.content or ""
    logger.debug("DeepSeek raw response:\n%s", raw)

    pv = _parse_json(raw)

    # Assign a stable PV ID if the LLM didn't generate one
    if not pv.get("pv_id"):
        pv["pv_id"] = str(uuid.uuid4())

    return pv


# ── Helpers ──────────────────────────────────────────────────────────


def _parse_json(raw: str) -> dict:
    """Extract and parse JSON from the LLM response.

    Handles cases where the model wraps JSON in ```json blocks or adds extra text.
    """
    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from ```json ... ``` block
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find the outermost { ... }
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from DeepSeek response:\n{raw}")
