#!/bin/bash
# MeshNet VPN - Script di avvio principale
# Questo script verifica la disponibilità di Docker, installa una versione portable se necessario
# e avvia i componenti di MeshNet VPN.

set -e  # Termina lo script in caso di errori

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Color

# Variabili
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PODMAN_DIR="$SCRIPT_DIR/tools/podman"
PODMAN_VERSION="v4.5.0"  # Versione di Podman da scaricare
PODMAN_MACHINE_NAME="meshnet"
PODMAN_MACHINE_CREATED=false
MAX_RETRIES=3

# Log funzioni
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Banner
show_banner() {
    echo -e "${BLUE}"
    echo "=================================================="
    echo "            MeshNet VPN - Avvio Sistema           "
    echo "=================================================="
    echo -e "${NC}"
}

# Verifica requisiti
check_requirements() {
    log_info "Verifico requisiti di sistema..."
    
    # Verifica sistema operativo
    PLATFORM="$(uname -s)"
    if [[ "$PLATFORM" == "Darwin" ]]; then
        log_info "Sistema operativo: macOS"
        OS_TYPE="macos"
    elif [[ "$PLATFORM" == "Linux" ]]; then
        log_info "Sistema operativo: Linux"
        OS_TYPE="linux"
    else
        log_error "Sistema operativo non supportato: $PLATFORM"
        exit 1
    fi
    
    # Verifica Python
    if command -v python3 &>/dev/null; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        log_success "Python trovato: $PYTHON_VERSION"
    else
        log_error "Python 3 non trovato. Installa Python 3.8 o superiore."
        exit 1
    fi
}

# Controlla se Docker o Podman è disponibile
check_docker() {
    log_info "Verifico se Docker è installato..."
    
    if command -v docker &>/dev/null && docker info &>/dev/null; then
        log_success "Docker trovato e funzionante"
        DOCKER_CMD="docker"
        COMPOSE_CMD="docker-compose"
        USING_PODMAN=false
        return 0
    fi
    
    log_warning "Docker non trovato o non funzionante."
    
    # Controlla se Podman è installato
    if command -v podman &>/dev/null; then
        log_success "Podman trovato, userò questo al posto di Docker"
        setup_podman
        return 0
    fi
    
    log_warning "Podman non trovato. Scaricherò una versione portable."
    return 1
}

# Configura Podman esistente
setup_podman() {
    DOCKER_CMD="podman"
    COMPOSE_CMD="podman-compose"
    USING_PODMAN=true
    
    # Verifica che podman-compose sia installato
    if ! command -v podman-compose &>/dev/null; then
        log_info "Installazione di podman-compose..."
        pip3 install podman-compose
    fi
    
    # Verifica che la macchina Podman sia attiva
    ensure_podman_machine_running
}

# Assicura che la macchina Podman sia in esecuzione
ensure_podman_machine_running() {
    if [[ "$OS_TYPE" != "macos" ]]; then
        # Su Linux non serve la macchina
        return 0
    fi
    
    log_info "Verifico stato macchina virtuale Podman..."
    
    # Controlla se la macchina esiste
    if podman machine list 2>/dev/null | grep -q "$PODMAN_MACHINE_NAME"; then
        log_info "Macchina '$PODMAN_MACHINE_NAME' trovata."
        
        # Controlla se è in esecuzione
        if podman machine list | grep "$PODMAN_MACHINE_NAME" | grep -q "Running"; then
            log_success "Macchina '$PODMAN_MACHINE_NAME' già in esecuzione."
            return 0
        else
            log_info "Avvio della macchina '$PODMAN_MACHINE_NAME'..."
            podman machine start "$PODMAN_MACHINE_NAME"
            
            # Attendi che la macchina sia pronta
            for i in {1..30}; do
                if podman machine list | grep "$PODMAN_MACHINE_NAME" | grep -q "Running"; then
                    log_success "Macchina '$PODMAN_MACHINE_NAME' avviata con successo."
                    # Attendi qualche secondo per essere sicuri che il socket sia disponibile
                    sleep 5
                    return 0
                fi
                sleep 1
            done
            
            log_error "Timeout durante l'avvio della macchina '$PODMAN_MACHINE_NAME'."
            return 1
        fi
    else
        log_info "Inizializzazione macchina '$PODMAN_MACHINE_NAME'..."
        podman machine init --cpus 2 --memory 2048 --disk-size 20 "$PODMAN_MACHINE_NAME"
        PODMAN_MACHINE_CREATED=true
        
        log_info "Avvio macchina '$PODMAN_MACHINE_NAME'..."
        podman machine start "$PODMAN_MACHINE_NAME"
        
        # Attendi che la macchina sia pronta
        for i in {1..30}; do
            if podman machine list | grep "$PODMAN_MACHINE_NAME" | grep -q "Running"; then
                log_success "Macchina '$PODMAN_MACHINE_NAME' inizializzata e avviata con successo."
                # Attendi qualche secondo per essere sicuri che il socket sia disponibile
                sleep 5
                return 0
            fi
            sleep 1
        done
        
        log_error "Timeout durante l'inizializzazione della macchina '$PODMAN_MACHINE_NAME'."
        return 1
    fi
}

