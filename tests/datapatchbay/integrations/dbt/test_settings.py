import pytest

from datapatchbay.integrations.dbt.settings import dbt_settings


def test_missing_dbt_section_says_what_is_missing():
    with pytest.raises(RuntimeError, match=r"no resolved `dbt:` section"):
        dbt_settings({})
