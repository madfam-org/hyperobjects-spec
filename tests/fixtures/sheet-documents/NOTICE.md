# Sheet-document fixtures

- `valley-fold.fold` is hand-written for the keystone (Apache-2.0). Its
  `pliego:meta.digest` was re-stamped when the digest moved to spec §5.15 (RFC 8785).
- `digest_vector.json` is Pliego's shared spec §5.15 test vector, copied byte for byte
  from [madfam-org/pliego](https://github.com/madfam-org/pliego)
  `packages/kernel/tests/fixtures/digest_vector.json` at `2f85906` (main; last changed in
  `ef377a0`, git blob `c6847785edc8e6ced4bfcd3af2972517f23fef93`). It is a document, its
  canonical text and its digest, cross-checked by Pliego against Node's `JSON.stringify`.
  Authored by Innovaciones MADFAM S.A.S. de C.V., the copyright holder of both repos. Do
  not edit it: re-copy it when Pliego changes it.
- `kernel-0.2/` and `kernel-0.3/` are real kernel output; each has its own NOTICE.
