#!/bin/bash
# Avvia il server di scoperta centralizzato

PORT=8000

# Verifica se è stato specificato un numero di porta
if [ $# -eq 1 ]; then
    PORT=$1
fi

echo "Avvio server di scoperta sulla porta $PORT..."
# Usa python dall'ambiente virtuale se presente
if [ -n "$VIRTUAL_ENV" ]; then
    "$VIRTUAL_ENV/bin/python" -m meshnet.discovery.discovery_server --port $PORT
else
    python3 -m meshnet.discovery.discovery_server --port $PORT
fi 