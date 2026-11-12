from importlib.metadata import version

import datapatchbay


def test_version_matches_installed_metadata():
    assert datapatchbay.__version__ == version("datapatchbay")
