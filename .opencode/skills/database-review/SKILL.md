---
name: database-review
description: Database schema, index, query efficiency, migration, and data integrity inspection skill.
---

# Database Review Skill

Use this skill when auditing or optimizing relational and document databases (e.g. SQLite `data/research.db`).

## Mandatory Rule
**NEVER PERFORM DESTRUCTIVE PRODUCTION DATABASE OPERATIONS WITHOUT EXPLICIT APPROVAL.**
Always take database backups (`.db` copies) before running schema alterations or bulk data migrations.

## Database Review Checklist

1. **Schema Integrity**: Inspect tables, columns, primary keys, foreign key constraints, and default values.
2. **Index Optimization**: Identify frequently queried columns (`WHERE`, `JOIN`, `ORDER BY`) lacking indexes.
3. **Query Efficiency**: Audit SQL queries for `SELECT *` overuse, unindexed scans, and inefficient joins.
4. **Transaction & Concurrency Safety**: Verify transaction isolation, write locking, write-ahead logging (WAL mode), and deadlock prevention.
5. **Data Backups & Recovery**: Ensure automated database snapshots and journal backups are active before running schema changes.