# Scarica e configura Podman portable
download_podman_portable() {
    log_info "Scarico Podman portable..."
    
    mkdir -p "$PODMAN_DIR"
    
    if [[ "$OS_TYPE" == "macos" ]]; then
        # Su macOS, installiamo podman usando Homebrew
        if ! command -v brew &>/dev/null; then
            log_info "Installo Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        
        log_info "Installo Podman con Homebrew..."
        brew install podman
        
        # Installa podman-compose
        log_info "Installo podman-compose..."
        pip3 install podman-compose
        
        DOCKER_CMD="podman"
        COMPOSE_CMD="podman-compose"
        USING_PODMAN=true
        
        # Inizializza e avvia la macchina Podman
        ensure_podman_machine_running
        
    elif [[ "$OS_TYPE" == "linux" ]]; then
        # Su Linux, scarichiamo il binario di podman
        PODMAN_URL="https://github.com/containers/podman/releases/download/$PODMAN_VERSION/podman-$PODMAN_VERSION-linux-amd64.tar.gz"
        log_info "Scarico Podman da $PODMAN_URL..."
        
        curl -L "$PODMAN_URL" -o "$PODMAN_DIR/podman.tar.gz"
        tar -xzf "$PODMAN_DIR/podman.tar.gz" -C "$PODMAN_DIR"
        rm "$PODMAN_DIR/podman.tar.gz"
        
        # Trova il percorso esatto del binario
        PODMAN_BIN=$(find "$PODMAN_DIR" -name "podman" -type f -executable | head -n 1)
        
        if [[ -z "$PODMAN_BIN" ]]; then
            log_error "Non è stato possibile trovare il binario di Podman"
            exit 1
        fi
        
        # Installa podman-compose
        log_info "Installo podman-compose..."
        pip3 install podman-compose
        
        DOCKER_CMD="$PODMAN_BIN"
        COMPOSE_CMD="podman-compose"
        USING_PODMAN=true
    else
        log_error "Sistema operativo non supportato per Podman portable"
        exit 1
    fi
    
    log_success "Podman configurato correttamente"
}

# Configura Podman come Docker
setup_podman_as_docker() {
    # Crea alias per Docker
    mkdir -p "$SCRIPT_DIR/tools/bin"
    ln -sf "$(which $DOCKER_CMD)" "$SCRIPT_DIR/tools/bin/docker"
    
    # Aggiungi il percorso al PATH
    export PATH="$SCRIPT_DIR/tools/bin:$PATH"
}

# Controlla e verifica che Docker/Podman funzioni correttamente
verify_container_engine() {
    log_info "Verifico che il container engine funzioni correttamente..."
    
    local retry_count=0
    while [ $retry_count -lt $MAX_RETRIES ]; do
        if [[ "$USING_PODMAN" == true ]]; then
            if podman ps &>/dev/null; then
                log_success "Podman funziona correttamente"
                return 0
            else
                retry_count=$((retry_count + 1))
                log_warning "Podman non risponde, tentativo $retry_count di $MAX_RETRIES"
                
                if [[ "$OS_TYPE" == "macos" ]]; then
                    log_info "Riavvio la macchina Podman..."
                    podman machine stop "$PODMAN_MACHINE_NAME" &>/dev/null || true
                    sleep 2
                    ensure_podman_machine_running
                fi
                
                sleep 5
            fi
        else
            if docker ps &>/dev/null; then
                log_success "Docker funziona correttamente"
                return 0
            else
                retry_count=$((retry_count + 1))
                log_warning "Docker non risponde, tentativo $retry_count di $MAX_RETRIES"
                sleep 5
            fi
        fi
    done
    
    log_error "Container engine non funzionante dopo $MAX_RETRIES tentativi"
    return 1
}

