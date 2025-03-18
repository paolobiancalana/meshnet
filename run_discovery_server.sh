#!/bin/bash
# Avvia il server di scoperta centralizzato

PORT=8000

# Verifica se è stato specificato un numero di porta
if [ $# -eq 1 ]; then
    PORT=$1
fi

echo "Avvio server di scoperta sulla porta $PORT..."
python -m meshnet.discovery.discovery_server --port $PORT 