---
name: performance-review
description: Performance auditing and latency/memory optimization based on empirical benchmark evidence.
---

# Performance Review Skill

Use this skill to identify, measure, and resolve performance bottlenecks across software components.

## Mandatory Rule
**PREFER MEASURED EVIDENCE OVER ASSUMPTIONS.**
Measure execution time (ms/sec) and memory footprint before and after any performance optimization.

## Performance Checklist

1. **Algorithmic Efficiency**: Locate $O(N^2)$ nested loops and convert to hash sets/dictionaries or vectorized operations (`NumPy`/`Pandas`).
2. **Database Query Profiling**: Detect N+1 query patterns, missing index scans, and redundant fetches.
3. **Caching Strategy**: Verify hit rates for in-memory and disk caches (`data/` cache directory).
4. **Network & Payload Footprint**: Check REST API response sizes, compression, and unnecessary polling loops.
5. **Memory & Concurrency**: Audit memory allocation, unclosed buffers, and blocking operations on main event loops.
