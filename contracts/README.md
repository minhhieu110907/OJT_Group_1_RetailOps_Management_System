# Contract artifacts

- `openapi.yaml`: HTTP, `x-contract-status=FROZEN_DESIGN` for core S2 write flows; other operations remain proposed.
- `python/retailops_core_ports.pyi`: Python signatures (typing-only, NOT executable application code).
- `examples/*.json`: illustrative shape-consistent fixtures for FE mock & BE tests (not live records).

Verify using `python scripts/check_contract_package.py` from package root. This checks YAML parse, refs, frozen operations, fixtures, and cards; **does not replace running the FastAPI app, MySQL integration tests, or browser E2E**.
