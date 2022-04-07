#!/bin/bash
cd src
CLIENT_NAME="Killer"
CLIENT_IP="127.0.0.1"
CLIENT_PORT=9004
CLIENT_PHONEBOOK_FILE="../phonebooks/killer_phonebook.json"
CLIENT_PEERS_FILE="../peers-lists/killer_peers.json"
source ../run-peer.sh
