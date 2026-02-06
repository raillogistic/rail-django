# Table v3 Backend Migration

1. Enable table extension through default schema integration (already wired in `core/schema`).
2. Move frontend consumers to `@/lib/table`.
3. Remove legacy compatibility paths only after import scans reach zero legacy references.

