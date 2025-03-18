#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import threading
import time
import ipaddress
from typing import Dict, Any, Optional, Tuple, List, Set, Union

# Importa moduli locali
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from discovery.mesh_node import MeshNode
from core.tun_adapter import TunAdapter

# Importa moduli per crittografia
import nacl.secret
import nacl.utils
import nacl.hash
import nacl.signing

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class VpnNode(MeshNode):
    """
    Nodo VPN che integra la mesh P2P con un'interfaccia TUN/TAP
    per creare una rete virtuale privata.
    """
    
    def __init__(self, node_id: Optional[str] = None, 
                local_port: int = 0,
                discovery_server: Tuple[str, int] = None,
                tun_address: str = None,
                network: str = '10.0.0.0/24',
                encryption_key: bytes = None):
        """
        Inizializza un nodo VPN.
        
        Args:
            node_id: ID univoco del nodo (generato automaticamente se None)
            local_port: Porta locale su cui ascoltare
            discovery_server: Server di scoperta (host, porta)
            tun_address: Indirizzo IP dell'interfaccia TUN (se None, assegnato automaticamente)
            network: Rete VPN (CIDR)
            encryption_key: Chiave per crittografia (generata se None)
        """
        super().__init__(node_id, local_port, discovery_server)
        
        # Interfaccia TUN
        self.tun = None
        self.network = ipaddress.ip_network(network)
        self.tun_address = tun_address
        
        # Se indirizzo TUN non fornito, genera automaticamente
        if not self.tun_address:
            # Usa hash dell'ID nodo per generare un indirizzo coerente
            id_hash = nacl.hash.blake2b(self.node_id.encode(), digest_size=4)
            host_id = int.from_bytes(id_hash, byteorder='big') % (2**(32-self.network.prefixlen)-2) + 1
            self.tun_address = str(self.network.network_address + host_id) + '/' + str(self.network.prefixlen)
            
        # Crittografia
        self.encryption_key = encryption_key or nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)
        self.box = nacl.secret.SecretBox(self.encryption_key)
        
        # Per routing
        self.routing_table: Dict[str, str] = {}  # IP -> node_id
        self.ip_mapping: Dict[str, str] = {}  # node_id -> IP
        
        # Estensione capabilities
        self._capabilities.update({
            'vpn': True,
            'vpn_network': str(self.network),
        })
        
        self.logger.info(f"Nodo VPN inizializzato con rete {self.network}")
        
    def start(self) -> None:
        """Avvia il nodo VPN e l'interfaccia TUN."""
        # Prima avvia la rete mesh
        super().start()
        
        # Poi inizializza e avvia l'interfaccia TUN
        self._setup_tun_interface()
        
        self.logger.info("Nodo VPN avviato")
        
    def stop(self) -> None:
        """Ferma il nodo VPN e l'interfaccia TUN."""
        # Ferma l'interfaccia TUN
        if self.tun:
            try:
                self.tun.close()
            except Exception as e:
                self.logger.error(f"Errore chiudendo interfaccia TUN: {e}")
            self.tun = None
            
        # Ferma il nodo mesh
        super().stop()
        
    def _setup_tun_interface(self) -> None:
        """Configura l'interfaccia TUN."""
        try:
            # Crea interfaccia TUN
            self.tun = TunAdapter(mode='tun', address=self.tun_address)
            
            if not self.tun.open():
                self.logger.error("Impossibile aprire interfaccia TUN")
                return
                
            # Registra handler per i pacchetti TUN
            self.tun.start_reading(self._handle_tun_packet)
            
            self.logger.info(f"Interfaccia TUN {self.tun.name} configurata con indirizzo {self.tun_address}")
            
            # Aggiungi al dizionario indirizzi per routing locale
            ip = self.tun_address.split('/')[0]
            self.ip_mapping[self.node_id] = ip
            self.routing_table[ip] = self.node_id
            
        except Exception as e:
            self.logger.error(f"Errore configurando interfaccia TUN: {e}")
            
    def _handle_tun_packet(self, packet: bytes) -> None:
        """
        Gestisce un pacchetto ricevuto dall'interfaccia TUN.
        
        Args:
            packet: Pacchetto IP grezzo
        """
        try:
            # Analisi base dell'header IP per determinare indirizzi
            if len(packet) < 20:
                return  # Pacchetto troppo corto
                
            # Check versione IP
            version = (packet[0] >> 4) & 0xF
            if version != 4:
                self.logger.debug(f"Pacchetto IP versione {version} non supportata")
                return
                
            # Estrai indirizzi sorgente e destinazione
            src_ip = '.'.join(str(b) for b in packet[12:16])
            dst_ip = '.'.join(str(b) for b in packet[16:20])
            
            self.logger.debug(f"Pacchetto da {src_ip} a {dst_ip} ({len(packet)} bytes)")
            
            # Cerca destinazione nella tabella di routing
            if dst_ip in self.routing_table:
                dst_node_id = self.routing_table[dst_ip]
                
                # Cifra il pacchetto
                encrypted = self._encrypt_packet(packet)
                
                # Invia al nodo destinazione
                self._send_vpn_packet(dst_node_id, encrypted)
            else:
                # Se destinazione sconosciuta, broadcast a tutti i peer
                # Questo è inefficiente ma semplice per la dimostrazione
                self.logger.debug(f"Destinazione {dst_ip} sconosciuta, broadcast")
                self._broadcast_vpn_packet(packet)
                
        except Exception as e:
            self.logger.error(f"Errore processando pacchetto TUN: {e}")
            
    def _send_vpn_packet(self, peer_id: str, encrypted_packet: bytes) -> bool:
        """
        Invia un pacchetto VPN cifrato a un peer specifico.
        
        Args:
            peer_id: ID del peer destinazione
            encrypted_packet: Pacchetto cifrato
            
        Returns:
            True se inviato con successo, False altrimenti
        """
        message = {
            'action': 'vpn_packet',
            'node_id': self.node_id,
            'data': encrypted_packet.hex()  # Converti binario in hex per JSON
        }
        return self.send_to_peer(peer_id, message)
        
    def _broadcast_vpn_packet(self, packet: bytes) -> None:
        """
        Invia un pacchetto a tutti i peer attivi.
        
        Args:
            packet: Pacchetto da inviare
        """
        # Cifra il pacchetto
        encrypted = self._encrypt_packet(packet)
        
        # Invia a tutti i peer attivi
        active_peers = self.get_active_peers()
        for peer_id in active_peers:
            self._send_vpn_packet(peer_id, encrypted)
            
    def _encrypt_packet(self, packet: bytes) -> bytes:
        """
        Cifra un pacchetto con la chiave di sessione.
        
        Args:
            packet: Pacchetto in chiaro
            
        Returns:
            Pacchetto cifrato
        """
        try:
            nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
            encrypted = self.box.encrypt(packet, nonce)
            return encrypted
        except Exception as e:
            self.logger.error(f"Errore cifrando pacchetto: {e}")
            raise
            
    def _decrypt_packet(self, encrypted: bytes) -> bytes:
        """
        Decifra un pacchetto.
        
        Args:
            encrypted: Pacchetto cifrato
            
        Returns:
            Pacchetto in chiaro
        """
        try:
            decrypted = self.box.decrypt(encrypted)
            return decrypted
        except Exception as e:
            self.logger.error(f"Errore decifrando pacchetto: {e}")
            raise
            
    def _handle_message(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """Estende la gestione messaggi per pacchetti VPN."""
        if 'action' not in message:
            return
            
        action = message['action']
        
        # Gestisci messaggi VPN specifici
        if action == 'vpn_packet' and self.tun:
            self._handle_vpn_packet(message, addr)
        elif action == 'vpn_route_update':
            self._handle_route_update(message, addr)
        else:
            # Delega alla classe base
            super()._handle_message(message, addr)
            
    def _handle_vpn_packet(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """
        Gestisce un pacchetto VPN cifrato ricevuto.
        
        Args:
            message: Messaggio contenente il pacchetto
            addr: Indirizzo del mittente
        """
        if 'data' not in message or 'node_id' not in message:
            return
            
        try:
            # Converti da hex a binario
            encrypted = bytes.fromhex(message['data'])
            
            # Decifra
            packet = self._decrypt_packet(encrypted)
            
            # Analisi IP per aggiornare routing
            if len(packet) >= 20:
                # Estrai indirizzo sorgente
                src_ip = '.'.join(str(b) for b in packet[12:16])
                
                # Aggiorna routing table
                peer_id = message['node_id']
                if peer_id not in self.ip_mapping or self.ip_mapping[peer_id] != src_ip:
                    self.ip_mapping[peer_id] = src_ip
                    self.routing_table[src_ip] = peer_id
                    self.logger.info(f"Aggiornata route: {src_ip} -> {peer_id}")
            
            # Invia pacchetto all'interfaccia TUN
            if self.tun:
                self.tun.write(packet)
                
        except Exception as e:
            self.logger.error(f"Errore processando pacchetto VPN da {addr}: {e}")
            
    def _handle_route_update(self, message: Dict[str, Any], addr: Tuple[str, int]) -> None:
        """
        Gestisce un aggiornamento di routing.
        
        Args:
            message: Messaggio contenente informazioni di routing
            addr: Indirizzo del mittente
        """
        if 'node_id' not in message or 'routes' not in message:
            return
            
        peer_id = message['node_id']
        routes = message['routes']
        
        for ip, node in routes.items():
            # Non aggiungere route per i nodi locali
            if node == self.node_id:
                continue
                
            # Aggiorna routing
            self.routing_table[ip] = node
            
        self.logger.info(f"Aggiornate {len(routes)} routes da {peer_id}")
        
    def _send_route_updates(self) -> None:
        """Invia aggiornamenti di routing ai peer."""
        message = {
            'action': 'vpn_route_update',
            'node_id': self.node_id,
            'routes': self.routing_table
        }
        
        active_peers = self.get_active_peers()
        for peer_id in active_peers:
            self.send_to_peer(peer_id, message)
            
        self.logger.info(f"Inviate {len(self.routing_table)} routes a {len(active_peers)} peer")
        
    def _maintenance_loop(self) -> None:
        """Estende il loop di manutenzione con aggiornamenti routing."""
        last_route_update = 0
        
        while self.running:
            try:
                # Chiamata al loop base
                super()._maintenance_loop()
                
                # Aggiornamenti di routing periodici
                now = time.time()
                if now - last_route_update > 30:  # Ogni 30 secondi
                    self._send_route_updates()
                    last_route_update = now
                    
            except Exception as e:
                self.logger.error(f"Errore nel loop di manutenzione VPN: {e}")
                
            time.sleep(5)
            
    def get_routing_table(self) -> Dict[str, str]:
        """Restituisce la tabella di routing corrente."""
        return self.routing_table.copy()
        
    def get_encryption_key_hex(self) -> str:
        """Restituisce la chiave di crittografia in formato hex."""
        return self.encryption_key.hex()
        
if __name__ == "__main__":
    # Esempio d'uso
    import argparse
    
    parser = argparse.ArgumentParser(description='Nodo VPN Mesh')
    parser.add_argument('--id', help='ID del nodo (generato casualmente se non fornito)')
    parser.add_argument('--port', type=int, default=0, help='Porta locale (0=caso)')
    parser.add_argument('--server', default='127.0.0.1:8000', help='Server di scoperta (host:porta)')
    parser.add_argument('--tun', help='Indirizzo interfaccia TUN (es. 10.0.0.1/24)')
    parser.add_argument('--network', default='10.0.0.0/24', help='Rete VPN (CIDR)')
    parser.add_argument('--key', help='Chiave di crittografia (hex, generata se non fornita)')
    args = parser.parse_args()
    
    # Converti l'indirizzo del server in (host, porta)
    server_parts = args.server.split(':')
    if len(server_parts) != 2:
        print("Formato server non valido. Usa 'host:porta'")
        sys.exit(1)
    discovery_server = (server_parts[0], int(server_parts[1]))
    
    # Chiave di crittografia
    encryption_key = None
    if args.key:
        try:
            encryption_key = bytes.fromhex(args.key)
            if len(encryption_key) != nacl.secret.SecretBox.KEY_SIZE:
                print(f"Lunghezza chiave non valida, deve essere {nacl.secret.SecretBox.KEY_SIZE*2} caratteri hex")
                sys.exit(1)
        except ValueError:
            print("Formato chiave non valido, usa hex")
            sys.exit(1)
    
    # Configura logging
    logging.getLogger().setLevel(logging.INFO)
    
    # Crea e avvia il nodo
    node = VpnNode(
        node_id=args.id,
        local_port=args.port,
        discovery_server=discovery_server,
        tun_address=args.tun,
        network=args.network,
        encryption_key=encryption_key
    )
    
    node.start()
    
    print(f"Nodo VPN avviato con ID: {node.node_id}")
    print(f"Indirizzo locale: {node.local_ip}:{node.local_port}")
    print(f"Indirizzo TUN: {node.tun_address}")
    print(f"Chiave crittografia: {node.get_encryption_key_hex()}")
    print("Nota: tutti i nodi devono usare la stessa chiave di rete")
    
    try:
        while True:
            time.sleep(10)
            active_peers = node.get_active_peers()
            if active_peers:
                print(f"Peer attivi ({len(active_peers)}): {', '.join(active_peers)}")
                
            routing = node.get_routing_table()
            if len(routing) > 1:  # Più di solo il nodo locale
                print("Tabella routing:")
                for ip, peer_id in routing.items():
                    print(f"  {ip} -> {peer_id}")
    except KeyboardInterrupt:
        print("Interruzione...")
    finally:
        node.stop()
        print("Nodo fermato.") 