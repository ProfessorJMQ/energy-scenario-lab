# Verification and reproducibility

Run `python -m unittest discover -s tests -v` from the repository root after installing the package.

The test suite covers:

- A hand-calculated grid energy and demand bill.
- A two-step charge/discharge case with separately known losses.
- Critical-load accounting during an outage.
- Priority shedding during an online grid-capacity shortfall.
- AC energy balance, storage bounds, no simultaneous charge/discharge, and cumulative battery loss accounting over 36 strategy/seed combinations.
- Equal EV energy when moving charging between time windows.
- Invalid assets, profiles, and outage intervals.

The default example and 60-case sweep run in CI in addition to the assertions. Floating-point comparisons use tolerances; random seeds are fixed. Regenerate committed figures using `energy-lab --output examples/demo --sweep`. NumPy or plotting-version changes can alter image bytes without changing the model.

These checks verify internal consistency and selected analytical cases. They do not establish field accuracy, engineering suitability, or the validity of omitted phenomena. A future benchmark should use an independently implemented model and documented public data.
