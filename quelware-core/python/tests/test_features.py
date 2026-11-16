from quelware_core.features import known


def test_known_keeps_the_names_this_package_knows_and_drops_the_rest():
    assert known(["dense_waveform", "from_a_newer_server"]) == {"dense_waveform"}


def test_known_of_an_empty_list_is_empty():
    assert known([]) == frozenset()
