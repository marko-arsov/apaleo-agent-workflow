# Architecture (apaleo) + Graphify

Modular monolith (.NET 10): `Apaleo.Api` host → domain projects → `Core` / `Contracts` / `Data` / `Common`. Autofac `[AutoWire]` services; **no MediatR**. Entities in `Apaleo.Data`. Controllers + URL versioning (`v1`, unstable `v0-nsfw`). Errors: typed exceptions → `MessageItemCollection`. Defer detail to `clean-code` and `apaleo/AGENTS.md`.

Conventions that agents get wrong live as one-liners in `$ROOT/AGENTS.md` (with pointers). Do not duplicate them here.

## Graphify

The `apaleo` repo ships Graphify (`pip install graphifyy` → CLI `graphify`). CI commits `src/graphify-out/` + `test/graphify-out/`; merge locally with `./merge-graphify.sh` → `graphify-out/graph.json`.

Pipeline skills should **query the graph before broad grep** when researching apaleo code (`graphify query|path|explain`). Details: `graphify.md`. `development/` has no graph.
