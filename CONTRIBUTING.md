# Contributing

- Never add code that writes inside /data/openpilot (the only exception is the opt-in patch in patches/).
- Safety guard changes must keep: 20 km/h hard cap, standstill, fail-safe on stale/missing data, block when onroad/engaged, re-check before shutdown. The touch device must never be grabbed (EVIOCGRAB).
- Run before a PR: `bash -n *.sh bin/cwr && shellcheck *.sh bin/cwr && python3 -m unittest discover -s tests -t .`
- Hardware test reports (device, AGNOS version, sunnypilot branch, results) are very welcome as issues.
