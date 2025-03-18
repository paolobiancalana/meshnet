#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import random
import struct
import logging
import time
from typing import Tuple, Optional, List

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Costanti STUN
STUN_SERVERS = [
    ('stun.l.google.com', 19302),
    ('stun1.l.google.com', 19302),
    ('stun2.l.google.com', 19302),
    ('stun3.l.google.com', 19302),
    ('stun4.l.google.com', 19302),
    ('stun.ekiga.net', 3478),
    ('stun.ideasip.com', 3478),
    ('stun.schlund.de', 3478),
    ('stun.stunprotocol.org', 3478),
    ('stun.voiparound.com', 3478),
    ('stun.voipbuster.com', 3478),
    ('stun.voipstunt.com', 3478),
    ('stun.voxgratia.org', 3478)
]

# Tipi di messaggi STUN
STUN_BINDING_REQUEST = 0x0001
STUN_BINDING_RESPONSE = 0x0101
STUN_BINDING_ERROR_RESPONSE = 0x0111

# Tipi di attributi
STUN_ATTR_MAPPED_ADDRESS = 0x0001
STUN_ATTR_XOR_MAPPED_ADDRESS = 0x0020
STUN_ATTR_ERROR_CODE = 0x0009
STUN_ATTR_UNKNOWN_ATTRIBUTES = 0x000A
STUN_ATTR_SOFTWARE = 0x8022
STUN_ATTR_ALTERNATE_SERVER = 0x8023

# Famiglie di indirizzi
STUN_IPV4 = 0x01
STUN_IPV6 = 0x02

