#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Genera una chiave di crittografia adatta per la VPN mesh.
"""

import nacl.secret
import nacl.utils

def generate_key():
    """Genera una chiave di crittografia adatta per NaCl."""
    key = nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)
    return key.hex()

if __name__ == "__main__":
    key = generate_key()
    print("\nNuova chiave VPN generata:")
    print("-" * 40)
    print(key)
    print("-" * 40)
    print("\nUtilizza questa chiave con il parametro --key quando avvii i nodi VPN.")
    print("Esempio:\n  sudo ./run_vpn_node.sh --key", key) 