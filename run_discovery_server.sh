#!/bin/bash
# Avvia il server di scoperta centralizzato

PORT=8000

# Verifica se è stato specificato un numero di porta
if [ $# -eq 1 ]; then
    PORT=$1
fi

# Trova l'interprete Python
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "Errore: Python non trovato. Installa Python 3."
    exit 1
fi

echo "Avvio server di scoperta sulla porta $PORT..."
echo "Usando interprete Python: $PYTHON"

# Esegui direttamente il file invece del modulo
$PYTHON meshnet/discovery/discovery_server.py --port $PORT 