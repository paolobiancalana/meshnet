#!/bin/bash
# Avvia un nodo VPN mesh

# Verifica se l'utente è root (necessario per TUN)
if [ "$EUID" -ne 0 ]; then
  echo "Per favore esegui come root (sudo) per creare l'interfaccia TUN"
  exit 1
fi

# Server di scoperta di default
SERVER="127.0.0.1:8000"

# Leggi parametri da riga di comando
ID=""
PORT="0"
TUN=""
NETWORK="10.0.0.0/24"
KEY=""

# Mostra aiuto
function show_help {
    echo "Utilizzo: $0 [opzioni]"
    echo "Opzioni:"
    echo "  --server HOST:PORT   Server di scoperta (default: 127.0.0.1:8000)"
    echo "  --id ID              ID nodo (default: generato automaticamente)"
    echo "  --port PORT          Porta locale UDP (default: assegnata dal sistema)"
    echo "  --tun ADDRESS        Indirizzo interfaccia TUN (es: 10.0.0.1/24)"
    echo "  --network NETWORK    Rete VPN CIDR (default: 10.0.0.0/24)"
    echo "  --key KEY            Chiave di crittografia (hex)"
    echo "  --help               Mostra questo aiuto"
}

# Elabora parametri da riga di comando
while [ "$1" != "" ]; do
    case $1 in
        --server )      shift
                        SERVER=$1
                        ;;
        --id )          shift
                        ID=$1
                        ;;
        --port )        shift
                        PORT=$1
                        ;;
        --tun )         shift
                        TUN=$1
                        ;;
        --network )     shift
                        NETWORK=$1
                        ;;
        --key )         shift
                        KEY=$1
                        ;;
        --help )        show_help
                        exit
                        ;;
        * )             echo "Opzione sconosciuta: $1"
                        show_help
                        exit 1
    esac
    shift
done

# Determina quale interprete Python usare
if [ -n "$VIRTUAL_ENV" ]; then
    PYTHON="$VIRTUAL_ENV/bin/python"
else
    PYTHON="python3"
fi

# Prepara il comando
CMD="$PYTHON -m meshnet.core.vpn_node --server $SERVER"

# Aggiungi parametri opzionali se specificati
if [ ! -z "$ID" ]; then
    CMD="$CMD --id $ID"
fi

if [ ! -z "$PORT" ]; then
    CMD="$CMD --port $PORT"
fi

if [ ! -z "$TUN" ]; then
    CMD="$CMD --tun $TUN"
fi

if [ ! -z "$NETWORK" ]; then
    CMD="$CMD --network $NETWORK"
fi

if [ ! -z "$KEY" ]; then
    CMD="$CMD --key $KEY"
else
    echo "ATTENZIONE: Chiave di crittografia non specificata. Tutti i nodi della rete devono usare la stessa chiave."
    echo "Usa l'opzione --key o genera una nuova chiave con:"
    echo "$PYTHON -c \"import nacl.secret, nacl.utils; print(nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE).hex())\""
    exit 1
fi

echo "Avvio nodo VPN mesh..."
echo "Server di scoperta: $SERVER"
if [ ! -z "$ID" ]; then
    echo "ID nodo: $ID"
fi
echo "Rete: $NETWORK"

echo "Esecuzione: $CMD"
$CMD 