# Avvia il server di discovery
start_discovery_server() {
    log_info "Avvio del server di discovery..."
    
    # Verifica che il container engine funzioni
    verify_container_engine
    
    # Controlla se docker-compose.yml esiste
    if [ ! -f "$SCRIPT_DIR/docker-compose.yml" ]; then
        log_error "File docker-compose.yml non trovato in $SCRIPT_DIR"
        log_info "Creo un file docker-compose.yml di base..."
        
        # Crea un docker-compose.yml di base
        cat > "$SCRIPT_DIR/docker-compose.yml" << EOL
version: '3'

services:
  # Server di discovery
  discovery:
    build:
      context: .
      dockerfile: docker/Dockerfile.discovery
    ports:
      - "8000:8000/udp"
    environment:
      - BIND=0.0.0.0
      - PORT=8000
    restart: unless-stopped
    networks:
      - meshnet

networks:
  meshnet:
    driver: bridge
EOL
        
        log_info "File docker-compose.yml creato"
    fi
    
    # Controlla se Dockerfile.discovery esiste
    if [ ! -f "$SCRIPT_DIR/docker/Dockerfile.discovery" ]; then
        log_info "Creo cartella docker/ se non esiste..."
        mkdir -p "$SCRIPT_DIR/docker"
        
        log_info "Creo Dockerfile.discovery di base..."
        
        # Crea un Dockerfile.discovery di base
        cat > "$SCRIPT_DIR/docker/Dockerfile.discovery" << EOL
FROM python:3.9-slim

WORKDIR /app

# Copia solo i file necessari
COPY meshnet/discovery/discovery_server.py meshnet/discovery/
COPY meshnet/discovery/__init__.py meshnet/discovery/
COPY meshnet/discovery/mesh_node.py meshnet/discovery/
COPY meshnet/discovery/stun_client.py meshnet/discovery/

# Installa le dipendenze
RUN pip install --no-cache-dir pynacl flask cryptography

# Argomenti predefiniti
ENV PORT=8000
ENV BIND=0.0.0.0

# Esponi la porta
EXPOSE \$PORT/udp

# Comando di avvio
CMD ["sh", "-c", "python -u meshnet/discovery/discovery_server.py --port \$PORT --bind \$BIND"]
EOL
        
        log_info "Dockerfile.discovery creato"
    fi
    
    # Avvia il server con gestione degli errori
    retry_count=0
    while [ $retry_count -lt $MAX_RETRIES ]; do
        log_info "Tentativo di avvio del server di discovery: $((retry_count + 1)) di $MAX_RETRIES"
        
        if [[ "$USING_PODMAN" == true ]]; then
            log_info "Utilizzo Podman per avviare il server..."
            set +e  # Disabilita temporaneamente set -e
            $COMPOSE_CMD up -d discovery
            local result=$?
            set -e  # Riabilita set -e
        else
            log_info "Utilizzo Docker per avviare il server..."
            set +e  # Disabilita temporaneamente set -e
            $COMPOSE_CMD up -d discovery
            local result=$?
            set -e  # Riabilita set -e
        fi
        
        if [ $result -eq 0 ]; then
            log_success "Server di discovery avviato con successo"
            return 0
        else
            retry_count=$((retry_count + 1))
            log_warning "Errore durante l'avvio del server di discovery, riprovo..."
            
            if [[ "$USING_PODMAN" == true && "$OS_TYPE" == "macos" ]]; then
                log_info "Riavvio la macchina Podman..."
                podman machine stop "$PODMAN_MACHINE_NAME" &>/dev/null || true
                sleep 2
                ensure_podman_machine_running
            fi
            
            sleep 5
        fi
    done
    
    log_error "Impossibile avviare il server di discovery dopo $MAX_RETRIES tentativi"
    return 1
}

