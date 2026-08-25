# Input Schema — Conversation Format Expected by DeepSeek

This document specifies the transcript format that the summarizer (`app/agent/summarizer.py`) passes to DeepSeek. The LLM is flexible, but following this schema produces the most reliable Procès-Verbal (PV).

---

## The Wrapper (What DeepSeek Actually Receives)

The transcript you provide is wrapped by the system before reaching DeepSeek:

```
┌──────────────────────────────────────────────────────┐
│  SYSTEM PROMPT (detailed instructions in French)     │
│  - How to detect call type                           │
│  - How to identify participants (left vs right)      │
│  - How to write compte rendu (3-6 sentences)         │
│  - How to extract actions with difficulty levels     │
│  - How to detect follow-up meetings                  │
│  - Return ONLY valid JSON                            │
├──────────────────────────────────────────────────────┤
│  USER PROMPT:                                        │
│  "Voici la transcription d'un appel téléphonique.    │
│   Analyse-la et produis le PV structuré.             │
│                                                      │
│   ---                                                │
│   {YOUR TRANSCRIPT GOES HERE}                        │
│   ---                                                │
│   Retourne uniquement le JSON du PV."                │
└──────────────────────────────────────────────────────┘
```

---

## Recommended Format: Timestamped Dialogue

The format used by the existing test fixtures. Best results.

```
[HH:MM:SS] APPEL DÉMARRÉ
[HH:MM:SS] SpeakerName : Message text...
[HH:MM:SS] OtherSpeaker : Reply text...
[HH:MM:SS] SpeakerName : More discussion...
...
[HH:MM:SS] APPEL TERMINÉ
```

### Rules

| Rule | Example |
|------|---------|
| **One message per line** | `[14:05:03] Ahmed : Bonjour...` |
| **Timestamp in brackets** | `[HH:MM:SS]` at the start of every line |
| **Speaker name, colon, space** | `Ahmed : ` not `Ahmed:` |
| **Bookend markers** | First line = `APPEL DÉMARRÉ`, last line = `APPEL TERMINÉ` |
| **French language** | The LLM prompt is in French; transcripts should be too |
| **Natural dialogue** | Use real spoken French, not formal written French |

### Full Example (Commercial Call)

```
[14:05:00] APPEL DÉMARRÉ
[14:05:03] Ahmed : Bonjour Mehdi, merci de prendre le temps. Comment ça va depuis la dernière fois ?
[14:05:06] Client Contact : Bonjour Ahmed, ça va super. J'ai bien reçu votre proposition, on l'a étudiée en interne cette semaine.
[14:05:10] Ahmed : Excellent, justement c'est pour ça que je vous appelle. Quel est votre retour sur le partenariat Q3 ?
[14:05:14] Client Contact : Écoutez, on est très intéressés. Le pricing est compétitif, et votre approche modulaire correspond bien à ce qu'on cherche pour ACME Corp.
[14:05:20] Ahmed : Content de l'entendre. L'idée c'est qu'on commence avec le module CRM de base en juillet, puis le module analytics en septembre.
[14:05:48] Client Contact : Super. Et sur l'aspect contractuel, on aimerait avoir une clause de réversibilité. C'est obligatoire pour nous.
[14:05:52] Ahmed : Aucun souci, on inclut la clause dans la proposition. Vous voulez qu'on cale une réunion avec les équipes techniques ?
[14:05:56] Client Contact : Oui, excellente idée. La semaine du 23 juin ça vous irait ?
[14:06:00] Ahmed : On peut faire le 23 juin à 14h. J'invite kh et votre IT.
[14:06:18] Client Contact : À bientôt, au revoir.
[14:06:20] APPEL TERMINÉ
```

### Full Example (Technical Call)

```
[17:30:12] APPEL DÉMARRÉ
[17:30:15] kh : Salam Oussema, ça va ? T'es dispo pour faire le point sur l'infra Ora CRM ?
[17:30:18] Oussema : Salam kh, ouais bien sûr. J'ai regardé ton message sur Slack, on va faire le point.
[17:30:22] kh : Super. Donc on a besoin de monter deux environnements : un dev et un prod. L'environnement dev c'est pour que l'équipe puisse tester l'API CRM Vocal, et le prod évidemment pour la mise en ligne.
[17:30:30] Oussema : Ok, je peux créer les deux sur GitLab. Pour le dev, je peux le faire d'ici vendredi. Pour le prod, il faut qu'on voit avec l'encadrant pour les credentials AWS.
[17:31:40] kh : Top. Donc pour résumer : toi tu t'occupes de l'environnement dev sur GitLab pour vendredi, tu me fais la reco auth pour demain, et tu implémentes le endpoint pour le 25. Moi je t'envoie les specs et le payload JSON aujourd'hui. On se revoit mercredi 25 à 10h.
[17:31:47] kh : À mercredi, salam !
[17:31:50] APPEL TERMINÉ
```

