#!/bin/bash
# Fix ownership of volumes that Docker creates as root
for dir in /stk-data /imports /imports/processed /imports/failed /downloads /library /library/kindle; do
    if [ -d "$dir" ]; then
        chown -R appuser:appuser "$dir" 2>/dev/null || true
    else
        mkdir -p "$dir" && chown appuser:appuser "$dir" 2>/dev/null || true
    fi
done

exec gosu appuser bash start.sh
