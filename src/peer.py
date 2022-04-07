import json
import socket
import argparse
import logging
import sys
import random
import threading
from logging import Formatter
from logging.handlers import RotatingFileHandler


#-------------------------------------------------------------------------------
# Utility functions
#-------------------------------------------------------------------------------

def setup_logging():
    """
        \brief Set-up a formatted logger instance.
    """
    log_console_format = "[%(levelname)s]: %(message)s"

    # Main logger
    main_logger = logging.getLogger()
    main_logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(Formatter(log_console_format))
    main_logger.addHandler(console_handler)

    return main_logger

#-------------------------------------------------------------------------------
# Data-models
#-------------------------------------------------------------------------------

# PhonebookEntry
#-------------------------------------------------------------------------------
class PhonebookEntry:
    """
        \brief Model of a simple phonebook entry
    """

    def __init__(self,name="",number=""):
        """
            \brief Constructor
        """
        self.name=name
        self.number=number

    def loadFromDict(self,entryDict):
        """
            \brief Loads PhonebookEntry fields from a Python dicitonary
        """
        self.name=entryDict["name"]
        self.number=entryDict["number"]

    def loadFromJson(self,jsonObbj):
        """
            \brief Loads PhonebookEntry fields from a JSON string
        """
        entryDict=json.loads(jsonObbj)
        self.name=entryDict["name"]
        self.number=entryDict["number"]

    def __str__(self):
        """
            \brief __str__ built-in method override
        """
        return json.dumps({
            "name" : self.name,
            "number" : self.number
        })

# Phonebook
#-------------------------------------------------------------------------------
class Phonebook:
    """
        \brief Model of a simple phonebook
    """

    def __init__(self,logger):
        """
            \brief Constructor
        """
        self.book={}
        self.logger=logger

    def loadDataFromJsonFile(self,jsonFile):
        """
            \brief Load phonebook entries from a given file in JSON format
            \note See phonebook/example_phonebook.json for details about file's
                  format
        """
        with open(jsonFile,"r") as f:
            bookDict=json.load(f)
            self.logger.info("Loading phonebook entries from file: {}".format(jsonFile))
            for entry in bookDict["entries"]:
                pbEntry=PhonebookEntry()
                pbEntry.loadFromDict(entry)
                self.book[pbEntry.name]=pbEntry
                self.logger.info("Loaded entry: {}".format(str(pbEntry)))

    def addEntry(self,entry):
        """
            \brief Add a PhonebookEntry object to the Phonebook
        """
        self.book[entry.name]=entry

    def printme(self):
        """
            \brief Pretty print of the whole phonebook
        """
        for e in self.book:
            print(str(e))

    def lookup(self,contactName):
        """
            \brief Check if a given contactName is present in the Phonebook
        """
        return self.book[contactName] if (contactName in self.book) else None


# ContactLookupRequest
#-------------------------------------------------------------------------------
class ContactLookupRequest:
    """
        \brief Model of a protocol message of type ContactLookupRequest
    """

    def __init__(self,contactName=None,timeout=None):
        """
            \brief Constructor
        """
        self.contactName=contactName
        self.timeout=timeout
        self.requestId=random.randint(1,10**6)

    def loadFromDict(self,reqDict):
        """
            \brief Load model's fields from a Python dictionary
        """
        self.contactName=reqDict["contactName"]
        self.timeout=reqDict["timeout"]
        self.requestId=reqDict["requestId"]

    def __str__(self):
        """
            \brief __str__ built-in method override
        """
        return json.dumps({
            "requestId" : self.requestId,
            "timeout" : self.timeout,
            "contactName" : self.contactName
        })


# ContactLookupResponse
#-------------------------------------------------------------------------------
class ContactLookupResponse:
    """
        \brief Model of a protocol message of type ContactLookupResponse
    """

    def __init__(self,requestId,contact):
        """
            \brief Constructor
        """
        self.requestId=requestId
        self.contact=contact

    def parseFromJson(jsonObj):
        """
            \brief Loads model's fields from a JSON string
        """
        respDict=json.loads(jsonObj)
        self.requestId=respDict["requestId"]
        self.contact=contact

    def __str__(self):
        """
            \brief __str__ built-in method override
        """
        return json.dumps({
            "requestId" : self.requestId,
            "contact" : None if self.contact==None else str(self.contact)
        })

#-------------------------------------------------------------------------------
# Application Global variables
#-------------------------------------------------------------------------------

# Client parameters
#-------------------------------------------------------------------------------
CLIENT_NAME=""
CLIENT_IP=""
CLIENT_PORT=9000
CLIENT_PHONEBOOK=""
CLIENT_PEERS=""

# Application console logger
#-------------------------------------------------------------------------------
appLogger = setup_logging()

# List of known peers
#-------------------------------------------------------------------------------
PEERS=[]

