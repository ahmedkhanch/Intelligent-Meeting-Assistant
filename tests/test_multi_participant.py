"""Multi-participant tolerance tests.

Verifies that a meeting with more than two people is captured end-to-end:
the PV schema stores every speaker (not just left/right), the summarizer
prompt instructs the LLM to emit them, and downstream routing/formatting
does not drop them.
"""

from app.agent.summarizer import SYSTEM_PROMPT
from app.models.call import CallStartRequest
from app.models.pv import PV
from app.routing.hubspot import contacts, deals


def _four_person_pv() -> dict:
    """A PV dict for a 4-person meeting (2 Ora + 2 external)."""
    return {
        "call_type": "#appel-tech",
        "left": {"name": "kh", "role": "CTO", "side": "left"},
        "right": {"name": "Oussema", "role": "DevOps", "side": "right"},
        "additional_participants": [
            {"name": "Sami", "role": "Backend", "side": "left"},
            {"name": "Lina", "role": "Chef de projet", "side": "right"},
        ],
        "subject": "Intégration CRM Vocal",
        "compte_rendu": "Réunion à quatre.",
        "actions": [],
        "meeting_created": False,
    }


def test_pv_schema_accepts_additional_participants():
    pv = PV.model_validate({**_four_person_pv(), "call_date": "2026-08-20"})
    assert [p.name for p in pv.additional_participants] == ["Sami", "Lina"]
    assert pv.additional_participants[0].side == "left"
    assert pv.additional_participants[1].side == "right"


def test_pv_schema_defaults_to_no_additional_participants():
    """Two-person calls keep an empty list — backward compatible."""
    pv = PV.model_validate(
        {
            "call_type": "#appel-tech",
            "left": {"name": "kh", "side": "left"},
            "right": {"name": "Oussema", "side": "right"},
            "subject": "x",
            "compte_rendu": "Appel à deux.",
            "call_date": "2026-08-20",
        }
    )
    assert pv.additional_participants == []


def test_participant_phone_and_role_optional():
    """The LLM often returns null phone/role for meetings — must not fail."""
    pv = PV.model_validate(
        {
            "call_type": "#appel-tech",
            "left": {"name": "kh", "side": "left"},
            "right": {"name": "Oussema", "side": "right"},
            "additional_participants": [{"name": "Sami", "side": "left"}],
            "subject": "x",
            "compte_rendu": "Réunion.",
            "call_date": "2026-08-20",
        }
    )
    assert pv.additional_participants[0].phone_number == ""
    assert pv.additional_participants[0].role == ""


def test_call_start_request_accepts_additional_participants():
    req = CallStartRequest(
        left={"name": "kh", "side": "left"},
        right={"name": "Oussema", "side": "right"},
        additional_participants=[{"name": "Lina", "side": "right"}],
        subject="x",
    )
    assert [p.name for p in req.additional_participants] == ["Lina"]


def test_summarizer_prompt_mentions_additional_participants():
    assert "additional_participants" in SYSTEM_PROMPT


def test_deal_description_includes_additional_participants():
    desc = deals._format_deal_description(_four_person_pv())
    assert "Sami" in desc
    assert "Lina" in desc


async def test_contacts_creates_only_external_additional_participants():
    """Additional Ora-side team members are owners, not CRM contacts."""
    created = await contacts.create_contacts_for_additional_participants(_four_person_pv())
    names = [name for name, _ in created]
    assert "Lina" in names          # external → contact
    assert "Sami" not in names      # Ora-side → skipped
