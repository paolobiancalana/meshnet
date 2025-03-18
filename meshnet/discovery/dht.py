#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import socket
import threading
import json
import time
import random
import hashlib
import logging
from typing import Dict, Any, List, Tuple, Optional, Set, Union

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class DHTNode:
    """
    Implementazione semplificata di un nodo DHT (Distributed Hash Table).
    Basato su una versione semplificata del protocollo Kademlia.
    
    Questo è un prototipo base e non implementa tutte le funzionalità
    di un DHT completo. In un'implementazione reale, si consiglia di
    utilizzare librerie dedicate come py-libp2p o Kademlia.
    """
    
    # Numero di bit per gli ID (160 bit = 20 byte come in Kademlia)
    ID_BITS = 160
    
    # Dimensione del k-bucket (numero di nodi per bucket)
    K = 20
    
    # Numero di nodi da contattare in parallelo per le operazioni
    ALPHA = 3
    
    def __init__(self, node_id: Optional[str] = None, port: int = 0):
        """
        Inizializza un nodo DHT.
        
        Args:
            node_id: ID del nodo (hex string di 40 caratteri).
                     Se None, viene generato automaticamente.
            port: Porta su cui ascoltare
        """
        # Genera o valida ID nodo
        if node_id is None:
            # Genera ID casuale
            random_bytes = os.urandom(self.ID_BITS // 8)
            self.node_id = hashlib.sha1(random_bytes).hexdigest()
        else:
            # Valida formato ID
            if len(node_id) != 40 or not all(c in '0123456789abcdef' for c in node_id.lower()):
                raise ValueError("ID nodo deve essere una stringa hex di 40 caratteri")
            self.node_id = node_id.lower()
            
        # Converti ID in intero per operazioni bit-a-bit
        self.node_id_int = int(self.node_id, 16)
        
        # Crea socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('0.0.0.0', port))
        self.port = self.socket.getsockname()[1]
        
        # Routing table (k-buckets)
        self.buckets: List[List[Dict[str, Any]]] = [[] for _ in range(self.ID_BITS)]
        
        # Storage per valori (chiave -> valore)
        self.storage: Dict[str, Any] = {}
        
        # Contatti recenti
        self.recent_contacts: Dict[str, Dict[str, Any]] = {}
        
        # Lock per thread-safety
        self.buckets_lock = threading.RLock()
        self.storage_lock = threading.RLock()
        
        # Flag per controllo esecuzione
        self.running = False
        
        # Logger
        self.logger = logging.getLogger(f"DHTNode-{self.node_id[:8]}")
        self.logger.info(f"Nodo DHT inizializzato con ID: {self.node_id[:8]}...")
        
    def start(self) -> None:
        """Avvia il nodo DHT."""
        if self.running:
            return
            
        self.running = True
        
        # Avvia thread per gestione messaggi in arrivo
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        
        # Thread per manutenzione
        self.maintenance_thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self.maintenance_thread.start()
        
        self.logger.info(f"Nodo DHT avviato sulla porta {self.port}")
        
    def stop(self) -> None:
        """Ferma il nodo DHT."""
        if not self.running:
            return
            
        self.running = False
        self.logger.info("Arresto nodo DHT...")
        
        # Attendi che i thread terminino
        self.receive_thread.join(timeout=3.0)
        self.maintenance_thread.join(timeout=1.0)
        
        # Chiudi socket
        try:
            self.socket.close()
        except:
            pass
            
        self.logger.info("Nodo DHT arrestato")
        
    def bootstrap(self, nodes: List[Tuple[str, int]]) -> bool:
        """
        Avvia il bootstrap del nodo DHT contattando nodi conosciuti.
        
        Args:
            nodes: Lista di (host, porta) di nodi bootstrap
            
        Returns:
            True se almeno un nodo ha risposto, False altrimenti
        """
        if not nodes:
            return False
            
        self.logger.info(f"Avvio bootstrap con {len(nodes)} nodi")
        
        # Contatta nodi bootstrap
        successful = False
        for host, port in nodes:
            try:
                # Ping nodo
                if self._ping_node(host, port):
                    # Trova nodi vicini al nostro ID
                    self._find_node(self.node_id, host, port)
                    successful = True
            except Exception as e:
                self.logger.warning(f"Errore bootstrap con {host}:{port}: {e}")
                
        return successful
        
    def store(self, key: str, value: Any) -> bool:
        """
        Memorizza una coppia chiave-valore nel DHT.
        
        Args:
            key: Chiave (verrà convertita in hash)
            value: Valore da memorizzare (deve essere serializzabile JSON)
            
        Returns:
            True se memorizzato con successo, False altrimenti
        """
        # Calcola hash della chiave
        key_hash = hashlib.sha1(key.encode('utf-8')).hexdigest()
        
        # Trova nodi più vicini alla chiave
        nearest_nodes = self.find_nodes(key_hash, self.K)
        
        if not nearest_nodes:
            # Nessun nodo disponibile, salva localmente
            with self.storage_lock:
                self.storage[key_hash] = value
            return True
            
        # Invia richiesta STORE a tutti i nodi trovati
        successful = False
        for node in nearest_nodes:
            host, port = node['addr']
            try:
                self._send_store(key_hash, value, host, port)
                successful = True
            except Exception as e:
                self.logger.warning(f"Errore inviando STORE a {host}:{port}: {e}")
                
        return successful
        
    def get(self, key: str) -> Any:
        """
        Recupera un valore dal DHT.
        
        Args:
            key: Chiave da cercare
            
        Returns:
            Valore associato alla chiave o None se non trovato
        """
        # Calcola hash della chiave
        key_hash = hashlib.sha1(key.encode('utf-8')).hexdigest()
        
        # Verifica se presente in locale
        with self.storage_lock:
            if key_hash in self.storage:
                return self.storage[key_hash]
                
        # Trova nodi più vicini alla chiave
        nearest_nodes = self.find_nodes(key_hash, self.K)
        
        # Contatta nodi per trovare il valore
        for node in nearest_nodes:
            host, port = node['addr']
            try:
                value = self._send_find_value(key_hash, host, port)
                if value is not None:
                    # Memorizza in cache locale
                    with self.storage_lock:
                        self.storage[key_hash] = value
                    return value
            except Exception as e:
                self.logger.warning(f"Errore inviando FIND_VALUE a {host}:{port}: {e}")
                
        return None
        
    def find_nodes(self, target_id: str, count: int = K) -> List[Dict[str, Any]]:
        """
        Trova i nodi più vicini a un ID.
        
        Args:
            target_id: ID target (hex string)
            count: Numero massimo di nodi da restituire
            
        Returns:
            Lista di nodi ordinati per distanza (più vicini prima)
        """
        target_int = int(target_id, 16)
        
        # Raccogli tutti i nodi conosciuti
        all_nodes = []
        with self.buckets_lock:
            for bucket in self.buckets:
                all_nodes.extend(bucket)
                
        # Calcola distanza e ordina
        nodes_with_distance = []
        for node in all_nodes:
            node_id_int = int(node['node_id'], 16)
            distance = node_id_int ^ target_int
            nodes_with_distance.append((distance, node))
            
        # Ordina per distanza e prendi i primi 'count'
        nodes_with_distance.sort(key=lambda x: x[0])
        return [node for _, node in nodes_with_distance[:count]]
        
    def _calculate_bucket_index(self, node_id: str) -> int:
        """
        Calcola l'indice del bucket per un ID nodo.
        
        Args:
            node_id: ID nodo (hex string)
            
        Returns:
            Indice del bucket (0-159)
        """
        node_int = int(node_id, 16)
        distance = self.node_id_int ^ node_int
        
        # Trova il bit più significativo diverso
        if distance == 0:
            return 0
            
        # Converti distanza in binario e trova indice del primo '1'
        bin_distance = bin(distance)[2:]
        index = self.ID_BITS - len(bin_distance)
        return index
        
    def _update_routing_table(self, node_id: str, addr: Tuple[str, int]) -> None:
        """
        Aggiorna la tabella di routing con un nuovo nodo.
        
        Args:
            node_id: ID del nodo (hex string)
            addr: (host, porta) del nodo
        """
        if node_id == self.node_id:
            return  # Ignora se stesso
            
        bucket_index = self._calculate_bucket_index(node_id)
        
        with self.buckets_lock:
            bucket = self.buckets[bucket_index]
            
            # Verifica se il nodo è già presente
            for node in bucket:
                if node['node_id'] == node_id:
                    # Sposta in fondo (più recente)
                    bucket.remove(node)
                    node['last_seen'] = time.time()
                    bucket.append(node)
                    return
                    
            # Nuovo nodo
            new_node = {
                'node_id': node_id,
                'addr': addr,
                'last_seen': time.time()
            }
            
            # Se il bucket è pieno, elimina il nodo più vecchio
            if len(bucket) >= self.K:
                # Ping il nodo più vecchio prima di eliminarlo
                oldest_node = bucket[0]
                oldest_addr = oldest_node['addr']
                
                if self._ping_node(oldest_addr[0], oldest_addr[1]):
                    # Se risponde, sposta in fondo e scarta il nuovo nodo
                    bucket.remove(oldest_node)
                    oldest_node['last_seen'] = time.time()
                    bucket.append(oldest_node)
                else:
                    # Se non risponde, eliminalo e aggiungi il nuovo
                    bucket.pop(0)
                    bucket.append(new_node)
            else:
                # Se c'è spazio, aggiungi direttamente
                bucket.append(new_node)
                
    def _receive_loop(self) -> None:
        """Loop principale per ricevere messaggi."""
        self.socket.settimeout(1.0)  # 1 secondo timeout
        
        while self.running:
            try:
                data, addr = self.socket.recvfrom(4096)
                
                try:
                    message = json.loads(data.decode('utf-8'))
                    self._handle_message(message, addr)
                except json.JSONDecodeError:
                    self.logger.warning(f"Ricevuto messaggio non JSON da {addr}")
                    
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Errore nella ricezione: {e}")
                    
    def _handle_message(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """
        Gestisce un messaggio ricevuto.
        
        Args:
            message: Messaggio ricevuto
            addr: (host, porta) del mittente
        """
        if 'type' not in message or 'node_id' not in message:
            return
            
        msg_type = message['type']
        node_id = message['node_id']
        
        # Aggiorna routing table
        self._update_routing_table(node_id, addr)
        
        # Dispatch in base al tipo
        handlers = {
            'PING': self._handle_ping,
            'PONG': self._handle_pong,
            'FIND_NODE': self._handle_find_node,
            'FIND_VALUE': self._handle_find_value,
            'STORE': self._handle_store,
            'NODES': self._handle_nodes
        }
        
        if msg_type in handlers:
            try:
                handlers[msg_type](message, addr)
            except Exception as e:
                self.logger.error(f"Errore gestendo {msg_type} da {addr}: {e}")
                
    def _handle_ping(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce un messaggio PING."""
        response = {
            'type': 'PONG',
            'node_id': self.node_id,
            'msgid': message.get('msgid', '')
        }
        self._send_message(response, addr)
        
    def _handle_pong(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce un messaggio PONG."""
        # Solo per aggiornare routing table, già fatto in _handle_message
        pass
        
    def _handle_find_node(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce un messaggio FIND_NODE."""
        if 'target' not in message:
            return
            
        target_id = message['target']
        nearest_nodes = self.find_nodes(target_id, self.K)
        
        # Prepara risposta
        response = {
            'type': 'NODES',
            'node_id': self.node_id,
            'msgid': message.get('msgid', ''),
            'nodes': [
                {
                    'node_id': node['node_id'],
                    'host': node['addr'][0],
                    'port': node['addr'][1]
                }
                for node in nearest_nodes
            ]
        }
        
        self._send_message(response, addr)
        
    def _handle_find_value(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce un messaggio FIND_VALUE."""
        if 'key' not in message:
            return
            
        key = message['key']
        
        # Controlla se abbiamo il valore
        with self.storage_lock:
            if key in self.storage:
                response = {
                    'type': 'VALUE',
                    'node_id': self.node_id,
                    'msgid': message.get('msgid', ''),
                    'key': key,
                    'value': self.storage[key]
                }
                self._send_message(response, addr)
                return
                
        # Se non abbiamo il valore, restituisci i nodi più vicini
        return self._handle_find_node(
            {'type': 'FIND_NODE', 'node_id': message['node_id'], 'target': key},
            addr
        )
        
    def _handle_store(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce un messaggio STORE."""
        if 'key' not in message or 'value' not in message:
            return
            
        key = message['key']
        value = message['value']
        
        # Memorizza il valore
        with self.storage_lock:
            self.storage[key] = value
            
        # Risposta di conferma
        response = {
            'type': 'STORE_OK',
            'node_id': self.node_id,
            'msgid': message.get('msgid', ''),
            'key': key
        }
        self._send_message(response, addr)
        
    def _handle_nodes(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Gestisce un messaggio NODES (risposta a FIND_NODE)."""
        if 'nodes' not in message:
            return
            
        # Aggiorna routing table con i nodi ricevuti
        for node in message['nodes']:
            if 'node_id' not in node or 'host' not in node or 'port' not in node:
                continue
                
            node_addr = (node['host'], node['port'])
            self._update_routing_table(node['node_id'], node_addr)
            
    def _send_message(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """
        Invia un messaggio a un indirizzo.
        
        Args:
            message: Messaggio da inviare
            addr: (host, porta) destinazione
        """
        try:
            data = json.dumps(message).encode('utf-8')
            self.socket.sendto(data, addr)
        except Exception as e:
            self.logger.error(f"Errore inviando a {addr}: {e}")
            
    def _ping_node(self, host: str, port: int) -> bool:
        """
        Ping un nodo per verificare se è attivo.
        
        Args:
            host: Hostname o IP
            port: Porta
            
        Returns:
            True se il nodo risponde, False altrimenti
        """
        message = {
            'type': 'PING',
            'node_id': self.node_id,
            'msgid': str(random.randint(0, 1000000))
        }
        
        try:
            self._send_message(message, (host, port))
            
            # Attendi risposta
            self.socket.settimeout(2.0)
            start_time = time.time()
            
            while time.time() - start_time < 2.0:
                try:
                    data, addr = self.socket.recvfrom(4096)
                    if addr[0] == host and addr[1] == port:
                        response = json.loads(data.decode('utf-8'))
                        if (response.get('type') == 'PONG' and 
                            response.get('msgid') == message['msgid']):
                            return True
                except socket.timeout:
                    break
                except:
                    pass
                    
            return False
        finally:
            # Ripristina timeout normale
            self.socket.settimeout(1.0)
            
    def _find_node(self, target_id: str, host: str, port: int) -> List[Dict[str, Any]]:
        """
        Trova i nodi più vicini a target_id contattando un nodo.
        
        Args:
            target_id: ID target
            host: Hostname o IP del nodo da contattare
            port: Porta del nodo
            
        Returns:
            Lista di nodi restituiti
        """
        message = {
            'type': 'FIND_NODE',
            'node_id': self.node_id,
            'target': target_id,
            'msgid': str(random.randint(0, 1000000))
        }
        
        try:
            self._send_message(message, (host, port))
            
            # Attendi risposta
            self.socket.settimeout(2.0)
            start_time = time.time()
            
            while time.time() - start_time < 2.0:
                try:
                    data, addr = self.socket.recvfrom(4096)
                    if addr[0] == host and addr[1] == port:
                        response = json.loads(data.decode('utf-8'))
                        if (response.get('type') == 'NODES' and 
                            response.get('msgid') == message['msgid']):
                            # Aggiorna routing table
                            nodes = response.get('nodes', [])
                            for node in nodes:
                                if 'node_id' in node and 'host' in node and 'port' in node:
                                    self._update_routing_table(
                                        node['node_id'], 
                                        (node['host'], node['port'])
                                    )
                            return nodes
                except socket.timeout:
                    break
                except:
                    pass
                    
            return []
        finally:
            # Ripristina timeout normale
            self.socket.settimeout(1.0)
            
    def _send_store(self, key: str, value: Any, host: str, port: int) -> bool:
        """
        Invia richiesta STORE a un nodo.
        
        Args:
            key: Chiave (hash)
            value: Valore
            host: Hostname o IP del nodo
            port: Porta del nodo
            
        Returns:
            True se confermato, False altrimenti
        """
        message = {
            'type': 'STORE',
            'node_id': self.node_id,
            'key': key,
            'value': value,
            'msgid': str(random.randint(0, 1000000))
        }
        
        try:
            self._send_message(message, (host, port))
            
            # Attendi conferma
            self.socket.settimeout(2.0)
            start_time = time.time()
            
            while time.time() - start_time < 2.0:
                try:
                    data, addr = self.socket.recvfrom(4096)
                    if addr[0] == host and addr[1] == port:
                        response = json.loads(data.decode('utf-8'))
                        if (response.get('type') == 'STORE_OK' and 
                            response.get('msgid') == message['msgid'] and
                            response.get('key') == key):
                            return True
                except socket.timeout:
                    break
                except:
                    pass
                    
            return False
        finally:
            self.socket.settimeout(1.0)
            
    def _send_find_value(self, key: str, host: str, port: int) -> Any:
        """
        Invia richiesta FIND_VALUE a un nodo.
        
        Args:
            key: Chiave (hash)
            host: Hostname o IP del nodo
            port: Porta del nodo
            
        Returns:
            Valore trovato o None
        """
        message = {
            'type': 'FIND_VALUE',
            'node_id': self.node_id,
            'key': key,
            'msgid': str(random.randint(0, 1000000))
        }
        
        try:
            self._send_message(message, (host, port))
            
            # Attendi risposta
            self.socket.settimeout(2.0)
            start_time = time.time()
            
            while time.time() - start_time < 2.0:
                try:
                    data, addr = self.socket.recvfrom(4096)
                    if addr[0] == host and addr[1] == port:
                        response = json.loads(data.decode('utf-8'))
                        
                        # Risposta VALUE
                        if (response.get('type') == 'VALUE' and 
                            response.get('msgid') == message['msgid'] and
                            response.get('key') == key):
                            return response.get('value')
                            
                        # Risposta NODES (valore non trovato)
                        if (response.get('type') == 'NODES' and 
                            response.get('msgid') == message['msgid']):
                            return None
                            
                except socket.timeout:
                    break
                except:
                    pass
                    
            return None
        finally:
            self.socket.settimeout(1.0)
            
    def _maintenance_loop(self) -> None:
        """Loop di manutenzione per refresh bucket e pulizia storage."""
        last_bucket_refresh = [0] * self.ID_BITS
        
        while self.running:
            try:
                # Refresh buckets (uno alla volta, in modo ciclico)
                now = time.time()
                for i in range(self.ID_BITS):
                    # Refresh ogni 3600 secondi (1 ora)
                    if now - last_bucket_refresh[i] > 3600:
                        self._refresh_bucket(i)
                        last_bucket_refresh[i] = now
                        break
                        
                # Rimuovi valori scaduti dallo storage
                self._cleanup_storage()
                
            except Exception as e:
                self.logger.error(f"Errore nel loop di manutenzione: {e}")
                
            time.sleep(10)  # Controlla ogni 10 secondi
            
    def _refresh_bucket(self, bucket_index: int) -> None:
        """
        Aggiorna un bucket contattando un ID casuale nel suo range.
        
        Args:
            bucket_index: Indice del bucket da aggiornare
        """
        # Genera un ID casuale che corrisponde al bucket
        if bucket_index == 0:
            # Bucket 0 è speciale, contiene nodi con ID uguale al nostro
            target_id = self.node_id
        else:
            # Calcola un ID che ha il primo bit diverso nella posizione bucket_index
            prefix = self.node_id[:bucket_index // 4]
            bit_pos = 3 - (bucket_index % 4)
            hex_char = self.node_id[bucket_index // 4]
            hex_val = int(hex_char, 16)
            
            # Cambia il bit alla posizione specificata
            new_hex_val = hex_val ^ (1 << bit_pos)
            new_hex_char = format(new_hex_val, 'x')
            
            # Ricostruisci ID target
            suffix = self.node_id[(bucket_index // 4) + 1:]
            target_id = prefix + new_hex_char + suffix
            
        # Esegui FIND_NODE per questo ID
        with self.buckets_lock:
            bucket = self.buckets[bucket_index]
            if bucket:
                # Contatta un nodo casuale nel bucket
                node = random.choice(bucket)
                host, port = node['addr']
                self._find_node(target_id, host, port)
                
    def _cleanup_storage(self) -> None:
        """Rimuove voci scadute dallo storage."""
        # In questa implementazione semplice non gestiamo scadenze
        pass
        
if __name__ == "__main__":
    # Esempio di utilizzo
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='Nodo DHT (Distributed Hash Table)')
    parser.add_argument('--port', type=int, default=0, help='Porta locale (0=caso)')
    parser.add_argument('--id', help='ID nodo (generato casualmente se non fornito)')
    parser.add_argument('--bootstrap', help='Nodo bootstrap (host:porta)')
    parser.add_argument('--put', nargs=2, metavar=('KEY', 'VALUE'), help='Memorizza KEY=VALUE')
    parser.add_argument('--get', metavar='KEY', help='Recupera valore per KEY')
    parser.add_argument('--lookup', metavar='NODE_ID', help='Cerca nodi vicini a ID')
    args = parser.parse_args()
    
    # Configura logging
    logging.getLogger().setLevel(logging.INFO)
    
    # Crea nodo
    dht = DHTNode(args.id, args.port)
    dht.start()
    
    print(f"Nodo DHT avviato con ID: {dht.node_id}")
    print(f"Porta: {dht.port}")
    
    # Bootstrap
    if args.bootstrap:
        try:
            host, port = args.bootstrap.split(':')
            port = int(port)
            bootstrap_nodes = [(host, port)]
            
            if dht.bootstrap(bootstrap_nodes):
                print(f"Bootstrap completato con {args.bootstrap}")
            else:
                print(f"Bootstrap fallito con {args.bootstrap}")
                
        except Exception as e:
            print(f"Errore nel bootstrap: {e}")
            
    # Operazioni PUT/GET
    if args.put:
        key, value = args.put
        if dht.store(key, value):
            print(f"Memorizzato: {key} = {value}")
        else:
            print(f"Errore memorizzando {key} = {value}")
            
    if args.get:
        value = dht.get(args.get)
        if value is not None:
            print(f"Recuperato: {args.get} = {value}")
        else:
            print(f"Chiave non trovata: {args.get}")
            
    # Lookup nodi
    if args.lookup:
        nodes = dht.find_nodes(args.lookup)
        print(f"Trovati {len(nodes)} nodi vicini a {args.lookup[:8]}...")
        for i, node in enumerate(nodes):
            print(f"  {i+1}. ID: {node['node_id'][:8]}... @ {node['addr'][0]}:{node['addr'][1]}")
            
    # Resta in esecuzione
    try:
        print("\nNodo DHT in esecuzione. Premi Ctrl+C per terminare.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Interruzione...")
    finally:
        dht.stop()
        print("Nodo DHT fermato.") 