---

## What the LLM Extracts From This Format

DeepSeek reads the dialogue and infers:

| Field | How it's detected |
|-------|-------------------|
| **call_type** | Context: commercial vocabulary (devis, contrat, partenariat) vs technical (API, GitLab, environnements, déploiement) |
| **left participant** | The Ora Telecom speaker — typically the one driving the agenda or representing the company |
| **right participant** | The external party — client, partner, or colleague from another team |
| **subject** | Synthesized from the opening lines — what the call is about |
| **compte_rendu** | Narrative summary of: context → discussion → decisions → open points |
| **actions** | Explicit commitments ("je te fais ça pour demain", "tu peux livrer pour le 25") |
| **difficulty** | How the task is described: "c'est facile" → facile, "c'est complexe" → difficile, "c'est un boulot conséquent" → très difficile |
| **meeting** | Explicit scheduling ("mercredi 25 à 10h", "on se refait un point la semaine prochaine") |

---

## Alternative Formats That Also Work

DeepSeek is a general-purpose LLM — it handles variations. These all work, just with slightly lower reliability:

### Format A: Bare Dialogue (no timestamps)
```
Ahmed: Bonjour, merci d'être là.
Mehdi: Bonjour Ahmed, avec plaisir.
Ahmed: Alors, concernant le contrat...
```
**Trade-off:** No temporal context. The LLM can't tell how long the call lasted or detect pauses.

### Format B: Speaker-Only (no colons)
```
Ahmed - Bonjour, merci d'être là.
Mehdi - Bonjour Ahmed, avec plaisir.
```
**Trade-off:** Works but occasionally confuses the parser for multi-word names.

### Format C: JSON Input
```json
{
  "utterances": [
    {"speaker": "Ahmed", "text": "Bonjour...", "timestamp": "14:05:03"},
    {"speaker": "Client Contact", "text": "Bonjour Ahmed...", "timestamp": "14:05:06"}
  ]
}
```
**Trade-off:** More structured, but the summarizer prompt would need adjustment to handle JSON input. Not recommended unless your STT outputs JSON natively.

---

## What Makes a Good Transcript (for LLM Accuracy)

| Quality | Why it matters |
|---------|---------------|
| **Speakers clearly identified** | The LLM needs to know who is Ora Telecom (left) vs external (right) |
| **Complete sentences** | Fragments reduce action extraction accuracy |
| **Closure at the end** | The call summary at the end (récapitulatif) is the LLM's strongest signal for actions and meetings |
| **Natural spoken French** | The LLM prompt is in French — mixing languages degrades output |
| **No side-channel notes** | Don't include "\[rire\]", "\[pause\]", or annotator comments — they distract the LLM |
| **200-400 lines max** | Very long transcripts may exceed the 2000-token output limit; the LLM will truncate |

---

## How to Pass a Transcript

### Via CLI (Phase 1 — development)
```bash
python scripts/mock_call.py --file path/to/transcript.txt
python scripts/mock_call.py --text "Ahmed: Bonjour..."
```

### Via API (Phase 1 — integration)
```http
POST /api/call/process
Content-Type: application/json

{
  "transcript": "[14:05:00] APPEL DÉMARRÉ\n[14:05:03] Ahmed : Bonjour...",
  "session_id": "call-001",
  "call_date": "2026-06-20T14:00:00Z"
}
```

### Via WebSocket (Phase 2 — planned)
```
WebSocket connect → stream text chunks → pipeline triggers on call end
```
The WebSocket handler in `app/ws/call_handler.py` will accumulate chunks and pass the complete transcript to the summarizer. Format will be the same — just delivered incrementally.

---

## Summary

```
Your transcript              What DeepSeek produces
═══════════════              ═══════════════════════
[HH:MM:SS] Name : Message    {
[HH:MM:SS] Name : Reply        "call_type": "#appel-commercial",
[HH:MM:SS] Name : Discussion   "left": { "name": "...", ... },
...                            "right": { "name": "...", ... },
[HH:MM:SS] APPEL TERMINÉ       "subject": "...",
                               "compte_rendu": "...",
                               "actions": [ { "title": "...", ... } ],
                               "meeting_created": true/false,
                               "meeting_datetime": "..."
                             }
```
