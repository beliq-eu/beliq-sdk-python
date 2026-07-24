from beliq import LIVE_GENERATE_PRESETS, LIVE_GENERATE_STANDARDS


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
