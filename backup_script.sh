#!/bin/bash
# backup_databases.sh

BACKUP_DIR="/backups/oil_gas_swarm/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# SQLite safe backup (using .backup command)
sqlite3 .cache/swarm_cache.db ".backup '$BACKUP_DIR/swarm_cache.db'"
sqlite3 .cache/swarm_checkpoints.db ".backup '$BACKUP_DIR/swarm_checkpoints.db'"
sqlite3 .cache/analysis_history.db ".backup '$BACKUP_DIR/analysis_history.db'"

# ChromaDB (copy entire directory)
cp -r .cache/rag_risk_db $BACKUP_DIR/

# Compress
tar -czf $BACKUP_DIR.tar.gz $BACKUP_DIR
rm -rf $BACKUP_DIR

# Retain last 30 days
find /backups/oil_gas_swarm -name "*.tar.gz" -mtime +30 -delete