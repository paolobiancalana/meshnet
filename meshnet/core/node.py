#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import json
import time
import uuid
import logging
from typing import Dict, Any, Tuple, Optional, List, Set

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class Node:
    """
    Classe base per un nodo P2P che implementa la comunicazione di base.
    """
    
    def __init__(self, node_id: Optional[str] = None, local_port: int = 0):
        """
        Inizializza un nuovo nodo.
        
        Args:
            node_id: ID univoco del nodo (generato automaticamente se None)
            local_port: Porta locale su cui ascoltare (0 = assegnata dal sistema)
        """
        self.node_id = node_id or str(uuid.uuid4())[:8]
        self.logger = logging.getLogger(f"Node-{self.node_id}")
        
        # Informazioni di rete
        self.local_ip = self._get_local_ip()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', local_port))
        self.local_port = self.socket.getsockname()[1]
        self.external_ip = None
        self.external_port = None
        
        # Gestione dei peer
        self.peers: Dict[str, Dict[str, Any]] = {}
        self.running = True
        
        self.logger.info(f"Nodo inizializzato con ID: {self.node_id}")
        self.logger.info(f"Indirizzo locale: {self.local_ip}:{self.local_port}")
    
    def _get_local_ip(self) -> str:
        """Determina l'indirizzo IP locale."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connessione non reale, solo per ottenere l'interfaccia
            s.connect(('8.8.8.8', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip
        
    def start(self) -> None:
        """Avvia il nodo e inizia ad ascoltare per messaggi in entrata."""
        # Avvia thread per gestire messaggi in entrata
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        
        self.logger.info(f"Nodo avviato e in ascolto su {self.local_ip}:{self.local_port}")
        
    def stop(self) -> None:
        """Ferma il nodo."""
        self.running = False
        self.logger.info("Arresto nodo in corso...")
        # Il socket verrà chiuso quando il thread termina
        
    def _receive_loop(self) -> None:
        """Loop principale per ricevere messaggi."""
        self.socket.settimeout(1.0)  # Timeout di 1 secondo per permettere l'arresto
        
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
    
    def _handle_message(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce un messaggio ricevuto."""
        if 'action' not in message or 'node_id' not in message:
            return
            
        peer_id = message['node_id']
        action = message['action']
        
        self.logger.debug(f"Messaggio da {peer_id}@{addr}: {action}")
        
        # Aggiorna info peer se è conosciuto
        if peer_id in self.peers:
            self.peers[peer_id]['last_seen'] = time.time()
            
        # Routing basato sull'azione
        handler_name = f"_handle_{action}"
        if hasattr(self, handler_name):
            handler = getattr(self, handler_name)
            try:
                handler(message, addr, peer_id)
            except Exception as e:
                self.logger.error(f"Errore gestendo {action} da {peer_id}: {e}")
        else:
            self.logger.warning(f"Azione sconosciuta: {action}")
    
    def _handle_ping(self, message: Dict[str, Any], addr: Tuple[str, int], peer_id: str) -> None:
        """Gestisce un messaggio ping."""
        self.logger.debug(f"Ping ricevuto da {peer_id}")
        response = {
            'action': 'pong',
            'node_id': self.node_id,
            'timestamp': time.time()
        }
        self._send_to_addr(response, addr)
    
    def _send_to_addr(self, message: Dict[str, Any], addr: Tuple[str, int]) -> bool:
        """Invia un messaggio a un indirizzo specifico."""
        try:
            data = json.dumps(message).encode('utf-8')
            self.socket.sendto(data, addr)
            return True
        except Exception as e:
            self.logger.error(f"Errore inviando a {addr}: {e}")
            return False
    
    def send_to_peer(self, peer_id: str, message: Dict[str, Any]) -> bool:
        """Invia un messaggio a un peer conosciuto."""
        if peer_id not in self.peers:
            self.logger.warning(f"Tentativo di invio a peer sconosciuto: {peer_id}")
            return False
            
        # Assicurati che il messaggio contenga l'ID del nodo mittente
        message['node_id'] = self.node_id
        
        peer = self.peers[peer_id]
        if 'external_ip' not in peer or 'external_port' not in peer:
            self.logger.warning(f"Indirizzo peer non disponibile: {peer_id}")
            return False
            
        addr = (peer['external_ip'], peer['external_port'])
        return self._send_to_addr(message, addr)
    
    def ping_peer(self, peer_id: str) -> bool:
        """Invia un ping a un peer."""
        message = {
            'action': 'ping',
            'node_id': self.node_id,
            'timestamp': time.time()
        }
        return self.send_to_peer(peer_id, message)
    
    def add_peer(self, peer_id: str, external_ip: str, external_port: int) -> None:
        """Aggiunge un peer manualmente."""
        if peer_id == self.node_id:
            return
            
        if peer_id not in self.peers:
            self.peers[peer_id] = {
                'external_ip': external_ip,
                'external_port': external_port,
                'status': 'manual',
                'last_seen': time.time()
            }
            self.logger.info(f"Peer aggiunto manualmente: {peer_id} @ {external_ip}:{external_port}")
        else:
            # Aggiorna informazioni
            self.peers[peer_id].update({
                'external_ip': external_ip,
                'external_port': external_port,
                'last_seen': time.time()
            })
            self.logger.info(f"Informazioni peer aggiornate: {peer_id}")
            
    def get_peers(self) -> Dict[str, Dict[str, Any]]:
        """Ottiene la lista dei peer conosciuti."""
        return self.peers
            
    def cleanup_peers(self, max_age: int = 300) -> None:
        """Rimuove peer inattivi da troppo tempo."""
        now = time.time()
        inactive = []
        
        for peer_id, data in self.peers.items():
            if now - data.get('last_seen', 0) > max_age:
                inactive.append(peer_id)
                
        for peer_id in inactive:
            del self.peers[peer_id]
            self.logger.info(f"Peer rimosso (inattivo): {peer_id}")
            
    def __str__(self) -> str:
        """Rappresentazione stringa del nodo."""
        return f"Node(id={self.node_id}, address={self.local_ip}:{self.local_port})" 