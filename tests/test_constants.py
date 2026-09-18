import pytest

from beliq import (
    LIVE_GENERATE_PRESETS,
    LIVE_GENERATE_STANDARDS,
    LIVE_PROFILES_BY_STANDARD,
    is_profile_allowed_for_standard,
    profiles_for_standard,
)


def test_presets_list_the_public_generate_targets():
    assert [p.id for p in LIVE_GENERATE_PRESETS] == [
        "xrechnung",
        "factur-x",
        "zugferd",
        "peppol-bis",
        "nlcius",
    ]


def test_nlcius_is_a_peppol_bis_profile_not_a_standalone_standard():
    nlcius = next(p for p in LIVE_GENERATE_PRESETS if p.id == "nlcius")
    assert nlcius.standard == "peppol-bis"
    assert nlcius.profile == "netherlands-nlcius"
    assert nlcius.output == "xml"
    # It is a profile, so it must not have leaked into the standards list.
    assert "nlcius" not in LIVE_GENERATE_STANDARDS


def test_facturx_preset_carries_the_canonical_profile():
    facturx = next(p for p in LIVE_GENERATE_PRESETS if p.id == "factur-x")
    assert facturx.standard == "facturx"
    assert facturx.output == "pdf"
    assert facturx.facturx_profile == "en16931"


def test_every_preset_maps_to_a_known_live_standard():
    for preset in LIVE_GENERATE_PRESETS:
        assert preset.standard in LIVE_GENERATE_STANDARDS


def test_profile_table_covers_exactly_the_live_generate_standards():
    assert sorted(LIVE_PROFILES_BY_STANDARD) == sorted(LIVE_GENERATE_STANDARDS)


def test_profile_table_leaves_no_standard_without_a_reachable_profile():
    for standard, profiles in LIVE_PROFILES_BY_STANDARD.items():
        assert profiles, standard


@pytest.mark.parametrize("profile", ["basicwl", "en16931", "extended", "extended-ctc-fr"])
def test_factur_x_granularity_profiles_are_withheld_from_xrechnung_and_peppol_bis(profile):
    # The pair that shipped broken: every one of these is a 422 on those two
    # standards, so a flat profile dropdown offers four unreachable values.
    assert not is_profile_allowed_for_standard("xrechnung", profile)
    assert not is_profile_allowed_for_standard("peppol-bis", profile)


def test_extended_ctc_fr_is_factur_x_only():
    # extended-ctc-fr is the AFNOR XP Z12-012 France CTC overlay; ZUGFeRD is the
    # German packaging of the same CII document and has no counterpart for it.
    assert not is_profile_allowed_for_standard("zugferd", "extended-ctc-fr")
    assert is_profile_allowed_for_standard("facturx", "extended-ctc-fr")


def test_every_preset_profile_is_legal_for_the_standard_it_targets():
    for preset in LIVE_GENERATE_PRESETS:
        for profile in (preset.profile, preset.facturx_profile):
            if profile is not None:
                assert is_profile_allowed_for_standard(preset.standard, profile), (
                    f"{preset.id}: {preset.standard} + {profile}"
                )


def test_an_unknown_standard_defers_to_the_api():
    assert profiles_for_standard("fatturapa") == ()
    assert is_profile_allowed_for_standard("fatturapa", "ordinaria")


def test_profile_table_cannot_be_mutated_by_a_caller():
    with pytest.raises(TypeError):
        LIVE_PROFILES_BY_STANDARD["xrechnung"] = ("en16931",)  # type: ignore[index]
