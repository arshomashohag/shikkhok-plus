"""City areas in the area picker and in an owner's listing.

A district's children are its upazilas followed by its city corporations,
and a listing's ``upazila_code`` may name a metropolitan thana whose city
corporation lies in the listing's district.
"""

from __future__ import annotations

from typing import Final

import pytest
from sqlalchemy.orm import Session

from app.errors import ValidationError
from app.hub import areas
from app.hub.listings import owner
from app.hub.listings.owner import OwnerListingUpdate
from tests.hub.support import solo_lens

#: Dhaka district, and Chattogram as a district Mirpur is not in.
DHAKA: Final[str] = "BD3026"
CHATTOGRAM: Final[str] = "BD2015"

#: Dhaka North City Corporation and its Mirpur thana.
DNCC: Final[str] = "BD30262500"
MIRPUR: Final[str] = "MT3026250003"


def test_a_districts_children_are_upazilas_then_city_corporations(
    restricted_session: Session,
) -> None:
    """Dhaka lists its five upazilas by name, then its two city corporations.

    :param restricted_session: The application role's session
    :return: None
    """
    found = areas.children(restricted_session, DHAKA)

    kinds = [a.kind for a in found]
    assert kinds == ["upazila"] * 5 + ["city_corporation"] * 2
    upazilas = [a.name_en for a in found if a.kind == "upazila"]
    assert upazilas == sorted(upazilas)
    assert [a.name_en for a in found[5:]] == [
        "Dhaka North City Corporation",
        "Dhaka South City Corporation",
    ]


def test_a_city_corporations_children_are_its_metro_thanas(
    restricted_session: Session,
) -> None:
    """Dhaka North lists its thanas, Mirpur among them, with Bangla names.

    :param restricted_session: The application role's session
    :return: None
    """
    found = areas.children(restricted_session, DNCC)

    assert {a.kind for a in found} == {"metro_thana"}
    mirpur = next(a for a in found if a.code == MIRPUR)
    assert (mirpur.name_en, mirpur.name_bn) == ("Mirpur", "মিরপুর")


def test_no_parent_lists_the_divisions_and_unknown_lists_nothing(
    restricted_session: Session,
) -> None:
    """The top level is unchanged; an unknown code has no children.

    :param restricted_session: The application role's session
    :return: None
    """
    assert {a.kind for a in areas.children(restricted_session, None)} == {"division"}
    assert len(areas.children(restricted_session, None)) == 8
    assert areas.children(restricted_session, "BD0000") == []


def test_listing_accepts_metro_thana_under_its_district(
    owner_session: Session, restricted_session: Session
) -> None:
    """Dhaka with Mirpur is a valid, nested area.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    owner.get_or_draft(restricted_session, lens)

    listing = owner.update(
        restricted_session,
        lens,
        OwnerListingUpdate(district_code=DHAKA, upazila_code=MIRPUR),
    )

    assert (listing.district_code, listing.upazila_code) == (DHAKA, MIRPUR)


def test_listing_accepts_city_corporation_under_its_district(
    owner_session: Session, restricted_session: Session
) -> None:
    """Dhaka with Dhaka North is valid: a thana is optional below a city.

    An owner whose thana is not in the vocabulary stops at the city
    corporation, which then sits in the upazila slot.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :return: None
    """
    lens = solo_lens(owner_session)
    owner.get_or_draft(restricted_session, lens)

    listing = owner.update(
        restricted_session,
        lens,
        OwnerListingUpdate(district_code=DHAKA, upazila_code=DNCC),
    )

    assert (listing.district_code, listing.upazila_code) == (DHAKA, DNCC)


@pytest.mark.parametrize(
    ("district", "upazila"),
    [(CHATTOGRAM, MIRPUR), (CHATTOGRAM, DNCC), (DNCC, MIRPUR)],
    ids=["thana-elsewhere", "city-corporation-elsewhere", "city-as-district"],
)
def test_listing_rejects_metro_thana_from_another_district(
    owner_session: Session,
    restricted_session: Session,
    district: str,
    upazila: str,
) -> None:
    """A thana or city outside the district, or a city as the district, fails.

    :param owner_session: An arranging session
    :param restricted_session: The application role's session
    :param district: The district code sent
    :param upazila: The upazila code sent
    :return: None
    """
    lens = solo_lens(owner_session)
    owner.get_or_draft(restricted_session, lens)

    with pytest.raises(ValidationError) as raised:
        owner.update(
            restricted_session,
            lens,
            OwnerListingUpdate(district_code=district, upazila_code=upazila),
        )
    assert raised.value.code == "HUB_AREA_MISMATCH"
