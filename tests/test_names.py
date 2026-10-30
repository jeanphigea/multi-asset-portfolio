"""Company identity (spec/02-names.md). The JS companyKey must give the same keys."""
import pytest

from names import canonical_company_name, company_key, display_name

CASES = [
    ("Samsung Electronics Co., Ltd.", "Samsung Electronics", "samsung electronics"),
    ("Samsung Electronics Co Ltd (2)", "Samsung Electronics (2)", "samsung electronics"),
    ("Gold (Physical)", "Gold (Physical)", "gold"),
    ("L'Oréal SA", "L'Oréal SA", "l'oreal"),
    ("Amazon.com Inc", "Amazon.com", "amazon"),
    ("Advanced Micro Devices Inc", "Advanced Micro Devices", "amd"),
    ("US TREASURY 3.15% 2031", "US Treasury 3.15% 2031", "us treasury 3.15% 2031"),
    ("Microsoft Corp", "Microsoft", "microsoft"),
    ("ALPHABET INC-CL C", "Alphabet", "alphabet cl"),     # why broker names are canonicalised first
]


@pytest.mark.parametrize("raw,name,key", CASES)
def test_worked_examples(raw, name, key):
    assert canonical_company_name(raw) == name
    assert company_key(raw) == key


def test_share_classes_merge():
    assert company_key("Alphabet Inc A") == company_key("Alphabet Inc C") == "alphabet"


def test_display_name_keeps_counter_and_bonds():
    assert display_name("Samsung Electronics Co Ltd (2)") == "Samsung Electronics (2)"
    assert display_name("US TREASURY 3.15% 2031") == "US TREASURY 3.15% 2031"


def test_isin_override():
    assert canonical_company_name("ALPHABET INC-CL C", "US02079K1079") == "Alphabet"
