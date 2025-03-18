#!/bin/bash
# Avvia un nodo VPN mesh

# Controlla se lo script è eseguito come root (necessario per interfacce TUN/TAP)
if [ "$(id -u)" -ne 0 ]; then
    echo "Sono richiesti privilegi di amministratore per creare interfacce TUN/TAP."
    echo "Eseguo nuovamente lo script con sudo..."
    exec sudo "$0" "$@"
    exit $?
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
    echo "  --key KEY            Chiave di crittografia (hex, generata automaticamente se non specificata)"
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

# Trova l'interprete Python
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "Errore: Python non trovato. Installa Python 3."
    exit 1
fi

# Genera chiave se non specificata
if [ -z "$KEY" ]; then
    echo "Nessuna chiave specificata, genero una chiave casuale..."
    if ! command -v $PYTHON >/dev/null 2>&1; then
        echo "Errore: Python è richiesto per generare la chiave"
        exit 1
    fi
    
    # Verifica se PyNaCl è installato
    if ! $PYTHON -c "import nacl.utils" >/dev/null 2>&1; then
        echo "Errore: PyNaCl è richiesto per generare la chiave"
        echo "Installa con: pip install pynacl"
        exit 1
    fi
    
    # Genera chiave con Python e nacl
    KEY=$($PYTHON -c "import nacl.utils, binascii; print(binascii.hexlify(nacl.utils.random(32)).decode())")
    echo "Chiave generata: $KEY"
fi

# Prepara il comando
CMD="$PYTHON meshnet/core/vpn_node.py --server $SERVER"

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

CMD="$CMD --key $KEY"

echo "Avvio nodo VPN mesh..."
echo "Server di scoperta: $SERVER"
if [ ! -z "$ID" ]; then
    echo "ID nodo: $ID"
fi
echo "Rete: $NETWORK"
echo "Usando interprete Python: $PYTHON"
echo "Chiave: $KEY"

echo "Esecuzione: $CMD"
$CMD 