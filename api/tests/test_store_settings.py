import pytest

from tests.conftest import auth_header


def _rename(api, headers, name, address=None):
    return api.patch("/store", json={"name": name, "address": address}, headers=headers)


def _join(api, headers, role):
    invite = {"email": f"{role}@example.com", "role": role}
    token = api.post("/staff/invites", json=invite, headers=headers).json()["token"]
    res = api.post(
        "/staff/invites/accept",
        json={"accept_terms": True, "token": token, "password": "Staff-pass-1"},
    )
    return auth_header(res.json()["access_token"])


def test_a_manager_renames_the_store(api, manager):
    res = _rename(api, manager, "  Hardware Uno  ", "  12 Rizal St  ")
    assert res.status_code == 200
    assert res.json() == {"name": "Hardware Uno", "address": "12 Rizal St"}
    me = api.get("/auth/me", headers=manager).json()
    assert me["store_name"] == "Hardware Uno" and me["store_address"] == "12 Rizal St"


def test_a_blank_address_clears_it(api, manager):
    _rename(api, manager, "Store A", "Somewhere")
    assert _rename(api, manager, "Store A", "   ").json()["address"] is None


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
def test_a_store_needs_a_real_name(api, manager, name):
    assert _rename(api, manager, name).status_code == 422


def test_leaving_out_the_address_does_not_erase_it(api, manager):
    _rename(api, manager, "Store A", "Somewhere")
    assert api.patch("/store", json={"name": "Renamed"}, headers=manager).status_code == 422
    assert api.get("/auth/me", headers=manager).json()["store_address"] == "Somewhere"


def test_an_address_has_a_length_limit(api, manager):
    assert _rename(api, manager, "Store A", "x" * 301).status_code == 422


@pytest.mark.parametrize("role", ["secretary", "member"])
def test_only_managers_rename_the_store(api, manager, role):
    assert _rename(api, _join(api, manager, role), "Mine now").status_code == 403
    assert api.get("/auth/me", headers=manager).json()["store_name"] == "Store A"


def test_renaming_changes_only_your_store(api, manager, signup):
    other = auth_header(signup(email="other@example.com", store_name="Store B")["access_token"])
    _rename(api, manager, "Renamed")
    assert api.get("/auth/me", headers=other).json()["store_name"] == "Store B"


def test_renaming_needs_sign_in(api):
    assert api.patch("/store", json={"name": "Nope", "address": None}).status_code == 401
