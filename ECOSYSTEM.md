# Hyperobjects Spec in the MADFAM ecosystem

Last Updated: 2026-09-28

Owns shared solid/soft hyperobject schemas, validators and conformance tooling. It is the common contract between platforms and cartridge repositories. Platform UI, production service credentials and authored cartridges remain in their owning repositories.

Start with [README.md](./README.md) and [AGENTS.md](./AGENTS.md). Follow the
[public repository boundary](./docs/PUBLIC_REPO_BOUNDARY.md) when updating
interfaces or recording evidence. Changes to shared contracts belong in
hyperobjects-spec; consumers advance explicit pins after the relevant checks
pass. Do not copy platform implementation into the commons or move product
application code into operational documentation.

Enclii provides deployment and observability; Janua owns identity and
entitlements. This repository must not create an independent identity authority
or contain deployment credentials. Report verified capabilities separately from
experimental paths and missing external prerequisites.
