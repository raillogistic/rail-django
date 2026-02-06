# Table v3 Performance

- Use `tableBootstrapMinimal` for fast shell rendering.
- Apply stale-while-revalidate cache hints for row reads.
- Track bootstrap/rows latency and cache hit rates.
- Use pagination and virtualized rendering for large datasets.
