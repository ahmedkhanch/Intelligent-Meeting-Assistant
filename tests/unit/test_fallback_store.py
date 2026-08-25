"""Tests for the JSON-file-backed fallback store.

Uses the ``fallback_store_tmp`` fixture so no test writes to ui-next/data/.
"""

from app import fallback_store


async def test_save_requires_pv_id(fallback_store_tmp):
    assert await fallback_store.save_pv({"subject": "no id"}) == ""


async def test_save_and_get_roundtrip(fallback_store_tmp, tech_pv):
    pv_id = await fallback_store.save_pv(tech_pv)
    assert pv_id == "pv-tech-1"

    got = await fallback_store.get_pv("pv-tech-1")
    assert got is not None
    assert got["subject"] == tech_pv["subject"]
    assert got["call_type"] == "#appel-tech"


async def test_get_pv_missing_returns_none(fallback_store_tmp):
    assert await fallback_store.get_pv("does-not-exist") is None


async def test_list_pvs_is_lightweight(fallback_store_tmp, tech_pv):
    await fallback_store.save_pv(tech_pv)
    pvs = await fallback_store.list_pvs()
    assert len(pvs) == 1

    entry = pvs[0]
    assert entry["pv_id"] == "pv-tech-1"
    assert entry["task_count"] == 2
    # Lightweight: no full narrative.
    assert "compte_rendu" not in entry


async def test_list_pvs_filters_by_call_type(fallback_store_tmp, tech_pv, commercial_pv):
    await fallback_store.save_pv(tech_pv)
    await fallback_store.save_pv(commercial_pv)

    tech = await fallback_store.list_pvs(call_type="#appel-tech")
    commercial = await fallback_store.list_pvs(call_type="#appel-commercial")
    assert len(tech) == 1
    assert len(commercial) == 1
    assert tech[0]["pv_id"] == "pv-tech-1"


async def test_get_todos_across_pvs(fallback_store_tmp, tech_pv):
    await fallback_store.save_pv(tech_pv)
    todos = await fallback_store.get_todos()
    assert len(todos) == 2
    assert {t["title"] for t in todos} == {
        "Créer l'environnement dev sur GitLab",
        "Implémenter le endpoint POST /api/crm/tasks",
    }


async def test_get_todos_filters_by_pv_id(fallback_store_tmp, tech_pv, commercial_pv):
    await fallback_store.save_pv(tech_pv)
    await fallback_store.save_pv(commercial_pv)

    todos = await fallback_store.get_todos(pv_id="pv-tech-1")
    assert len(todos) == 2
    assert all(t["pv_id"] == "pv-tech-1" for t in todos)


async def test_clear_store(fallback_store_tmp, tech_pv, commercial_pv):
    await fallback_store.save_pv(tech_pv)
    await fallback_store.save_pv(commercial_pv)

    assert await fallback_store.clear_store() == 2
    assert await fallback_store.list_pvs() == []
