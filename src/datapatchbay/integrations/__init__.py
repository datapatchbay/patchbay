"""One folder per integration (ADR-0024): the support for one technology, found through an entry point.

The folders starting with an underscore hold what several integrations share: SQL, generated code and the container
rendering. The core imports nothing from this package; `tests/datapatchbay/test_integration_boundary.py` enforces it.
"""
