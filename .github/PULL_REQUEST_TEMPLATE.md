## Description

Please include a summary of the change and which issue it fixes.

Fixes # (issue)

## Type of change

- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (requires existing users to update)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)

## How has this been tested?

```bash
# Run the test command
cd reference-runtime && python -m pytest tests/ -q
```

- [ ] All existing tests pass
- [ ] New tests added for the change

## Checklist

- [ ] Code follows the project's code style (`from __future__ import annotations`, `dataclass`, type hints)
- [ ] CLI commands follow the existing pattern (lazy imports, `sys.exit(1)` on error)
- [ ] Tests follow the project's naming convention (`class TestComponent`, `def test_scenario`)
- [ ] If adding a new Spec, it follows SPEC-NNNN naming and includes validation rules
- [ ] If adding a new Adapter, it inherits `AdapterBase` and implements all required methods

## Additional context

Add any other context about the PR here.
