import json
import socket
import argparse
import logging
import sys
import random
import threading
from logging import Formatter
from logging.handlers import RotatingFileHandler




def setup_logging(log_dir = None):
    log_file_format = "[%(levelname)s] - %(asctime)s - %(name)s - : %(message)s in %(pathname)s:%(lineno)d"
    log_console_format = "[%(levelname)s]: %(message)s"

    # Main logger
    main_logger = logging.getLogger()
    main_logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(Formatter(log_console_format))

    if log_dir != None:
        exp_file_handler = RotatingFileHandler('{}exp_debug.log'.format(log_dir), maxBytes=10**6, backupCount=5)
        exp_file_handler.setLevel(logging.DEBUG)
        exp_file_handler.setFormatter(Formatter(log_file_format))

        exp_errors_file_handler = RotatingFileHandler('{}exp_error.log'.format(log_dir), maxBytes=10**6, backupCount=5)
        exp_errors_file_handler.setLevel(logging.WARNING)
        exp_errors_file_handler.setFormatter(Formatter(log_file_format))
        main_logger.addHandler(exp_file_handler)
        main_logger.addHandler(exp_errors_file_handler)

    main_logger.addHandler(console_handler)

    return main_logger



class PhonebookEntry:

    def __init__(self,name="",number=""):
        self.name=name
        self.number=number

    def loadFromDict(self,entryDict):
        self.name=entryDict["name"]
        self.number=entryDict["number"]

    def loadFromJson(self,jsonObbj):
        entryDict=json.loads(jsonObbj)
        self.name=entryDict["name"]
        self.number=entryDict["number"]

    def __str__(self):
        return json.dumps({
            "name" : self.name,
            "number" : self.number
        })

class Phonebook:

    def __init__(self,logger):
        self.book={}
        self.logger=logger

    def loadDataFromJsonFile(self,jsonFile):
        with open(jsonFile,"r") as f:
            bookDict=json.load(f)
            self.logger.info("Loading phonebook entries from file: {}".format(jsonFile))
            for entry in bookDict["entries"]:
                pbEntry=PhonebookEntry()
                pbEntry.loadFromDict(entry)
                self.book[pbEntry.name]=pbEntry
                self.logger.info("Loaded entry: {}".format(str(pbEntry)))

    def addEntry(self,entry):
        self.book[entry.name]=entry

    def printme(self):
        for e in self.book:
            print(str(e))

    def lookup(self,contactName):
        return self.book[contactName] if (contactName in self.book) else None



#-------------------------------------------------------------------------------


class ContactLookupRequest:

    def __init__(self,contactName=None,timeout=None):
        self.contactName=contactName
        self.timeout=timeout
        self.requestId=random.randint(1,10**6)

    def loadFromDict(self,reqDict):
        self.contactName=reqDict["contactName"]
        self.timeout=reqDict["timeout"]
        self.requestId=reqDict["requestId"]

    def __str__(self):
        return json.dumps({
            "requestId" : self.requestId,
            "timeout" : self.timeout,
            "contactName" : self.contactName
        })


class ContactLookupResponse:

    def __init__(self,requestId,contact):
        self.requestId=requestId
        self.contact=contact

    def parseFromJson(jsonObj):
        respDict=json.loads(jsonObj)
        self.requestId=respDict["requestId"]
        self.contact=contact

    def __str__(self):
        return json.dumps({
            "requestId" : self.requestId,
            "contact" : None if self.contact==None else str(self.contact)
        })

#-------------------------------------------------------------------------------
CLIENT_NAME="Peer"
CLIENT_IP="127.0.0.1"
CLIENT_PORT=9001
CLIENT_PHONEBOOK="./example_entries.json"
CLIENT_PEERS="./example_peers.json"

appLogger = setup_logging()
PEERS=[]
SENT_REQUESTS_POOL=[]
RESOLVED_REQUESTS_POOL=[]
EXPIRED_REQUESTS_POOL=[]
clientSenderSocket=socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
clientListenerSocket=socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
killListener=False
phoneBook=Phonebook(appLogger)

def loadPeersFromJsonfile(jsonFile):
    with open(jsonFile,"r") as f:
        peersDict=json.load(f)
    for p in peersDict["peersList"]:
        PEERS.append({
            "peerName" : p["peerName"],
            "ipv4" : p["ipv4"],
            "port" : p["port"]
        })
        appLogger.info("Known peer: {}@{}:{}".format(p["peerName"],p["ipv4"],p["port"]))

def print_peers():
    for p in PEERS:
        print("{}@{}:{}".format(p["peerName"],p["ipv4"],p["port"]))

def wait_and_parse_lookup_response():
    #clientSenderSocket.settimeout(10)
    try:
        byteAddrRes=clientSenderSocket.recvfrom(4096)
        msg=byteAddrRes[0].decode('utf-8')
        sender=byteAddrRes[1]
        resps=msg.split('\r\n')
        for resp in resps:
            if resp!="":
                appLogger.info("{} sent a response {}".format(sender,msg))
                respDict=json.loads(resp)
                if ("contact" in respDict):
                    if respDict["contact"]!=None:
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
    req=ContactLookupRequest(contactName,200)
    appLogger.info("ContactLookupRequest created: {}".format(str(req)))
    SENT_REQUESTS_POOL.append(req.requestId)
    for p in PEERS:
        appLogger.info("Sending request {} to {}".format(req.requestId,p["peerName"]))
        clientSenderSocket.sendto(str(req).encode('utf-8')+b"\r\n",(p["ipv4"],p["port"]))
        pbEntry=wait_and_parse_lookup_response()
        if pbEntry!=None:
            appLogger.info("Adding new phonebook entry: {}".format(str(pbEntry)))
            phoneBook.addEntry(pbEntry)
            break

def foreward_lookup_request_to_peers(req):
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
    clientListenerSocket.bind((ip,port))
    appLogger.info("Client {} listening at: {}:{}".format(name,ip,port))
    while killListener==False:
        byteAddrRes=clientListenerSocket.recvfrom(4096)
        msg=byteAddrRes[0].decode('utf-8')
        sender=byteAddrRes[1]
        appLogger.info("Message is: {}".format(msg))
        reqs=msg.split('\r\n')
        appLogger.info("Message is: {}".format(reqs))
        for req in reqs:
            if req!="":
                appLogger.info("{} sent a contactLookupRequest: {}".format(sender,req))
                reqDict=json.loads(req)

                # Look up for contact name
                if ("contactName" in reqDict) and ("requestId" in reqDict):
                    if reqDict["requestId"] in RESOLVED_REQUESTS_POOL:
                        # Avoid flooding and loops
                        appLogger.info("Request {} already resolved. Skipping".format(reqDict["requestId"]))
                        contact=None
                    elif reqDict["requestId"] in SENT_REQUESTS_POOL:
                        appLogger.info("Request {} loop detected. Breaking".format(reqDict["requestId"]))
                        contact=None
                    else:
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
                                contact=phoneBook.lookup(reqDict["contactName"])
                            else:
                                contact=None
                            RESOLVED_REQUESTS_POOL.append(reqDict["requestId"])
                    resp=ContactLookupResponse(reqDict["requestId"],contact)
                    respMsg=str(resp).encode('utf-8')+b"\r\n"
                    appLogger.info("Sending response to {}".format(sender))
                    clientListenerSocket.sendto(respMsg,sender)
                else:
                    appLogger.warning("Malformed request, discarding")


def contact_lookup():
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


def print_user_menu():
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