# Reuqests pools
#-------------------------------------------------------------------------------
"""
    SENT_REQUESTS_POOL
    \brief Holds all the requests sent by the client. This is used for avoiding
           possible loops that can happen during peer-request-forewarding process
"""
SENT_REQUESTS_POOL=[]

"""
    RESOLVED_REQUESTS_POOL
    \brief Hold all the resolved requests (success/unsuccess) for avoiding
            to process the same request multiple times due to possible duplicates
            during peer-request-forewarding process
"""
RESOLVED_REQUESTS_POOL=[]


# UDP Sockets
#-------------------------------------------------------------------------------

"""
    clientListenerSocket
    \brief This is used by the application to always listen for requests coming
            from other peers

    clientSenderSocket
    \brief This is used by the application to send requests to other peers
            (when necessary)
"""
clientSenderSocket=socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
clientListenerSocket=socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

# Phonebook
#-------------------------------------------------------------------------------
"""
    phoneBook
    \brief A Phonebook object instance that holds client's phonebook
"""
phoneBook=Phonebook(appLogger)

# Listener stop-flag
#-------------------------------------------------------------------------------
killListener=False


#-------------------------------------------------------------------------------
# Application functions
#-------------------------------------------------------------------------------

def loadPeersFromJsonfile(jsonFile):
    """
        \brief Loads client's peers from a given JSON file
    """
    with open(jsonFile,"r") as f:
        peersDict=json.load(f)
    for p in peersDict["peersList"]:
        PEERS.append({
            "peerName" : p["peerName"],
            "ipv4" : p["ipv4"],
            "port" : p["port"]
        })
        appLogger.info("Known peer: {}@{}:{}".format(p["peerName"],p["ipv4"],p["port"]))

# Protocol functions
#-------------------------------------------------------------------------------
def wait_and_parse_lookup_response():
    """
        \brief Wait for a response message from a peer and parse it
    """
    try:
        # Wait for the response
        byteAddrRes=clientSenderSocket.recvfrom(4096)
        # Get the message (as string) and the sender's address
        msg=byteAddrRes[0].decode('utf-8')
        sender=byteAddrRes[1]
        # Split over terminator pattern (\r\n) for paring multiple requests that
        # may be arrived
        resps=msg.split('\r\n')
        for resp in resps:
            if resp!="":
                appLogger.info("{} sent a response {}".format(sender,msg))
                # Convert the JSON string to a dictionary
                respDict=json.loads(resp)
                if ("contact" in respDict):
                    if respDict["contact"]!=None:
                        # If we had a valid contact, update client's phonebook
                        appLogger.info("Received contact {}".format(respDict["contact"]))
                        pbEntry=PhonebookEntry()
                        pbEntry.loadFromJson(respDict["contact"])
                        return pbEntry
                    else:
                        appLogger.info("Peer didn't found requested contact")
    except socket.timeout as e:
        appLogger.info("Timeout expired")
    return None

def send_lookup_request_to_peers(contactName):
    """
        \brief Send a ContactLookupRequest message known peers
    """
    # Build the request and put it in SENT_REQUESTS_POOL
    req=ContactLookupRequest(contactName,200)
    appLogger.info("ContactLookupRequest created: {}".format(str(req)))
    SENT_REQUESTS_POOL.append(req.requestId)
    for p in PEERS:
        # Send the request to peer p
        appLogger.info("Sending request {} to {}".format(req.requestId,p["peerName"]))
        clientSenderSocket.sendto(str(req).encode('utf-8')+b"\r\n",(p["ipv4"],p["port"]))
        pbEntry=wait_and_parse_lookup_response()
        if pbEntry!=None:
            # Peer p has what we'are looking for, update client's phonebook and
            # don't proceed to send requests to other peers
            appLogger.info("Adding new phonebook entry: {}".format(str(pbEntry)))
            phoneBook.addEntry(pbEntry)
            break

def foreward_lookup_request_to_peers(req):
    """
        \brief Foreward a ContactLookupRequest received by a peer, to
            all client's known peers
    """
    found = False
    for p in PEERS:
        appLogger.info("Sending request {} to {}".format(req.requestId,p["peerName"]))
        clientSenderSocket.sendto(str(req).encode('utf-8')+b"\r\n",(p["ipv4"],p["port"]))
        pbEntry=wait_and_parse_lookup_response()
        if pbEntry!=None:
            appLogger.info("Adding new phonebook entry: {}".format(str(pbEntry)))
            phoneBook.addEntry(pbEntry)
            found=True
            break
    return found

