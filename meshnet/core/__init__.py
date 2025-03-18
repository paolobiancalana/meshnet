#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Core module per i componenti principali di MeshNet.

Questo modulo contiene i componenti base della rete mesh:
- Node: Il nodo base per la comunicazione P2P
- TunAdapter: Interfaccia di rete virtuale (TUN/TAP)
- VpnNode: Nodo che integra la rete P2P con interfaccia virtuale
"""

from .node import Node
from .tun_adapter import TunAdapter
from .vpn_node import VpnNode

__all__ = ['Node', 'TunAdapter', 'VpnNode'] 