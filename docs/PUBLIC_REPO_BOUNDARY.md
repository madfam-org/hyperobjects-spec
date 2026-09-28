# Public repository boundary

Last Updated: 2026-09-28

Owns shared solid/soft hyperobject schemas, validators and conformance tooling. It is the common contract between platforms and cartridge repositories. Platform UI, production service credentials and authored cartridges remain in their owning repositories.

Keep reusable code, public schemas, product documentation and synthetic test
fixtures here. Keep credentials, private customer cartridges, staff identities,
production topology, node identities and raw operational evidence in their
approved private systems. Never embed secret values in source, logs or PRs.

Enclii owns routine deployment, observability and secret intake. Record missing
platform capabilities privately; do not add a raw production-access fallback.
Licensing, governance and access rulings remain with the operator. A test skip or
unavailable dependency is not verification, and a pending CI run is not green.
