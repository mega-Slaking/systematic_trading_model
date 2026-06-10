"""Service layer: orchestration that calls the existing ``src/`` core and shapes
the result into response schemas (spec §3.1). No trading/analytics math lives
here -- anything numeric that doesn't already exist in ``src/`` goes into the one
``summaries.py`` helper.
"""
