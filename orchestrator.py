#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Orchestratore per MeshNet VPN
============================

Questo script gestisce l'avvio e la configurazione di tutti i componenti del sistema MeshNet VPN:
- Server di discovery
- Nodi VPN
- Configurazione di rete

Supporta sia Windows che macOS/Linux.
"""

import os
import sys
import time
import json
import signal
import argparse
import platform
import threading
import subprocess
import configparser
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

# Configurazione
DEFAULT_CONFIG = {
    "discovery": {
        "port": 8000,
        "bind": "0.0.0.0",
        "external_address": None,  # Per NAT o connessioni esterne
    },
    "vpn": {
        "network": "10.0.0.0/24",
        "port": 0,  # 0 = automatico
        "enable_ipv6": False
    },
    "orchestrator": {
        "web_interface": True,
        "web_port": 8080,
        "log_level": "info"
    }
}

# Variabili globali
running_processes = {}
is_windows = platform.system() == "Windows"
script_dir = Path(os.path.dirname(os.path.abspath(__file__)))

# Utilità
def run_script(script_name: str, args: List[str], is_admin: bool = False) -> subprocess.Popen:
    """Esegue uno script con gli argomenti specificati."""
    
    if is_windows:
        # Windows usa .bat
        if not script_name.endswith(".bat"):
            script_name += ".bat"
            
        cmd = [script_name] + args
        
        if is_admin:
            print(f"NOTA: {script_name} richiede privilegi di amministratore.")
            print("Eseguilo manualmente come amministratore.")
            
        # Su Windows, non possiamo avviare direttamente con privilegi admin
        return subprocess.Popen(cmd)
    else:
        # macOS/Linux usa .sh
        if not script_name.endswith(".sh"):
            script_name += ".sh"
            
        # Assicurati che lo script sia eseguibile
        script_path = script_dir / script_name
        if not script_path.exists():
            raise FileNotFoundError(f"Script non trovato: {script_path}")
            
        os.chmod(script_path, 0o755)
        cmd = [str(script_path)] + args
        
        if is_admin:
            # Su Linux/macOS usiamo sudo
            cmd = ["sudo"] + cmd
            
        return subprocess.Popen(cmd)

def load_config() -> configparser.ConfigParser:
    """Carica la configurazione da file."""
    config = configparser.ConfigParser()
    
    # Carica configurazione predefinita
    for section, options in DEFAULT_CONFIG.items():
        if section not in config:
            config[section] = {}
        for key, value in options.items():
            if value is not None:
                config[section][key] = str(value)
    
    # Cerca file di configurazione nell'ordine:
    config_files = [
        script_dir / "config.local.ini",  # Configurazione locale
        script_dir / "config.ini",        # Configurazione globale
    ]
    
    found = False
    for config_file in config_files:
        if config_file.exists():
            print(f"Carico configurazione da {config_file}")
            config.read(config_file)
            found = True
            break
    
    if not found:
        print("Nessun file di configurazione trovato. Uso impostazioni predefinite.")
        
        # Crea file di configurazione
        with open(script_dir / "config.ini", "w") as f:
            config.write(f)
    
    return config

def save_nodes_info(nodes: Dict[str, Any], filename: str = "nodes.json") -> None:
    """Salva le informazioni sui nodi in un file JSON."""
    with open(script_dir / filename, "w") as f:
        json.dump(nodes, f, indent=2)
        
def load_nodes_info(filename: str = "nodes.json") -> Dict[str, Any]:
    """Carica le informazioni sui nodi da un file JSON."""
    try:
        with open(script_dir / filename, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

class Orchestrator:
    """
    Gestisce il ciclo di vita dei componenti MeshNet VPN.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Inizializza l'orchestratore."""
        self.config = load_config()
        self.processes = {}
        self.nodes_info = load_nodes_info()
        self.setup_environment()
        
    def setup_environment(self) -> None:
        """Configura l'ambiente in base al sistema operativo."""
        if is_windows:
            # Verifica che setup_windows.bat sia stato eseguito
            venv_path = script_dir / "venv"
            if not venv_path.exists():
                print("Ambiente virtuale non trovato. Eseguo setup_windows.bat...")
                setup_proc = subprocess.run([script_dir / "setup_windows.bat"], 
                                           shell=True)
                if setup_proc.returncode != 0:
                    print("ERRORE: Configurazione Windows fallita.")
        else:
            # Su Linux/macOS verificare venv
            venv_path = script_dir / "venv"
            if not venv_path.exists():
                print("Ambiente virtuale non trovato. Creo venv...")
                subprocess.run([sys.executable, "-m", "venv", "venv"])
                
                # Installa dipendenze
                pip_path = venv_path / "bin" / "pip"
                subprocess.run([pip_path, "install", "pynacl", "cryptography", 
                               "flask", "pyroute2", "pytest"])
    
    def start_discovery_server(self) -> None:
        """Avvia il server di discovery."""
        port = self.config["discovery"]["port"]
        bind = self.config["discovery"]["bind"]
        
        print(f"Avvio server di discovery su {bind}:{port}...")
        
        # Costruisci argomenti
        args = [
            "--port", port,
            "--bind", bind
        ]
        
        # Avvia processo
        script_name = "run_discovery_server"
        proc = run_script(script_name, args)
        self.processes["discovery"] = proc
        
        print(f"Server di discovery avviato (PID: {proc.pid})")
        
    def start_vpn_node(self, node_name: str, is_server: bool = False) -> None:
        """
        Avvia un nodo VPN.
        
        Args:
            node_name: Nome del nodo
            is_server: Se True, il nodo fungerà da server VPN
        """
        # Configurazione
        server = self.config["discovery"].get("external_address", "127.0.0.1") + ":" + self.config["discovery"]["port"]
        network = self.config["vpn"]["network"]
        port = self.config["vpn"]["port"]
        
        # Determina indirizzo IP del nodo
        # Per il server usiamo il primo indirizzo disponibile, per i client gli indirizzi successivi
        ip_base = network.split('/')[0]
        ip_parts = ip_base.split('.')
        if is_server:
            # Server: usa .1
            tun_address = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.1"
        else:
            # Client: trova prossimo IP disponibile
            existing_ips = []
            for node_info in self.nodes_info.values():
                if "tun_address" in node_info:
                    existing_ips.append(node_info["tun_address"])
            
            # Trova il primo IP disponibile
            for i in range(2, 254):
                test_ip = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.{i}"
                if test_ip not in existing_ips:
                    tun_address = test_ip
                    break
        
        print(f"Avvio nodo VPN {node_name} (IP: {tun_address})...")
        
        # Costruisci argomenti
        args = [
            "--server", server,
            "--id", node_name,
            "--tun", tun_address,
            "--network", network
        ]
        
        if port != "0":
            args.extend(["--port", port])
        
        # Avvia processo
        script_name = "run_vpn_node"
        proc = run_script(script_name, args, is_admin=True)
        self.processes[f"vpn_{node_name}"] = proc
        
        # Memorizza le informazioni del nodo
        self.nodes_info[node_name] = {
            "type": "server" if is_server else "client",
            "tun_address": tun_address,
            "server": server,
            "pid": proc.pid
        }
        save_nodes_info(self.nodes_info)
        
        print(f"Nodo VPN {node_name} avviato")
    
    def stop_component(self, component_name: str) -> None:
        """Ferma un componente specifico."""
        if component_name in self.processes:
            proc = self.processes[component_name]
            print(f"Arresto {component_name} (PID: {proc.pid})...")
            
            # Termina processo
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Forza chiusura
                proc.kill()
            
            del self.processes[component_name]
    
    def stop_all(self) -> None:
        """Ferma tutti i componenti."""
        for component_name in list(self.processes.keys()):
            self.stop_component(component_name)
    
    def run_interactive(self) -> None:
        """Esegue l'orchestratore in modalità interattiva."""
        print("\n=== MeshNet VPN Orchestrator ===\n")
        
        while True:
            print("\nComandi disponibili:")
            print("1. Avvia server di discovery")
            print("2. Avvia nodo VPN server")
            print("3. Avvia nodo VPN client")
            print("4. Elenca componenti attivi")
            print("5. Arresta componente")
            print("6. Arresta tutto")
            print("0. Esci")
            
            try:
                choice = input("\nScelta: ")
                
                if choice == "1":
                    self.start_discovery_server()
                elif choice == "2":
                    node_name = input("Nome del nodo server [server]: ").strip() or "server"
                    self.start_vpn_node(node_name, is_server=True)
                elif choice == "3":
                    node_name = input("Nome del nodo client [client]: ").strip() or "client"
                    self.start_vpn_node(node_name, is_server=False)
                elif choice == "4":
                    print("\nComponenti attivi:")
                    for name, proc in self.processes.items():
                        status = "In esecuzione" if proc.poll() is None else "Terminato"
                        print(f"- {name} (PID: {proc.pid}): {status}")
                    
                    print("\nNodi configurati:")
                    for name, info in self.nodes_info.items():
                        print(f"- {name}: {info['type']}, IP: {info['tun_address']}")
                elif choice == "5":
                    if not self.processes:
                        print("Nessun componente attivo.")
                        continue
                        
                    print("\nComponenti disponibili:")
                    for i, name in enumerate(self.processes.keys(), 1):
                        print(f"{i}. {name}")
                    
                    comp_idx = int(input("Numero componente da arrestare: ")) - 1
                    comp_name = list(self.processes.keys())[comp_idx]
                    self.stop_component(comp_name)
                elif choice == "6":
                    self.stop_all()
                elif choice == "0":
                    print("Arresto orchestratore...")
                    self.stop_all()
                    break
                else:
                    print("Scelta non valida.")
            except KeyboardInterrupt:
                print("\nInterruzione richiesta. Arresto orchestratore...")
                self.stop_all()
                break
            except Exception as e:
                print(f"Errore: {e}")
    
    def __del__(self) -> None:
        """Pulisce le risorse all'uscita."""
        self.stop_all()

if __name__ == "__main__":
    # Gestione CTRL+C
    def signal_handler(sig, frame):
        print("\nArresto orchestratore...")
        if 'orchestrator' in globals():
            orchestrator.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Avvio orchestratore
    orchestrator = Orchestrator()
    orchestrator.run_interactive() 