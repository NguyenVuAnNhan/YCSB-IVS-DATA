#!/bin/bash
set -euo pipefail

APOC_URL="https://github.com/neo4j/apoc/releases/latest/download/apoc.jar"

INSTANCES=(
  /opt/neo4j-instance-main
  /opt/neo4j-instance-unchange
  /opt/neo4j-instance-backup
)

echo "Installing APOC plugin..."

for DIR in "${INSTANCES[@]}"; do
    echo "Processing $DIR"

    sudo mkdir -p "$DIR/plugins"
    sudo wget -q "$APOC_URL" -O "$DIR/plugins/apoc.jar"

    CONF="$DIR/conf/neo4j.conf"

    if ! sudo grep -Fq 'dbms.security.procedures.unrestricted=apoc.*' "$CONF"; then
        echo 'dbms.security.procedures.unrestricted=apoc.*' | sudo tee -a "$CONF" >/dev/null
    fi

    if ! sudo grep -Fq 'dbms.security.procedures.allowlist=apoc.*' "$CONF"; then
        echo 'dbms.security.procedures.allowlist=apoc.*' | sudo tee -a "$CONF" >/dev/null
    fi

    echo "APOC installed for $DIR"
done

echo "Killing Neo4j processes..."
sudo pkill -f org.neo4j.server.CommunityEntryPoint || true

echo "Starting Neo4j instances..."
for DIR in "${INSTANCES[@]}"; do
    if [ -x "$DIR/bin/neo4j" ]; then
        sudo "$DIR/bin/neo4j" start
    else
        echo "WARNING: $DIR/bin/neo4j not found or not executable"
    fi
done

echo "Done."
