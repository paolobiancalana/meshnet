# MeshNet

Una VPN mesh peer-to-peer con scoperta automatica dei nodi e tecnica NAT traversal.

## Caratteristiche

- **Connessioni P2P dirette**: Comunicazione diretta tra nodi anche dietro NAT tramite UDP hole punching
- **Scoperta automatica**: Trova altri nodi nella rete tramite server di scoperta centralizzato
- **Rete virtuale privata**: Crea interfacce TUN/TAP per routing di rete trasparente
- **Crittografia end-to-end**: Tutti i pacchetti sono cifrati con NaCl (PyNaCl)
- **Multi-piattaforma**: Supporta Linux e macOS (supporto Windows in sviluppo)

## Requisiti

- Python 3.7 o superiore
- Privilegi root/admin (per creare interfacce TUN/TAP)
- Dipendenze: PyNaCl

## Installazione

```bash
# Clona il repository
git clone https://github.com/paolobiancalana/meshnet.git
cd meshnet

# Installa dipendenze
pip install -r requirements.txt
```

## Utilizzo

### Avvio server di scoperta

Per prima cosa, è necessario avviare un server di scoperta che aiuta i nodi a trovarsi:

```bash
python -m meshnet.discovery.discovery_server
```

Il server sarà in ascolto sulla porta UDP 8000 per impostazione predefinita.

### Avvio dei nodi VPN

Su ogni macchina che vuoi aggiungere alla VPN mesh, avvia un nodo:

```bash
sudo python -m meshnet.core.vpn_node --server IP_SERVER:8000 --key CHIAVE_RETE
```

Dove:

- `IP_SERVER` è l'IP o hostname pubblico del server di scoperta
- `CHIAVE_RETE` è una chiave condivisa che tutti i nodi devono utilizzare (es. generata con `python -c "import nacl.utils; print(nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE).hex())"`)

Per generare una nuova chiave di rete:

```bash
python -c "import nacl.secret, nacl.utils; print(nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE).hex())"
```

### Opzioni avanzate

```
Opzioni nodo VPN:
  --id ID            ID nodo (generato automaticamente se non specificato)
  --port PORT        Porta locale UDP (default: assegnata dal sistema)
  --server HOST:PORT Server di scoperta (default: 127.0.0.1:8000)
  --tun ADDRESS      Indirizzo interfaccia TUN (es: 10.0.0.1/24)
  --network NETWORK  Rete VPN CIDR (default: 10.0.0.0/24)
  --key KEY          Chiave di crittografia (hex)
```

## Architettura

MeshNet è composto da diversi moduli:

1. **Core**: Componenti base come il nodo P2P e le interfacce TUN
2. **Discovery**: Meccanismi per la scoperta dei peer e NAT traversal
3. **Protocols**: Protocolli di comunicazione e crittografia
4. **Utils**: Utilità varie

Il flusso di funzionamento è:

1. I nodi si avviano e creano interfacce TUN
2. Si registrano al server di scoperta e ottengono il loro indirizzo pubblico
3. Scoprono altri nodi tramite il server
4. Stabiliscono connessioni P2P dirette tramite UDP hole punching
5. Comunicano in modo sicuro tramite l'interfaccia TUN cifrata

## Limitazioni attuali

- Supporto Windows in sviluppo
- La registrazione e autenticazione dei nodi è basilare
- Non implementato il supporto DHT completo (solo server centralizzato)
- Supporto limitato per IPV6

## Contribuire

Contributi sono benvenuti! Apri una issue o una pull request.

## Licenza

Questo progetto è rilasciato sotto licenza MIT.
