from collections import Counter
import pytest
from tirage_conditions import CASES_2X2, en_csv, tirer


def test_reproductible_et_equilibre():
    a, b = tirer(8, 42), tirer(8, 42)
    assert a == b and tirer(8, 43) != a
    for bloc in (1, 2):
        cases = {(l["cond_support"], l["cond_provenance"]) for l in a if l["bloc"] == bloc}
        assert cases == set(CASES_2X2)
    assert Counter(l["cond_provenance"] for l in a) == {"affichee": 4, "non_affichee": 4}


def test_sans_support_et_contraintes():
    l = tirer(16, 1, sans_support=True)
    assert Counter(x["cond_provenance"] for x in l) == {"affichee": 8, "non_affichee": 8}
    with pytest.raises(ValueError):
        tirer(6, 1)
    assert en_csv(l).splitlines()[0] == "id_representation;bloc;cond_support;cond_provenance"