# Avvia il nodo VPN
start_vpn_node() {
    log_info "Avvio del nodo VPN..."
    
    # Il nodo VPN richiede accesso al sistema, quindi non lo eseguiamo in Docker/Podman
    chmod +x "$SCRIPT_DIR/run_vpn_node.sh"
    
    SERVER_ADDR="127.0.0.1:8000"
    NODE_ID="local_node"
    
    # Chiedi dettagli all'utente
    read -p "Indirizzo del server di discovery [$SERVER_ADDR]: " input
    SERVER_ADDR=${input:-$SERVER_ADDR}
    
    read -p "ID del nodo [$NODE_ID]: " input
    NODE_ID=${input:-$NODE_ID}
    
    log_info "Avvio nodo VPN con ID $NODE_ID connesso a $SERVER_ADDR..."
    
    if [[ "$OS_TYPE" == "macos" || "$OS_TYPE" == "linux" ]]; then
        sudo "$SCRIPT_DIR/run_vpn_node.sh" --server "$SERVER_ADDR" --id "$NODE_ID"
    else
        log_error "Sistema operativo non supportato per il nodo VPN"
        exit 1
    fi
}

# Menu principale
show_menu() {
    clear
    show_banner
    
    echo "Menu:"
    echo "1. Avvia server di discovery"
    echo "2. Avvia nodo VPN"
    echo "3. Avvia entrambi (server + nodo)"
    echo "4. Verifica stato"
    echo "5. Arresta tutti i servizi"
    echo "6. Riavvia container engine"
    echo "0. Esci"
    echo ""
    read -p "Scegli un'opzione: " choice
    
    case $choice in
        1)
            start_discovery_server
            ;;
        2)
            start_vpn_node
            ;;
        3)
            start_discovery_server
            start_vpn_node
            ;;
        4)
            if [[ "$USING_PODMAN" == true ]]; then
                $DOCKER_CMD ps
                
                if [[ "$OS_TYPE" == "macos" ]]; then
                    echo
                    echo "Stato macchina Podman:"
                    podman machine list
                fi
            else
                $DOCKER_CMD ps
            fi
            ;;
        5)
            log_info "Arresto dei servizi..."
            if [[ "$USING_PODMAN" == true ]]; then
                set +e  # Disabilita temporaneamente set -e
                $COMPOSE_CMD down
                set -e  # Riabilita set -e
                
                if [[ "$PODMAN_MACHINE_CREATED" == true && "$OS_TYPE" == "macos" ]]; then
                    podman machine stop "$PODMAN_MACHINE_NAME" || true
                fi
            else
                set +e  # Disabilita temporaneamente set -e
                $COMPOSE_CMD down
                set -e  # Riabilita set -e
            fi
            log_success "Servizi arrestati"
            ;;
        6)
            log_info "Riavvio del container engine..."
            if [[ "$USING_PODMAN" == true && "$OS_TYPE" == "macos" ]]; then
                podman machine stop "$PODMAN_MACHINE_NAME" || true
                sleep 2
                ensure_podman_machine_running
                log_success "Podman riavviato"
            else
                log_warning "Riavvio automatico supportato solo per Podman su macOS."
                log_info "Riavvia Docker manualmente, se necessario."
            fi
            ;;
        0)
            log_info "Uscita..."
            exit 0
            ;;
        *)
            log_error "Opzione non valida"
            ;;
    esac
    
    read -p "Premi Invio per continuare..."
    show_menu
}

# Pulizia all'uscita
cleanup() {
    log_info "Pulizia in corso..."
    
    if [[ "$PODMAN_MACHINE_CREATED" == true && "$OS_TYPE" == "macos" ]]; then
        log_info "Arresto della macchina Podman..."
        podman machine stop "$PODMAN_MACHINE_NAME" || true
    fi
}

# Aggiungi gestione per SIGINT e SIGTERM
trap cleanup EXIT INT TERM

# Esecuzione principale
main() {
    show_banner
    check_requirements
    
    # Controlla Docker/Podman
    if ! check_docker; then
        download_podman_portable
    fi
    
    # Configura Podman come Docker se necessario
    if [[ "$USING_PODMAN" == true ]]; then
        setup_podman_as_docker
    fi
    
    # Mostra il menu
    show_menu
}

# Avvio script
main 