class StunClient:
    """
    Client STUN (Session Traversal Utilities for NAT) per determinare 
    l'indirizzo IP e la porta pubblici di un nodo.
    """
    
    def __init__(self, local_port: int = 0, stun_servers: Optional[List[Tuple[str, int]]] = None):
        """
        Inizializza il client STUN.
        
        Args:
            local_port: Porta locale da usare (0 = assegnata dal sistema)
            stun_servers: Lista di server STUN da utilizzare (host, porta)
        """
        self.local_port = local_port
        self.stun_servers = stun_servers or STUN_SERVERS.copy()
        random.shuffle(self.stun_servers)  # Randomizza l'ordine per distribuzione del carico
        
        self.logger = logging.getLogger("StunClient")
        self.socket = None
        self.external_ip = None
        self.external_port = None
        
    def create_socket(self) -> socket.socket:
        """Crea e configura il socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', self.local_port))
        sock.settimeout(2.0)  # 2 secondi di timeout
        return sock
        
    def discover(self) -> Tuple[Optional[str], Optional[int]]:
        """
        Esegue la scoperta dell'indirizzo IP e porta pubblici.
        
        Returns:
            Tupla con (indirizzo_ip, porta) o (None, None) in caso di errore
        """
        if self.socket is None:
            self.socket = self.create_socket()
            
        for server, port in self.stun_servers:
            try:
                self.logger.debug(f"Tentativo con server STUN {server}:{port}")
                external_ip, external_port = self._stun_request(server, port)
                if external_ip and external_port:
                    self.external_ip = external_ip
                    self.external_port = external_port
                    self.logger.info(f"Indirizzo esterno: {external_ip}:{external_port}")
                    return external_ip, external_port
            except Exception as e:
                self.logger.debug(f"Errore con server {server}:{port}: {e}")
                
        self.logger.warning("Impossibile determinare l'indirizzo pubblico con STUN")
        return None, None
    
    def close(self) -> None:
        """Chiude il socket."""
        if self.socket:
            self.socket.close()
            self.socket = None
            
    def _create_stun_request(self) -> bytes:
        """
        Crea un messaggio di richiesta STUN.
        
        Returns:
            Messaggio STUN in formato binario
        """
        # Tipo di messaggio (Binding Request)
        msg_type = STUN_BINDING_REQUEST
        # Lunghezza del corpo (0 per richiesta semplice)
        msg_length = 0
        # Magic cookie (fisso in STUN)
        magic_cookie = 0x2112A442
        # Transaction ID (casuale)
        transaction_id = random.randint(0, 2**96 - 1)
        
        # Formato: 2 byte tipo, 2 byte lunghezza, 4 byte magic cookie, 12 byte transaction ID
        header = struct.pack('>HHI12s', 
                            msg_type, 
                            msg_length,
                            magic_cookie,
                            transaction_id.to_bytes(12, byteorder='big'))
        
        return header
        
    def _parse_stun_response(self, data: bytes) -> Tuple[Optional[str], Optional[int]]:
        """
        Analizza la risposta STUN.
        
        Args:
            data: Dati binari ricevuti
            
        Returns:
            Tupla con (indirizzo_ip, porta) o (None, None) in caso di errore
        """
        if len(data) < 20:  # Header minimo STUN
            return None, None
            
        # Estrai header
        msg_type, msg_length, _ = struct.unpack('>HHI', data[:8])
        
        # Verifica che sia una risposta Binding Success
        if msg_type != STUN_BINDING_RESPONSE:
            return None, None
            
        # Analizza gli attributi
        pos = 20  # Dopo header
        while pos < len(data):
            # Controlla se ci sono abbastanza byte per un attributo
            if pos + 4 > len(data):
                break
                
            attr_type, attr_length = struct.unpack('>HH', data[pos:pos+4])
            attr_value = data[pos+4:pos+4+attr_length]
            
            # Padding a multipli di 4 byte
            padded_length = (attr_length + 3) & ~3
            
            # Cerca attributo MAPPED_ADDRESS o XOR_MAPPED_ADDRESS
            if attr_type == STUN_ATTR_MAPPED_ADDRESS and attr_length >= 8:
                family, port, addr = self._parse_mapped_address(attr_value)
                if family == STUN_IPV4:
                    return addr, port
            elif attr_type == STUN_ATTR_XOR_MAPPED_ADDRESS and attr_length >= 8:
                family, port, addr = self._parse_xor_mapped_address(attr_value)
                if family == STUN_IPV4:
                    return addr, port
                    
            pos += 4 + padded_length
            
        return None, None
        
    def _parse_mapped_address(self, data: bytes) -> Tuple[int, int, str]:
        """
        Analizza un attributo MAPPED_ADDRESS.
        
        Args:
            data: Dati binari dell'attributo
            
        Returns:
            Tupla con (famiglia, porta, indirizzo)
        """
        family = data[1]
        port = struct.unpack('>H', data[2:4])[0]
        
        if family == STUN_IPV4:
            # IPv4
            ip = '.'.join(str(b) for b in data[4:8])
        else:
            # IPv6 (non implementato)
            ip = '::1'
            
        return family, port, ip
        
    def _parse_xor_mapped_address(self, data: bytes) -> Tuple[int, int, str]:
        """
        Analizza un attributo XOR_MAPPED_ADDRESS.
        
        Args:
            data: Dati binari dell'attributo
            
        Returns:
            Tupla con (famiglia, porta, indirizzo)
        """
        family = data[1]
        
        # XOR con la parte alta del magic cookie
        xor_port = struct.unpack('>H', data[2:4])[0] ^ (0x2112 >> 0)
        
        if family == STUN_IPV4:
            # IPv4 XORed con magic cookie
            addr_data = data[4:8]
            xor_mask = struct.pack('>I', 0x2112A442)
            ip_bytes = bytes(a ^ b for a, b in zip(addr_data, xor_mask))
            ip = '.'.join(str(b) for b in ip_bytes)
        else:
            # IPv6 (non implementato)
            ip = '::1'
            
        return family, xor_port, ip
        
    def _stun_request(self, server: str, port: int) -> Tuple[Optional[str], Optional[int]]:
        """
        Esegue una richiesta STUN a un server specifico.
        
        Args:
            server: Nome host del server STUN
            port: Porta del server STUN
            
        Returns:
            Tupla con (indirizzo_ip, porta) o (None, None) in caso di errore
        """
        # Risolvi l'indirizzo IP del server
        try:
            server_ip = socket.gethostbyname(server)
        except socket.gaierror:
            self.logger.warning(f"Impossibile risolvere server STUN: {server}")
            return None, None
            
        # Crea richiesta STUN
        request = self._create_stun_request()
        
        # Invia richiesta
        self.socket.sendto(request, (server_ip, port))
        
        # Attendi risposta
        try:
            data, addr = self.socket.recvfrom(2048)
            return self._parse_stun_response(data)
        except socket.timeout:
            self.logger.debug(f"Timeout attesa risposta da {server}:{port}")
            return None, None
            
if __name__ == "__main__":
    # Esempio d'uso
    logging.getLogger().setLevel(logging.INFO)
    
    print("Test di scoperta STUN...")
    stun = StunClient()
    
    start_time = time.time()
    external_ip, external_port = stun.discover()
    elapsed = time.time() - start_time
    
    if external_ip and external_port:
        print(f"Indirizzo pubblico: {external_ip}:{external_port}")
        print(f"Scoperto in {elapsed:.2f} secondi")
    else:
        print("Impossibile determinare l'indirizzo pubblico") 