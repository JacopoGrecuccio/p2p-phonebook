#!/bin/bash
cd src
CLIENT_NAME="Vitalik"
CLIENT_IP="127.0.0.1"
CLIENT_PORT=9003
CLIENT_PHONEBOOK_FILE="../phonebooks/vitalik_phonebook.json"
CLIENT_PEERS_FILE="../peers-lists/vitalik_peers.json"
source ../run-peer.sh
