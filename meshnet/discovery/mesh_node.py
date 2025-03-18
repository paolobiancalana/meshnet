#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import json
import time
import random
import logging
from typing import Dict, Any, Tuple, Optional, List, Set

# Importa moduli locali
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from meshnet.core.node import Node
from meshnet.discovery.stun_client import StunClient

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class MeshNode(Node):
    """
    Implementazione di un nodo mesh che utilizza un server di scoperta 
    centralizzato e tecniche di hole-punching per connessioni P2P.
    """
    
    def __init__(self, node_id: Optional[str] = None, local_port: int = 0,
                discovery_server: Tuple[str, int] = None):
        """
        Inizializza un nodo mesh.
        
        Args:
            node_id: ID univoco del nodo (generato automaticamente se None)
            local_port: Porta locale su cui ascoltare (0 = assegnata dal sistema)
            discovery_server: (host, porta) del server di scoperta
        """
        super().__init__(node_id, local_port)
        
        # Server di scoperta
        self.discovery_server = discovery_server
        self.registered = False
        
        # Aggiunta di gestori messaggi specifici
        self.handlers = {
            'register_ok': self._handle_register_ok,
            'discover_response': self._handle_discover_response,
            'hole_punch': self._handle_hole_punch,
            'hole_punch_ack': self._handle_hole_punch_ack,
            'pong': self._handle_pong
        }
        
        # Informazioni su NAT traversal
        self.hole_punching = {}
        self.connection_attempts = {}
        
        # Timeout per riconnessione
        self.reconnect_interval = 60  # secondi
        self.last_discover = 0
        
        self.logger.info("Nodo mesh inizializzato")
        
    def _handle_message(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Estende la gestione messaggi con handler specifici per mesh."""
        if 'action' not in message:
            return
            
        action = message['action']
        
        # Se il messaggio ha un ID nodo sorgente, aggiorniamo il peer
        if 'node_id' in message:
            peer_id = message['node_id']
            # Aggiorna o aggiungi il peer
            if peer_id != self.node_id and addr[0] != '127.0.0.1':
                if peer_id not in self.peers:
                    self.logger.info(f"Nuovo peer scoperto: {peer_id} @ {addr}")
                    self.peers[peer_id] = {
                        'external_ip': addr[0],
                        'external_port': addr[1],
                        'status': 'discovered',
                        'last_seen': time.time()
                    }
                else:
                    self.peers[peer_id].update({
                        'external_ip': addr[0],
                        'external_port': addr[1],
                        'last_seen': time.time()
                    })
        
        # Usa gli handler specifici per mesh, altrimenti usa quelli base
        if action in self.handlers:
            try:
                self.handlers[action](message, addr)
            except Exception as e:
                self.logger.error(f"Errore gestendo {action}: {e}")
        else:
            # Delega alla classe base
            super()._handle_message(message, addr)
            
    def start(self) -> None:
        """Avvia il nodo e lo registra al server di scoperta."""
        super().start()
        
        # Scopri indirizzo pubblico
        if not self.external_ip:
            self._discover_external_address()
            
        # Registra al server di scoperta
        if self.discovery_server:
            self._register_with_discovery()
            
        # Avvia thread per mantenere registrazione e scoprire nuovi peer
        self.maintenance_thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self.maintenance_thread.start()
        
        self.logger.info("Nodo mesh avviato")
        
    def stop(self) -> None:
        """Ferma il nodo mesh."""
        self.running = False
        super().stop()
        
    def _discover_external_address(self) -> None:
        """Scopre l'indirizzo IP pubblico e la porta usando STUN."""
        self.logger.info("Rilevamento indirizzo esterno via STUN...")
        stun = StunClient(self.local_port)
        external_ip, external_port = stun.discover()
        stun.close()  # Chiudi socket STUN
        
        if external_ip and external_port:
            self.external_ip = external_ip
            self.external_port = external_port
            self.logger.info(f"Indirizzo esterno rilevato: {external_ip}:{external_port}")
        else:
            self.logger.warning("Impossibile rilevare indirizzo esterno")
            
    def _register_with_discovery(self) -> None:
        """Registra il nodo al server di scoperta."""
        if not self.discovery_server:
            self.logger.warning("Nessun server di scoperta configurato")
            return
            
        self.logger.info(f"Registrazione al server di scoperta {self.discovery_server}...")
        
        message = {
            'action': 'register',
            'node_id': self.node_id,
            'local_ip': self.local_ip,
            'local_port': self.local_port,
            'capabilities': self._get_capabilities()
        }
        
        try:
            data = json.dumps(message).encode('utf-8')
            self.socket.sendto(data, self.discovery_server)
        except Exception as e:
            self.logger.error(f"Errore nella registrazione: {e}")
            
    def _get_capabilities(self) -> Dict[str, Any]:
        """Restituisce le funzionalità del nodo."""
        return {
            'version': '0.1',
            'hole_punch': True,
            'direct_connect': True
        }
        
    def _handle_register_ok(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce la conferma di registrazione dal server di scoperta."""
        self.registered = True
        
        # Aggiorna informazioni sull'indirizzo esterno se non rilevate da STUN
        if not self.external_ip and 'external_ip' in message:
            self.external_ip = message['external_ip']
            self.external_port = message['external_port']
            self.logger.info(f"Indirizzo esterno dal server: {self.external_ip}:{self.external_port}")
            
        self.logger.info("Registrazione al server di scoperta completata")
        
        # Scopri peer esistenti
        self._discover_peers()
        
    def _discover_peers(self) -> None:
        """Richiede l'elenco dei peer dal server di scoperta."""
        if not self.discovery_server or not self.registered:
            return
            
        self.logger.info("Richiesta elenco peer...")
        self.last_discover = time.time()
        
        # Prepara messaggio
        existing_peers = list(self.peers.keys())
        message = {
            'action': 'discover',
            'node_id': self.node_id,
            'exclude_ids': existing_peers,
        }
        
        try:
            data = json.dumps(message).encode('utf-8')
            self.socket.sendto(data, self.discovery_server)
        except Exception as e:
            self.logger.error(f"Errore nella scoperta peer: {e}")
            
    def _handle_discover_response(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce la risposta alla richiesta di scoperta peer."""
        if 'nodes' not in message:
            return
            
        nodes = message['nodes']
        self.logger.info(f"Ricevuti {len(nodes)} peer dal server di scoperta")
        
        for node in nodes:
            if 'node_id' not in node or node['node_id'] == self.node_id:
                continue
                
            peer_id = node['node_id']
            
            # Aggiorna il peer con le informazioni dal server
            if peer_id not in self.peers:
                self.peers[peer_id] = {
                    'external_ip': node['external_ip'],
                    'external_port': node['external_port'],
                    'status': 'discovered',
                    'last_seen': time.time() - 600  # Forza tentativo immediato
                }
                
                # Salva anche indirizzi locali se disponibili
                if 'local_ip' in node and 'local_port' in node:
                    self.peers[peer_id]['local_ip'] = node['local_ip']
                    self.peers[peer_id]['local_port'] = node['local_port']
                    
                self.logger.info(f"Nuovo peer dal server: {peer_id} @ {node['external_ip']}:{node['external_port']}")
                
                # Avvia hole punching per stabilire connessione
                self._initiate_hole_punch(peer_id)
                
    def _maintenance_loop(self) -> None:
        """Loop di manutenzione per registrazione e connessioni."""
        while self.running:
            try:
                # Controllo registrazione
                if self.discovery_server and not self.registered:
                    self._register_with_discovery()
                    
                # Scoperta periodica peer
                now = time.time()
                if self.registered and now - self.last_discover > self.reconnect_interval:
                    self._discover_peers()
                    
                # Controllo connessioni
                self._check_peer_connections()
                
                # Pulizia peer inattivi
                self.cleanup_peers()
                
            except Exception as e:
                self.logger.error(f"Errore nel loop di manutenzione: {e}")
                
            time.sleep(5)  # Intervallo di controllo
            
    def _check_peer_connections(self) -> None:
        """Controlla lo stato delle connessioni ai peer e inizia hole punching se necessario."""
        now = time.time()
        
        for peer_id, info in list(self.peers.items()):
            # Ignora peer in fase di connessione
            if peer_id in self.hole_punching:
                continue
                
            status = info.get('status', 'unknown')
            last_seen = info.get('last_seen', 0)
            
            # Se il peer è inattivo da troppo tempo, prova a riconnetterti
            if status != 'active' and now - last_seen > 60:
                self._initiate_hole_punch(peer_id)
            # Se è attivo ma non abbiamo ricevuto messaggi recentemente, ping
            elif status == 'active' and now - last_seen > 30:
                self.ping_peer(peer_id)
                
    def _initiate_hole_punch(self, peer_id: str) -> None:
        """Inizia il processo di hole punching con un peer."""
        if peer_id not in self.peers:
            return
            
        # Evita tentativi multipli contemporanei
        if peer_id in self.hole_punching:
            return
            
        self.logger.info(f"Avvio hole punching con peer: {peer_id}")
        
        # Segna l'inizio del tentativo
        self.hole_punching[peer_id] = {
            'start_time': time.time(),
            'attempts': 0,
            'max_attempts': 5
        }
        
        # Invia pacchetto di hole punching al peer
        peer = self.peers[peer_id]
        
        message = {
            'action': 'hole_punch',
            'node_id': self.node_id,
        }
        
        # Prova sia indirizzo esterno che locale se disponibile
        external_addr = (peer['external_ip'], peer['external_port'])
        self._send_to_addr(message, external_addr)
        
        # Se abbiamo informazioni sull'indirizzo locale, prova anche quello
        if 'local_ip' in peer and 'local_port' in peer:
            local_addr = (peer['local_ip'], peer['local_port'])
            if local_addr != external_addr:
                self._send_to_addr(message, local_addr)
                
        # Programma ulteriori tentativi
        threading.Timer(1.0, self._hole_punch_retry, args=[peer_id]).start()
        
    def _hole_punch_retry(self, peer_id: str) -> None:
        """Gestisce i tentativi ripetuti di hole punching."""
        if not self.running or peer_id not in self.hole_punching:
            return
            
        info = self.hole_punching[peer_id]
        info['attempts'] += 1
        
        # Verifica se abbiamo raggiunto il massimo di tentativi
        if info['attempts'] >= info['max_attempts']:
            self.logger.warning(f"Hole punching fallito dopo {info['attempts']} tentativi con {peer_id}")
            del self.hole_punching[peer_id]
            return
            
        # Riprova invio pacchetto
        if peer_id in self.peers:
            peer = self.peers[peer_id]
            
            message = {
                'action': 'hole_punch',
                'node_id': self.node_id,
                'attempt': info['attempts']
            }
            
            # Alterna tentativi tra indirizzo esterno e locale
            if info['attempts'] % 2 == 0:
                external_addr = (peer['external_ip'], peer['external_port'])
                self._send_to_addr(message, external_addr)
            elif 'local_ip' in peer and 'local_port' in peer:
                local_addr = (peer['local_ip'], peer['local_port'])
                self._send_to_addr(message, local_addr)
                
            # Programma prossimo tentativo con backoff esponenziale
            delay = min(5, 0.5 * 2 ** info['attempts'])
            threading.Timer(delay, self._hole_punch_retry, args=[peer_id]).start()
        else:
            del self.hole_punching[peer_id]
            
    def _handle_hole_punch(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce un pacchetto di hole punching ricevuto."""
        if 'node_id' not in message:
            return
            
        peer_id = message['node_id']
        
        self.logger.info(f"Ricevuto hole punch da {peer_id} @ {addr}")
        
        # Aggiorna o crea il peer
        if peer_id in self.peers:
            # Aggiorna indirizzo se necessario
            self.peers[peer_id].update({
                'external_ip': addr[0],
                'external_port': addr[1],
                'status': 'active',
                'last_seen': time.time()
            })
        else:
            self.peers[peer_id] = {
                'external_ip': addr[0],
                'external_port': addr[1],
                'status': 'active',
                'last_seen': time.time()
            }
        
        # Invia ACK di hole punch
        response = {
            'action': 'hole_punch_ack',
            'node_id': self.node_id,
        }
        self._send_to_addr(response, addr)
        
    def _handle_hole_punch_ack(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce la conferma di hole punching ricevuta."""
        if 'node_id' not in message:
            return
            
        peer_id = message['node_id']
        
        self.logger.info(f"Hole punch confermato con {peer_id} @ {addr}")
        
        # Aggiorna il peer come attivo
        if peer_id in self.peers:
            self.peers[peer_id].update({
                'external_ip': addr[0],
                'external_port': addr[1],
                'status': 'active',
                'last_seen': time.time()
            })
        
        # Rimuovi stato hole punching
        if peer_id in self.hole_punching:
            del self.hole_punching[peer_id]
            
    def _handle_pong(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce le risposte ping."""
        if 'node_id' not in message:
            return
            
        peer_id = message['node_id']
        
        if peer_id in self.peers:
            self.peers[peer_id]['last_seen'] = time.time()
            self.peers[peer_id]['status'] = 'active'
            self.logger.debug(f"Pong ricevuto da {peer_id}")
            
    def get_active_peers(self) -> List[str]:
        """Ottiene la lista dei peer attualmente attivi."""
        now = time.time()
        return [
            peer_id for peer_id, info in self.peers.items()
            if info.get('status') == 'active' and now - info.get('last_seen', 0) < 60
        ]
    
if __name__ == "__main__":
    # Esempio d'uso
    import argparse
    
    parser = argparse.ArgumentParser(description='Nodo Mesh P2P')
    parser.add_argument('--id', help='ID del nodo (generato casualmente se non fornito)')
    parser.add_argument('--port', type=int, default=0, help='Porta locale (0=caso)')
    parser.add_argument('--server', default='127.0.0.1:8000', help='Server di scoperta (host:porta)')
    args = parser.parse_args()
    
    # Converti l'indirizzo del server in (host, porta)
    server_parts = args.server.split(':')
    if len(server_parts) != 2:
        print("Formato server non valido. Usa 'host:porta'")
        sys.exit(1)
    discovery_server = (server_parts[0], int(server_parts[1]))
    
    # Configura logging
    logging.getLogger().setLevel(logging.INFO)
    
    # Crea e avvia il nodo
    node = MeshNode(args.id, args.port, discovery_server)
    node.start()
    
    print(f"Nodo avviato con ID: {node.node_id}")
    print(f"Indirizzo locale: {node.local_ip}:{node.local_port}")
    
    try:
        while True:
            time.sleep(10)
            active_peers = node.get_active_peers()
            if active_peers:
                print(f"Peer attivi ({len(active_peers)}): {', '.join(active_peers)}")
    except KeyboardInterrupt:
        print("Interruzione...")
    finally:
        node.stop()
        print("Nodo fermato.") 