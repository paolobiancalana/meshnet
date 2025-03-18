#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import fcntl
import struct
import logging
import threading
import subprocess
import platform
from typing import Optional, Tuple, Callable, Any

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Costanti per interfaccia TUN
TUNSETIFF = 0x400454ca
TUNSETOWNER = 0x400454cc
IFF_TUN = 0x0001
IFF_TAP = 0x0002
IFF_NO_PI = 0x1000

# Mappatura sistemi operativi
SYSTEM_MAPPING = {
    'Darwin': 'macos',
    'Linux': 'linux',
    'Windows': 'windows'
}

class TunAdapter:
    """
    Interfaccia per creare e gestire adattatori TUN/TAP per le reti virtuali.
    Supporta Linux, macOS (con utun) e Windows (con TAP-Windows o /dev/tun).
    """
    
    def __init__(self, 
                 name: Optional[str] = None, 
                 mode: str = 'tun',
                 mtu: int = 1500,
                 address: str = '10.0.0.1/24',
                 persist: bool = False):
        """
        Inizializza un nuovo adattatore TUN/TAP.
        
        Args:
            name: Nome dell'interfaccia (se None, usa nome default del sistema)
            mode: Modalità ('tun' o 'tap')
            mtu: Maximum Transmission Unit
            address: Indirizzo IP/netmask da assegnare all'interfaccia
            persist: Se True, mantiene l'interfaccia tra esecuzioni
        """
        self.name = name
        self.mode = mode.lower()
        self.mtu = mtu
        self.address = address
        self.persist = persist
        
        # Determina sistema operativo
        system = platform.system()
        self.os_type = SYSTEM_MAPPING.get(system, 'unknown')
        
        # File descriptor per l'interfaccia
        self.fd = None
        self.tun_file = None
        self.running = False
        self._read_thread = None
        self._packet_handler = None
        
        self.logger = logging.getLogger("TunAdapter")
        
        # Controlli iniziali
        if self.os_type == 'unknown':
            self.logger.error(f"Sistema operativo non supportato: {system}")
        
        if self.mode not in ['tun', 'tap']:
            self.logger.error(f"Modalità non valida: {self.mode}, usando 'tun'")
            self.mode = 'tun'
            
    def open(self) -> bool:
        """
        Apre/crea l'interfaccia TUN/TAP.
        
        Returns:
            True se operazione riuscita, False altrimenti
        """
        if self.fd is not None:
            self.logger.warning("Interfaccia già aperta")
            return True
        
        method_name = f"_open_{self.os_type}"
        if hasattr(self, method_name):
            method = getattr(self, method_name)
            try:
                return method()
            except Exception as e:
                self.logger.error(f"Errore aprendo interfaccia: {e}")
                return False
        else:
            self.logger.error(f"Apertura non implementata per {self.os_type}")
            return False
    
    def close(self) -> None:
        """Chiude l'interfaccia TUN/TAP."""
        self.running = False
        
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=2.0)
            
        if self.tun_file:
            try:
                self.tun_file.close()
            except Exception as e:
                self.logger.error(f"Errore chiudendo file: {e}")
            self.tun_file = None
                
        if self.fd:
            try:
                os.close(self.fd)
            except Exception as e:
                self.logger.error(f"Errore chiudendo descriptor: {e}")
            self.fd = None
            
        self.logger.info(f"Interfaccia {self.name} chiusa")
            
    def start_reading(self, packet_handler: Callable[[bytes], Any]) -> None:
        """
        Avvia thread per leggere pacchetti dall'interfaccia.
        
        Args:
            packet_handler: Funzione callback per gestire i pacchetti letti
        """
        if not self.fd:
            self.logger.error("Interfaccia non aperta")
            return
            
        self._packet_handler = packet_handler
        self.running = True
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()
        
        self.logger.info(f"Thread lettura avviato per {self.name}")
        
    def write(self, packet: bytes) -> int:
        """
        Scrive un pacchetto sull'interfaccia.
        
        Args:
            packet: Dati da scrivere (senza header)
            
        Returns:
            Numero di byte scritti o -1 in caso di errore
        """
        if not self.fd:
            self.logger.error("Interfaccia non aperta")
            return -1
            
        try:
            if self.tun_file:
                n = self.tun_file.write(packet)
                self.tun_file.flush()
                return n
            else:
                return os.write(self.fd, packet)
        except Exception as e:
            self.logger.error(f"Errore scrivendo pacchetto: {e}")
            return -1
            
    def _read_loop(self) -> None:
        """Loop principale per leggere pacchetti dall'interfaccia."""
        if not self.fd:
            return
            
        buf_size = self.mtu + 64  # Spazio per header
        
        while self.running:
            try:
                if self.tun_file:
                    packet = self.tun_file.read(buf_size)
                else:
                    packet = os.read(self.fd, buf_size)
                    
                if packet and self._packet_handler:
                    self._packet_handler(packet)
            except Exception as e:
                if self.running:
                    self.logger.error(f"Errore leggendo pacchetto: {e}")
                    
    def _open_linux(self) -> bool:
        """
        Apre un'interfaccia TUN/TAP su Linux.
        
        Returns:
            True se operazione riuscita, False altrimenti
        """
        try:
            # Apri il device TUN/TAP
            self.fd = os.open('/dev/net/tun', os.O_RDWR)
            
            # Configura flags
            flags = 0
            if self.mode == 'tun':
                flags |= IFF_TUN
            else:
                flags |= IFF_TAP
                
            flags |= IFF_NO_PI  # No info pacchetto
            
            # Nome interfaccia + flags
            ifr = struct.pack('16sH', 
                             (self.name or '').encode('utf-8').ljust(16, b'\0'), 
                             flags)
            
            # Configura interfaccia
            fcntl.ioctl(self.fd, TUNSETIFF, ifr)
            
            # Estrai nome assegnato
            assigned_name = struct.unpack('16sH', ifr)[0].strip(b'\0').decode('utf-8')
            self.name = assigned_name
            
            # Converti in file Python
            self.tun_file = os.fdopen(self.fd, 'rb+')
            
            # Configura interfaccia di rete
            self._setup_interface_linux()
            
            self.logger.info(f"Interfaccia {self.name} aperta con successo")
            return True
            
        except Exception as e:
            self.logger.error(f"Errore aprendo interfaccia su Linux: {e}")
            if self.fd:
                os.close(self.fd)
                self.fd = None
            return False
            
    def _setup_interface_linux(self) -> bool:
        """
        Configura l'interfaccia di rete su Linux.
        
        Returns:
            True se operazione riuscita, False altrimenti
        """
        try:
            # Estrai indirizzo IP e netmask
            ip_parts = self.address.split('/')
            ip = ip_parts[0]
            netmask = ip_parts[1] if len(ip_parts) > 1 else '24'
            
            # Porta interfaccia up
            subprocess.check_call(['ip', 'link', 'set', self.name, 'up'])
            
            # Assegna indirizzo
            subprocess.check_call(['ip', 'addr', 'add', f"{ip}/{netmask}", 'dev', self.name])
            
            # Imposta MTU
            subprocess.check_call(['ip', 'link', 'set', self.name, 'mtu', str(self.mtu)])
            
            self.logger.info(f"Interfaccia {self.name} configurata con indirizzo {self.address}")
            return True
            
        except Exception as e:
            self.logger.error(f"Errore configurando interfaccia su Linux: {e}")
            return False
            
    def _open_macos(self) -> bool:
        """
        Apre un'interfaccia TUN/TAP su macOS (usando utun).
        
        Returns:
            True se operazione riuscita, False altrimenti
        """
        try:
            # Controlla se l'utente è root
            if os.geteuid() != 0:
                self.logger.error("Sono richiesti privilegi di amministratore (root) per creare interfacce TUN")
                self.logger.error("Esegui il comando con 'sudo'")
                return False
                
            # Usa moduli specifici macOS
            import fcntl
            
            # Controlla modalità supportata
            if self.mode != 'tun':
                self.logger.warning("macOS supporta solo modalità TUN via utun, forzando modalità TUN")
                self.mode = 'tun'
                
            # Su macOS usiamo utun generato dal sistema
            utun_num = None
            if self.name and self.name.startswith('utun'):
                try:
                    utun_num = int(self.name[4:])
                except ValueError:
                    pass
                    
            # Prova ad aprire l'interfaccia
            result = subprocess.run(['ifconfig'], capture_output=True, text=True)
            existing_utuns = []
            for line in result.stdout.splitlines():
                if line.startswith('utun'):
                    existing_utuns.append(line.split(':')[0])
            
            self.logger.info(f"Interfacce utun esistenti: {existing_utuns}")
                    
            # Cerca una utun disponibile
            found_interface = False
            for i in range(10):  # Prova 10 interfacce
                try:
                    interface_path = f'/dev/utun{i}'
                    self.logger.info(f"Tentativo di apertura: {interface_path}")
                    self.fd = os.open(interface_path, os.O_RDWR)
                    self.name = f'utun{i}'
                    found_interface = True
                    self.logger.info(f"Interfaccia {self.name} aperta con successo")
                    break
                except OSError as e:
                    self.logger.debug(f"Errore aprendo {interface_path}: {e}")
                    continue
                    
            if not found_interface:
                self.logger.error("Impossibile trovare o creare interfaccia utun")
                self.logger.error("Verifica di avere i privilegi di root e che le interfacce utun siano disponibili")
                return False
                
            # Converti in file Python
            self.tun_file = os.fdopen(self.fd, 'rb+')
            
            # Configura interfaccia
            result = self._setup_interface_macos()
            if not result:
                self.logger.error("Configurazione interfaccia fallita")
                self.close()
                return False
            
            self.logger.info(f"Interfaccia {self.name} aperta e configurata con successo")
            return True
            
        except Exception as e:
            self.logger.error(f"Errore aprendo interfaccia su macOS: {e}")
            if self.fd:
                os.close(self.fd)
                self.fd = None
            return False
            
    def _setup_interface_macos(self) -> bool:
        """
        Configura l'interfaccia di rete su macOS.
        
        Returns:
            True se operazione riuscita, False altrimenti
        """
        try:
            # Estrai indirizzo IP e netmask
            ip_parts = self.address.split('/')
            ip = ip_parts[0]
            netmask = ip_parts[1] if len(ip_parts) > 1 else '24'
            
            # Converti netmask CIDR a netmask dotted
            if netmask.isdigit():
                cidr = int(netmask)
                mask_bits = (0xffffffff >> (32 - cidr)) << (32 - cidr)
                netmask = '.'.join([str((mask_bits >> i) & 0xff) for i in [24, 16, 8, 0]])
            
            # Porta interfaccia up
            subprocess.check_call(['ifconfig', self.name, 'up'])
            
            # Assegna indirizzo
            subprocess.check_call(['ifconfig', self.name, 'inet', ip, ip, 'netmask', netmask])
            
            # Imposta MTU
            subprocess.check_call(['ifconfig', self.name, 'mtu', str(self.mtu)])
            
            self.logger.info(f"Interfaccia {self.name} configurata con indirizzo {self.address}")
            return True
            
        except Exception as e:
            self.logger.error(f"Errore configurando interfaccia su macOS: {e}")
            return False
            
    def _open_windows(self) -> bool:
        """
        Apre un'interfaccia TUN/TAP su Windows.
        
        Returns:
            True se operazione riuscita, False altrimenti
        """
        try:
            # Windows richiede TAP-Windows driver o altro software dedicato
            # Questo è un semplice esempio che presuppone dei driver già installati
            # In una implementazione reale, dovremmo usare WinTUN o altro
            
            self.logger.error("Supporto Windows non completamente implementato")
            self.logger.info("Per Windows, installa OpenVPN TAP driver o WinTUN")
            return False
            
        except Exception as e:
            self.logger.error(f"Errore aprendo interfaccia su Windows: {e}")
            return False
            
