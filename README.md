# MeshNet VPN

Un sistema VPN Mesh P2P opensource, ispirato a ZeroTier ma completamente controllabile e personalizzabile.

## Caratteristiche

- **Rete Mesh P2P**: connessione diretta tra i nodi quando possibile, senza server centrali
- **NAT Traversal**: funziona anche quando i nodi sono dietro firewall o NAT
- **Crittografia End-to-End**: comunicazioni sicure tra tutti i nodi
- **Multi-piattaforma**: supporta macOS, Linux e Windows
- **Interfaccia TUN/TAP**: si integra facilmente con le applicazioni esistenti
- **Orchestratore**: gestione centralizzata dei nodi

## Architettura

Il sistema è composto da:

1. **Server di Discovery**: facilita la ricerca e connessione iniziale tra i nodi
2. **Nodi VPN**: istanze che creano interfacce di rete virtuale e gestiscono il routing
3. **Orchestratore**: strumento opzionale per gestire la rete e i nodi

## Requisiti

### Per macOS

- Python 3.8 o superiore
- Privilegi di amministratore (per creare interfacce TUN)

### Per Windows

- Python 3.8 o superiore
- Driver TAP-Windows (installabile tramite OpenVPN)
- Privilegi di amministratore (per creare interfacce TAP)

## Installazione

### macOS / Linux

```bash
# Clona il repository
git clone https://github.com/tuoutente/meshnet.git
cd meshnet

# Crea e attiva un ambiente virtuale
python3 -m venv venv
source venv/bin/activate

# Installa le dipendenze
pip install pynacl cryptography flask pyroute2 pytest
```

### Windows

```batch
# Clona il repository
git clone https://github.com/tuoutente/meshnet.git
cd meshnet

# Esegui lo script di setup
setup_windows.bat
```

## Utilizzo

### Opzione 1: Orchestratore (Raccomandato)

L'orchestratore è lo strumento più semplice per gestire la rete:

```bash
# Su macOS/Linux
python orchestrator.py

# Su Windows
python orchestrator.py
```

Segui le istruzioni interattive per avviare il server di discovery e i nodi VPN.

### Opzione 2: Script Manuali

#### Avvio del Server di Discovery

```bash
# Su macOS/Linux
./run_discovery_server.sh --port 8000

# Su Windows
run_discovery_server.bat --port 8000
```

#### Avvio di un Nodo VPN

```bash
# Su macOS/Linux (richiede sudo)
sudo ./run_vpn_node.sh --server <IP_SERVER>:8000

# Su Windows (eseguire come amministratore)
run_vpn_node.bat --server <IP_SERVER>:8000
```

## Connessione tra due nodi

Per connettere due dispositivi:

1. Avvia il server di discovery su uno dei dispositivi (o su un server centrale)
2. Avvia un nodo VPN su ogni dispositivo, specificando l'indirizzo del server di discovery
3. I nodi stabiliranno automaticamente una connessione diretta tra loro
4. Ora puoi comunicare tra i dispositivi usando gli indirizzi IP della rete VPN

### Esempio tra macOS e Windows

Supponiamo che il server di discovery sia in esecuzione su macOS (192.168.1.10):

**Su macOS:**

```bash
# Avvia il server di discovery
./run_discovery_server.sh --port 8000

# Avvia il nodo VPN
sudo ./run_vpn_node.sh --server 192.168.1.10:8000 --id mac_node
```

**Su Windows:**

```batch
# Avvia il nodo VPN
run_vpn_node.bat --server 192.168.1.10:8000 --id win_node
```

Ora i due nodi sono connessi e possono comunicare tra loro.

## Risoluzione dei problemi

### Errori di interfaccia TUN/TAP

- Assicurati di eseguire i comandi con privilegi di amministratore
- Su Windows, verifica che i driver TAP siano installati correttamente
- Su macOS, potrebbe essere necessario abilitare le estensioni di sistema

### Problemi di connessione

- Verifica che il server di discovery sia raggiungibile da tutti i nodi
- Controlla che le porte non siano bloccate da firewall
- Usa `--bind 0.0.0.0` per il server di discovery se hai problemi di binding

## Licenza

Questo progetto è rilasciato sotto licenza MIT.
