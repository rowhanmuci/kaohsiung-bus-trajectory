# PostgreSQL 17 + PostGIS 3 (spatial), pgvector (embeddings), pgRouting (road network),
# MobilityDB (moving-object / trajectory types), all from apt.postgresql.org, which the
# official postgres image already has configured. (postgis/postgis:17-3.5 is built on
# Debian bullseye, whose PGDG repository has been archived, so it cannot install extras.)
FROM postgres:17-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      postgresql-17-postgis-3 \
      postgresql-17-postgis-3-scripts \
      postgresql-17-pgvector \
      postgresql-17-pgrouting \
      postgresql-17-mobilitydb \
 && rm -rf /var/lib/apt/lists/*

# Creates the extensions in POSTGRES_DB on first start (empty data volume only).
COPY init/20_extensions.sql /docker-entrypoint-initdb.d/