if __name__ == "__main__":
    # Esempio di utilizzo
    import time
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='Test TUN/TAP adapter')
    parser.add_argument('--address', default='10.0.0.1/24', help='Indirizzo IP/netmask')
    parser.add_argument('--name', help='Nome interfaccia')
    parser.add_argument('--mode', default='tun', choices=['tun', 'tap'], help='Modalità')
    args = parser.parse_args()
    
    # Configura logging
    logging.getLogger().setLevel(logging.INFO)
    
    # Funzione di callback
    def handle_packet(packet):
        print(f"Pacchetto ricevuto: {len(packet)} bytes")
        # In un caso reale, qui instradereremmo il pacchetto alla VPN
    
    # Crea interfaccia
    print(f"Creazione interfaccia {args.mode}...")
    adapter = TunAdapter(name=args.name, mode=args.mode, address=args.address)
    
    if not adapter.open():
        print("Impossibile aprire interfaccia")
        sys.exit(1)
        
    print(f"Interfaccia {adapter.name} aperta con successo.")
    print(f"Indirizzo: {adapter.address}")
    
    # Avvia lettura pacchetti
    adapter.start_reading(handle_packet)
    
    print("In ascolto di pacchetti. Premi Ctrl+C per terminare...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Interruzione...")
    finally:
        adapter.close()
        print("Interfaccia chiusa.") 