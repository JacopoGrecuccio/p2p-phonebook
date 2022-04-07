#!/bin/bash
cd src
CLIENT_NAME="Satoshi"
CLIENT_IP="127.0.0.1"
CLIENT_PORT=9002
CLIENT_PHONEBOOK_FILE="../phonebooks/satoshi_phonebook.json"
CLIENT_PEERS_FILE="../peers-lists/satoshi_peers.json"
source ../run-peer.sh
