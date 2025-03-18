#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import json
import time
import logging
from typing import Dict, Any, Tuple, List, Set

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class DiscoveryServer:
    """
    Server di scoperta centralizzato per la rete mesh.
    Consente ai nodi di registrarsi e scoprire altri nodi nella rete.
    """
    
    def __init__(self, bind_address: str = '0.0.0.0', port: int = 8000):
        """
        Inizializza il server di scoperta.
        
        Args:
            bind_address: Indirizzo su cui avviare il server
            port: Porta su cui ascoltare
        """
        self.bind_address = bind_address
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((bind_address, port))
        
        # Registro dei nodi
        self.nodes: Dict[str, Dict[str, Any]] = {}
        
        # Flag per controllo esecuzione
        self.running = False
        
        self.logger = logging.getLogger("DiscoveryServer")
        self.logger.info(f"Server inizializzato su {bind_address}:{port}")
        
    def start(self) -> None:
        """Avvia il server di scoperta."""
        if self.running:
            return
            
        self.running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        
        # Thread per pulizia nodi inattivi
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        
        self.logger.info("Server di scoperta avviato")
        
    def stop(self) -> None:
        """Ferma il server di scoperta."""
        self.running = False
        self.logger.info("Arresto server in corso...")
        
    def _receive_loop(self) -> None:
        """Loop principale per ricevere messaggi."""
        self.socket.settimeout(1.0)
        
        while self.running:
            try:
                data, addr = self.socket.recvfrom(4096)
                try:
                    message = json.loads(data.decode('utf-8'))
                    self._handle_message(message, addr)
                except json.JSONDecodeError:
                    self.logger.warning(f"Ricevuto messaggio non valido da {addr}")
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Errore nella ricezione: {e}")
                    
    def _cleanup_loop(self) -> None:
        """Loop per rimuovere nodi inattivi."""
        while self.running:
            try:
                self._cleanup_nodes()
            except Exception as e:
                self.logger.error(f"Errore durante pulizia nodi: {e}")
            time.sleep(60)  # Controlla ogni minuto
                    
    def _handle_message(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce un messaggio ricevuto."""
        if 'action' not in message:
            return
            
        action = message['action']
        self.logger.debug(f"Ricevuto messaggio {action} da {addr}")
        
        # Dispatch basato sull'azione richiesta
        handlers = {
            'register': self._handle_register,
            'discover': self._handle_discover,
            'ping': self._handle_ping
        }
        
        if action in handlers:
            try:
                handlers[action](message, addr)
            except Exception as e:
                self.logger.error(f"Errore gestendo {action} da {addr}: {e}")
        else:
            self.logger.warning(f"Azione sconosciuta: {action}")
            
    def _handle_register(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce la registrazione di un nodo."""
        if 'node_id' not in message:
            return
            
        node_id = message['node_id']
        
        # Estrai informazioni dal messaggio
        node_info = {
            'external_ip': addr[0],
            'external_port': addr[1],
            'last_seen': time.time()
        }
        
        # Aggiungi campi opzionali se presenti
        for field in ['local_ip', 'local_port', 'capabilities']:
            if field in message:
                node_info[field] = message[field]
                
        # Aggiorna o crea record
        if node_id in self.nodes:
            self.nodes[node_id].update(node_info)
            action = "aggiornato"
        else:
            self.nodes[node_id] = node_info
            action = "registrato"
            
        self.logger.info(f"Nodo {action}: {node_id} @ {addr[0]}:{addr[1]}")
        
        # Invia conferma
        response = {
            'action': 'register_ok',
            'node_id': node_id,
            'external_ip': addr[0],
            'external_port': addr[1],
            'timestamp': time.time()
        }
        self._send_response(response, addr)
        
    def _handle_discover(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce la richiesta di scoperta dei nodi."""
        if 'node_id' not in message:
            return
            
        requester_id = message['node_id']
        exclude_ids = message.get('exclude_ids', [])
        exclude_ids.append(requester_id)  # Non includere il richiedente
        
        # Filtra nodi attivi escludendo quelli richiesti
        now = time.time()
        active_nodes = {
            node_id: info for node_id, info in self.nodes.items()
            if now - info['last_seen'] < 300 and node_id not in exclude_ids
        }
        
        # Prepara risposta
        response = {
            'action': 'discover_response',
            'nodes': [
                {
                    'node_id': node_id,
                    'external_ip': info['external_ip'],
                    'external_port': info['external_port'],
                    'local_ip': info.get('local_ip'),
                    'local_port': info.get('local_port'),
                    'capabilities': info.get('capabilities', {})
                }
                for node_id, info in active_nodes.items()
            ],
            'timestamp': time.time()
        }
        
        self.logger.info(f"Inviati {len(response['nodes'])} nodi a {requester_id}")
        self._send_response(response, addr)
        
    def _handle_ping(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce richieste ping."""
        response = {
            'action': 'pong',
            'timestamp': time.time()
        }
        self._send_response(response, addr)
        
        # Aggiorna last_seen se il nodo è registrato
        if 'node_id' in message and message['node_id'] in self.nodes:
            self.nodes[message['node_id']]['last_seen'] = time.time()
            
    def _send_response(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Invia una risposta a un indirizzo specifico."""
        try:
            data = json.dumps(message).encode('utf-8')
            self.socket.sendto(data, addr)
        except Exception as e:
            self.logger.error(f"Errore inviando a {addr}: {e}")
            
    def _cleanup_nodes(self, max_age: int = 300) -> None:
        """Rimuove nodi inattivi da troppo tempo."""
        now = time.time()
        before_count = len(self.nodes)
        
        # Rimuovi nodi inattivi
        inactive = []
        for node_id, info in self.nodes.items():
            if now - info['last_seen'] > max_age:
                inactive.append(node_id)
                
        for node_id in inactive:
            del self.nodes[node_id]
            
        after_count = len(self.nodes)
        if inactive:
            self.logger.info(f"Rimossi {before_count - after_count} nodi inattivi")
            
    def get_node_count(self) -> int:
        """Restituisce il numero di nodi registrati."""
        return len(self.nodes)
        
    def __str__(self) -> str:
        """Rappresentazione stringa del server."""
        return f"DiscoveryServer(address={self.bind_address}:{self.port}, nodes={len(self.nodes)})"
        
if __name__ == "__main__":
    # Esempio di esecuzione
    server = DiscoveryServer()
    server.start()
    try:
        while True:
            time.sleep(1)
            if server.get_node_count() > 0:
                print(f"Nodi attivi: {server.get_node_count()}")
    except KeyboardInterrupt:
        print("Interruzione...")
    finally:
        server.stop()
        print("Server fermato.") 