def request_handler_thread(name,ip,port):
    """
        \brief Reuqests listener thread
    """
    # Open a listener on the socket
    clientListenerSocket.bind((ip,port))
    appLogger.info("Client {} listening at: {}:{}".format(name,ip,port))
    while killListener==False:
        # Wait for requests from peers
        byteAddrRes=clientListenerSocket.recvfrom(4096)
        msg=byteAddrRes[0].decode('utf-8')
        sender=byteAddrRes[1]
        reqs=msg.split('\r\n')
        for req in reqs:
            if req!="":
                appLogger.info("{} sent a contactLookupRequest: {}".format(sender,req))
                reqDict=json.loads(req)
                # Look up for contact name
                if ("contactName" in reqDict) and ("requestId" in reqDict):
                    if reqDict["requestId"] in RESOLVED_REQUESTS_POOL:
                        # Avoid multiple processing of the same request
                        appLogger.info("Request {} already resolved. Skipping".format(reqDict["requestId"]))
                        contact=None
                    elif reqDict["requestId"] in SENT_REQUESTS_POOL:
                        # Avoid loops
                        appLogger.info("Request {} loop detected. Breaking".format(reqDict["requestId"]))
                        contact=None
                    else:
                        # New request. Check for wanted contact in client's local storage, otherwise ask
                        # to client's known peers
                        appLogger.info("Looking up for contact {} in local phonebook".format(reqDict["contactName"]))
                        contact=phoneBook.lookup(reqDict["contactName"])
                        if contact!=None:
                            appLogger.info("Contact {} found: {}".format(reqDict["contactName"],str(contact)))
                        else:
                            appLogger.info("Contact {} not found in local phonebook".format(reqDict["contactName"]))
                            appLogger.info("Asking to peers")
                            req=ContactLookupRequest()
                            req.loadFromDict(reqDict)
                            found=foreward_lookup_request_to_peers(req)
                            if found==True:
                                # One of client's peer has the wanted contact
                                contact=phoneBook.lookup(reqDict["contactName"])
                            else:
                                # None knows this person
                                contact=None
                            RESOLVED_REQUESTS_POOL.append(reqDict["requestId"])
                    # Send the response
                    resp=ContactLookupResponse(reqDict["requestId"],contact)
                    respMsg=str(resp).encode('utf-8')+b"\r\n"
                    appLogger.info("Sending response to {}".format(sender))
                    clientListenerSocket.sendto(respMsg,sender)
                else:
                    appLogger.warning("Malformed request, discarding")


# User-menu functions
#-------------------------------------------------------------------------------
def contact_lookup():
    """
        \brief Looks for a contact whose name is given by the user
    """
    contactName=input("Enter the contact name you are looking for: ")
    if contactName=="":
        print("No name provided")
    else:
        appLogger.info("Looking up for {} locally".format(contactName))
        contact=phoneBook.lookup(contactName)
        if contact==None:
            appLogger.info("Contact {} not found in local storage".format(contactName))
            askPeers=input("Contact {} not found. Should I ask to peers? (y/n): ".format(contactName))
            if askPeers=="y":
                appLogger.info("Looking up for {} in P2P network".format(contactName))
                send_lookup_request_to_peers(contactName)

        else:
            appLogger.info("Contact {} found in local storage".format(contactName))
            print("Contact {}".format(str(contact)))


def print_peers():
    """
        \brief Prints out client's known peers
    """
    for p in PEERS:
        print("{}@{}:{}".format(p["peerName"],p["ipv4"],p["port"]))

def print_user_menu():
    """
        \brief Displays a multi-choice text menu for user operations
    """
    exit=False
    while (not exit):
        print("===========================================")
        print("Chose an action from the list")
        print("===========================================")
        print("1) Lookup for a contact")
        print("2) Print phonebook")
        print("3) Print peers")
        print("4) Close client")
        print("===========================================")
        choice=int(input("Enter your choice [1-4]: "))
        print("===========================================")
        print("")
        if choice==1:
            contact_lookup()
        elif choice==2:
            phoneBook.printme()
        elif choice==3:
            print_peers()
        elif choice==4:
            exit=True
        print("")
        print("===========================================")


def main():
    """
        \brief Application entry-point
    """
    # run fmt python peer.py <client_name> <client_host> <client_port> <phonebook_file> <peers_file>
    if len(sys.argv)<6:
        appLogger.error("Too few arguments")
        return
    CLIENT_NAME=sys.argv[1]
    CLIENT_IP=sys.argv[2]
    CLIENT_PORT=int(sys.argv[3])
    CLIENT_PHONEBOOK=sys.argv[4]
    CLIENT_PEERS=sys.argv[5]

    appLogger.info("Client {} started".format(CLIENT_NAME))
    appLogger.info("Phonebook file: {}".format(CLIENT_PHONEBOOK))
    appLogger.info("Known peers file: {}".format(CLIENT_PEERS))

    phoneBook.loadDataFromJsonFile(CLIENT_PHONEBOOK)

    loadPeersFromJsonfile(CLIENT_PEERS)

    handlerThread=threading.Thread(target=request_handler_thread,args=(CLIENT_NAME,CLIENT_IP,CLIENT_PORT))
    handlerThread.start()

    print_user_menu()
    killListener=True
    handlerThread.join()

if __name__=="__main__":
    main()
