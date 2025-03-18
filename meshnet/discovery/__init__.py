#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Discovery module per la scoperta dei peer in MeshNet.

Questo modulo contiene i componenti per la scoperta e la connessione dei peer:
- StunClient: Client STUN per scoprire l'indirizzo IP pubblico
- DiscoveryServer: Server centralizzato per la scoperta dei peer
- MeshNode: Nodo con supporto per scoperta e hole punching
"""

from .stun_client import StunClient
from .discovery_server import DiscoveryServer
# from .mesh_node import MeshNode  # Importato separatamente per evitare cicli di importazione

__all__ = ['StunClient', 'DiscoveryServer'] 