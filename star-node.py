
import sys
import socket
import threading
import json
import queue
import logging
import time
import base64
import traceback

class packetType:
	Discovery = "Discovery"
	DiscoveryFinal = "DiscoveryFinal"
	RTTsend = "RTTsend"
	RTTSum = "RTTSum"
	Optimal = "Optimal"
	MessageToHub = "MessageToHub"
	MessageToPeers = "MessageToPeers"
	FileToHub = "FileToHub"
	FileToPeers = "FileToPeers"
	HeartBeat = "HeartBeat"
	UpdateOnline = "UpdateOnline"
	UpdatePeers = "UpdatePeers"
	Disconnect = "Disconnect"

	RTTsendACK = "RTTsendACK"
	DiscoveryACK = "DiscoveryACK"
	DiscoveryFinalACK = "DiscoveryFinalACK"
	RTTSumACK = "RTTSumACK"
	OptimalACK = "OptimalACK"
	MessageToHubACK = "MessageToHubACK"
	FileToHubACK = "FileToHubACK"
	HeartBeatACK = "HeartBeatACK"
	UpdateOnlineACK = "UpdateOnlineACK"
	UpdatePeersACK = "UpdatePeersACK"
	DisconnectACK = "DisconnectACK"
	MessageToPeersACK = "MessageToPeersACK"
	FileToPeersACK = "FileToPeersACK"

class starNode:

	def __init__(self):

		localName = sys.argv[1]
		localPort = sys.argv[2]
		pocIP = sys.argv[3]
		pocPort = sys.argv[4]
		n = sys.argv[5]

		self.n = int(n)
		self.hubName = None
		self.hubIP = None
		self.hubPort = None

		# StarNode variables
		self.localName = localName
		self.localIP = socket.gethostbyname('localhost')
		self.localPort = localPort
		self.localID = str(self.localIP) + str(self.localPort)

		# PoC variables
		self.pocName = None
		self.pocIP = pocIP
		self.pocPort = pocPort
		self.pocID = str(self.pocIP) + str(self.pocPort)

		# peers (holds all the stars that this node has found)
		self.peers = dict()
		self.peersLock = threading.Lock()
		self.peersCond = threading.Condition(self.peersLock)
		self.peers[self.localID] = {"name": self.localName, "ip": self.localIP, "port": self.localPort, "rttSum": 0.0, "rtt": 0.0, "rttTimer": 0.0, "rttGlobal": 0.0, "rttCounter": 0, "online": 1, "heartBeatTimer": time.monotonic()}

		# receive queue
		self.receiveQueue = queue.Queue()
		self.receiveQueueLock = threading.Lock()
		self.receiveQueueCond = threading.Condition(self.receiveQueueLock)

		# send queue
		self.sendQueue = queue.Queue()
		self.sendQueueLock = threading.Lock()
		self.sendQueueCond = threading.Condition(self.sendQueueLock)

		self.receiveAckQueue = queue.Queue()
		self.receiveAckQueueLock = threading.Lock()
		self.receiveAckQueueCond = threading.Condition(self.receiveAckQueueLock)

		self.sendAckQueue = queue.Queue()
		self.sendAckQueueLock = threading.Lock()
		self.sendAckQueueCond = threading.Condition(self.sendAckQueueLock)

		# UDP socket
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.socket.bind((self.localIP, int(self.localPort)))

		# global to kill discovery thread
		self.receivedDiscoveryFinal = False

		self.filename = self.localName + "_" + str(self.localIP) + "_" + str(self.localPort) + ".log"
		self.logger = logging.getLogger(__name__)

		logging.basicConfig(filename = self.filename,
		filemode = 'w',
		format = '%(asctime)s %(levelname)-2s %(message)s',
		datefmt='%Y-%m-%d %H:%M:%S',
		level=logging.DEBUG)

		# send queue
		self.numSent = 0
		self.endCounter = 0
		self.disconnectedCounter = 0
		self.endProgram = False
		self.endProgramLock = threading.Lock()
		self.endProgramCond = threading.Condition(self.endProgramLock)

		self.packetInTransit = None
		self.packetInTransitLock = threading.Lock()
		self.packetInTransitCond = threading.Condition(self.packetInTransitLock)

		self.stopWait = False
		self.stopWaitLock = threading.Lock()
		self.stopWaitCond = threading.Condition(self.stopWaitLock)

		# start sending, receiving, and discovery threads
		self.sendingThread = threading.Thread(target=self.sending, name="sendingThread")
		self.sendingThread.daemon = True
		self.sendingThread.start()
		self.receivingThread = threading.Thread(target=self.receiving, name="receivingThread")
		self.receivingThread.daemon = True
		self.receivingThread.start()
		self.discoveryThread = threading.Thread(target=self.discovery, name="discoveryThread")
		self.discoveryThread.daemon = True
		self.discoveryThread.start()
		self.processingThread = threading.Thread(target=self.processing, name="processingThread")
		self.processingThread.daemon = True
		self.processingThread.start()
		self.rttThread = threading.Thread(target=self.rtt, name="rttThread")
		self.rttThread.daemon = True
		self.rttThread.start()
		self.rttSumThread = threading.Thread(target=self.rttSum, name="rttSumThread")
		self.rttSumThread.daemon = True
		self.rttSumThread.start()
		self.optimalThread = threading.Thread(target=self.optimal, name="optimalThread")
		self.optimalThread.daemon = True
		self.optimalThread.start()
		self.broadcastThread = threading.Thread(target=self.broadcast, name="broadcastThread")
		self.broadcastThread.daemon = True
		self.broadcastThread.start()
		self.heartBeatThread = threading.Thread(target=self.heartBeat, name="heartBeatThread")
		self.heartBeatThread.daemon = True
		self.heartBeatThread.start()

		self.processingAckThread = threading.Thread(target=self.processingAck, name="processingAckThread")
		self.processingAckThread.daemon = True
		self.processingAckThread.start()
		self.sendingAckThread = threading.Thread(target=self.sendingAck, name="sendingackThread")
		self.sendingAckThread.daemon = True
		self.sendingAckThread.start()



		while True:
			self.endProgramLock.acquire()
			try:
				if self.endProgram == True:
					sys.exit()
			except Exception as e:
				print(traceback.format_exc())
			finally:
				self.endProgramCond.notify()
				self.endProgramLock.release()
			time.sleep(1)

	def discovery(self):
		terminate = 180
		while terminate > 0 and not self.receivedDiscoveryFinal:
			self.peersLock.acquire()
			try:
				print("discovery")
				self.putIntoSendQueue(packetType.Discovery, self.peers, self.localIP, self.localPort, self.pocIP, self.pocPort)
			except Exception as e:
				print(traceback.format_exc())
				continue
			finally:
				self.peersCond.notify()
				self.peersLock.release()
			terminate -= 5
			time.sleep(5)
		return

	def rtt(self):
		while True:
			# print("rtt")
			# print("rtt acquires " + str(   self.peersLock.acquire()   ))
			self.peersLock.acquire()
			try:
				for id in self.peers.keys():
					if id is not self.localID:
						self.putIntoSendQueue(packetType.RTTsend, None, self.localIP, self.localPort, self.peers[id]["ip"], self.peers[id]["port"])
			except Exception as e:
				print(traceback.format_exc())
			finally:
				self.peersCond.notify()
				self.peersLock.release()
				# print("rtt releases " + str(       self.peersLock.release()     ))
			time.sleep(0.1)

	def rttSum(self):
		while True:
			# print("rttSum")
			RTTSum = 0.0
			# print("rttSum acquires " + str(   self.peersLock.acquire()   ))
			self.peersLock.acquire()
			try:
				for id in self.peers.keys():
					RTTSum += self.peers[id]["rtt"]
					self.peers[self.localID]["rttCounter"] += 1
				self.peers[self.localID]["rttSum"] = RTTSum
				self.peers[self.localID]["rttGlobal"] += RTTSum
				#logging.info("Recalculated RTTsum")
				for id in self.peers.keys():
					if id is not self.localID:
						packet = {"rttSum": RTTSum, "rttGlobal": self.peers[self.localID]["rttGlobal"], "rttCounter": self.peers[self.localID]["rttCounter"]}
						self.putIntoSendQueue(packetType.RTTSum, packet, self.localIP, self.localPort, self.peers[id]["ip"], self.peers[id]["port"])
			except Exception as e:
				print(traceback.format_exc())
			finally:
				self.peersCond.notify()
				self.peersLock.release()
				# print("rttSum releases " + str(       self.peersLock.release()     ))
			time.sleep(0.2)

	def optimal(self):
		hubName = None
		hubIP = None
		hubPort = None
		while True:
			print("optimal")
			leastRTTSum = 10000000000000000000000000000000000000000000
			# print("optimal acquires " + str(   self.peersLock.acquire()   ))
			self.peersLock.acquire()
			try:
				for id in self.peers.keys():
					if self.peers[id]["rttCounter"] == 0:
						self.peers[id]["rttCounter"] += 1
					if (self.peers[id]["rttGlobal"] / self.peers[id]["rttCounter"]) < leastRTTSum and self.peers[id]["online"] == 1:
						leastRTTSum = self.peers[id]["rttGlobal"] / self.peers[id]["rttCounter"]
						hubName = self.peers[id]["name"]
						hubIP = self.peers[id]["ip"]
						hubPort = self.peers[id]["port"]
					self.peers[id]["rttGlobal"] = 0.0
					self.peers[id]["rttCounter"] = 0
				if str(self.hubIP) + str(self.hubPort) != hubIP + hubPort:
					logging.info("New hub selected:" + hubName + " - " + hubIP + " - " + hubPort)
				self.hubName = hubName
				self.hubIP = hubIP
				self.hubPort = hubPort
				#print(self.peers)
				#print(hubPort)
			except Exception as e:
				print(traceback.format_exc())
			finally:
				self.peersCond.notify()
				self.peersLock.release()
				# print("optimal releases " + str(       self.peersLock.release()     ))
			time.sleep(5)


	def heartBeat(self):
		while True:
			print("churn")
			self.peersLock.acquire()
			print("CHURN got lock")
			try:
				# check other nodes timer and mark offline if they havent responded in 15 seconds
				change = False
				for id in self.peers.keys():
					if (str(self.peers[id]["ip"]) + str(self.peers[id]["port"]) != str(self.localIP) + str(self.localPort)):
						if time.monotonic() - self.peers[str(self.localIP)+str(self.localPort)]["heartBeatTimer"] > 30:
							if self.peers[id]["online"] == 1:
								change = True
							self.peers[id]["online"] = 0
				# send changes to other nodes if any were made
				if change == True:
					for id in self.peers.keys():
						if (str(self.peers[id]["ip"]) + str(self.peers[id]["port"]) != str(self.localIP) + str(self.localPort)):
							self.putIntoSendQueue(packetType.UpdateOnline, self.peers, self.localIP, self.localPort, self.peers[id]["ip"], self.peers[id]["port"])
				# send heartbeat packets to all other nodes
				for id in self.peers.keys():
					if (str(self.peers[id]["ip"]) + str(self.peers[id]["port"]) != str(self.localIP) + str(self.localPort)):
						self.putIntoSendQueue(packetType.HeartBeat, None, self.localIP, self.localPort, self.peers[id]["ip"], self.peers[id]["port"])
			except Exception as e:
				print(traceback.format_exc())
				continue
			finally:
				self.peersCond.notify()
				self.peersLock.release()
				print("CHURN released lock")
			time.sleep(3)


	def broadcast(self):
		while True:
			userCommand = input("Star-node command: ")
			try:
				command = userCommand.split(" ")
				if "send" in command[0]:
					if "\"" in command[1]:
						message = "From " + self.localName + ": " + " ".join(command[1:])
						if (str(self.localIP) + str(self.localPort) != str(self.hubIP) + str(self.hubPort)):
							self.putIntoSendQueue(packetType.MessageToHub, message, self.localIP, self.localPort, self.hubIP, self.hubPort)
						else:
							self.peersLock.acquire()
							try:
								for id in self.peers.keys():
									if (str(self.peers[id]["ip"]) + str(self.peers[id]["port"]) != str(self.localIP) + str(self.localPort)):
										self.putIntoSendQueue(packetType.MessageToPeers, message, self.localIP, self.localPort, self.peers[id]["ip"], self.peers[id]["port"])
							except Exception as e:
								print(traceback.format_exc())
								continue
							finally:
								self.peersCond.notify()
								self.peersLock.release()

					else:
						filename = command[1]
						f = open(filename, "rb")
						message = {"filename": filename, "data": str(f.read().decode("latin1"))}
						f.close()
						if (str(self.localIP) + str(self.localPort) != str(self.hubIP) + str(self.hubPort)):
							self.putIntoSendQueue(packetType.FileToHub, message, self.localIP, self.localPort, self.hubIP, self.hubPort)
						else:
							self.peersLock.acquire()
							try:
								for id in self.peers.keys():
									if (str(self.peers[id]["ip"]) + str(self.peers[id]["port"]) != str(self.localIP) + str(self.localPort)):
										self.putIntoSendQueue(packetType.FileToPeers, message, self.localIP, self.localPort, self.peers[id]["ip"], self.peers[id]["port"])
							except Exception as e:
								print(traceback.format_exc())
								continue
							finally:
								self.peersCond.notify()
								self.peersLock.release()

				elif "show-status" in command[0]:
					print("Active nodes:")
					self.peersLock.acquire()
					print("SHOW STATUS got lock")
					try:
						if len(self.peers.keys()) == 1:
							print("No other known active nodes\n")
						else:
							for id in self.peers.keys():
								print(id)
								if self.peers[id]["online"] == 1:
									#if id != str(self.localIP) + str(self.localPort):
									print("Name: ")
									print(self.peers[id]["name"])
									print("RTTSum: ")
									if (self.peers[id]["rttCounter"] == 0):
										print(0)
									else:
										print(self.peers[id]["rttGlobal"] / self.peers[id]["rttCounter"])
									print()

									logging.info("Name: ")
									logging.info(self.peers[id]["name"])
									logging.info("RTTSum: ")
									if (self.peers[id]["rttCounter"] == 0):
										logging.info(0)
									else:
										logging.info(self.peers[id]["rttGlobal"] / self.peers[id]["rttCounter"])
									print()
							if self.hubName == None:
								print("Hub Node: " + self.localName)
								print()
								logging.info("Hub Node: " + self.localName)
							else:
								print("Hub Node: " + self.hubName)
								print()
					except Exception as e:
						print(traceback.format_exc())
						continue
					finally:
						self.peersCond.notify()
						self.peersLock.release()
						print("SHOW STATUS released lock")


				elif "disconnect" in command[0]:
					self.peersLock.acquire()
					try:
						self.peers[str(self.localIP) + str(self.localPort)]["online"] = 0
						for id in self.peers.keys():
							if id != str(self.localIP) + str(self.localPort):
								self.putIntoSendQueue(packetType.Disconnect, self.peers, self.localIP, self.localPort, self.peers[id]["ip"], self.peers[id]["port"])
								if self.peers[id]["online"] == 0:
									self.disconnectedCounter += 1
					except Exception as e:
						print(traceback.format_exc())
						continue
					finally:
						self.peersCond.notify()
						self.peersLock.release()


				elif "show-log" in command[0]:
					f = open(self.filename, 'r')
					for line in f:
						print(line, end="")
					f.close()
					print()
				else:
					print("Invalid Command")
			except:
				print("Could not execute command. Try Again")
				continue



	def sending(self):
		while True:
			self.numSent = 0
			self.sendQueueLock.acquire()
			self.sendQueueCond.wait_for(lambda: not self.sendQueue.empty())
			self.packetInTransitLock.acquire()
			try:

				if not self.sendQueue.empty():
					packet = self.sendQueue.get()
					packetJson = json.dumps(packet)
					self.packetInTransit = packet
					if "ACK" not in str(packet["type"]):
						self.stopWaitLock.acquire()
						try:
							self.stopWait = True
						except Exception as e:
							print(traceback.format_exc())
						finally:
							self.stopWaitCond.notify()
							self.stopWaitLock.release()
					else:
						packetJson = json.dumps(packet)
						self.putIntoSendACKQueue(packetJson.encode())

			except Exception as e:
				print(traceback.format_exc())
				continue
			finally:
				self.sendQueueCond.notify()
				self.sendQueueLock.release()
				self.packetInTransitCond.notify()
				self.packetInTransitLock.release()

			self.stopWaitLock.acquire()
			try:
				while self.stopWait and self.numSent < 100:
					self.numSent += 1
					if packet["type"] == packetType.Discovery:
						# keep sending peer to poc every 5 seconds
						# until it has received an ACK from poc
						self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
						#print("Sent Discovery Packet")
						logging.info("Sent Discovery Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

					elif packet["type"] == packetType.DiscoveryFinal:
						# send ACK to sender to notify it has received it contact packet AND STOP THE DISCOVERY THREAD
						self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
						#print("Sent Final Discovery Packet")
						logging.info("Sent Final Discovery Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

					elif packet["type"] == packetType.RTTsend:
						# print('sending rtt stuff haha')
						self.peersLock.acquire()
						try:
							self.peers[packet["receiverIP"] + packet["receiverPort"]]["rttTimer"] = time.time()
							packetJson = json.dumps(packet)
							self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
							# print("Sent RTT Packet")
							logging.info("Sent RTT Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])
						except:
							print(traceback.format_exc())
						finally:
							self.peersCond.notify()
							self.peersLock.release()

					elif packet["type"] == packetType.RTTSum:
						self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
						#print("Sent RTTSum Packet")
						logging.info("Sent RTTSum Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

					elif packet["type"] == packetType.MessageToHub:
						self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
						logging.info("Sent Message Packet to Hub : " + packet["receiverIP"] + " - " + packet["receiverPort"])

					elif packet["type"] == packetType.MessageToPeers:
						self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
						#print("Sent Message Packet to peers")
						logging.info("Sent Message Packet to peer : " + packet["receiverIP"] + " - " + packet["receiverPort"])

					elif packet["type"] == packetType.FileToHub:
						print("Sent File Packet to hub")
						self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
						logging.info("Sent Message Packet to Hub : " + packet["receiverIP"] + " - " + packet["receiverPort"])

					elif packet["type"] == packetType.FileToPeers:
						self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
						print("Sent File Packet to peers")
						logging.info("Sent File Packet to peer : " + packet["receiverIP"] + " - " + packet["receiverPort"])

					elif packet["type"] == packetType.HeartBeat:
						self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
						#print("Sent HeartBeat Packet")
						logging.info("Sent HeartBeat Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

					elif packet["type"] == packetType.UpdateOnline:
						self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
						#print("Sent UpdateOnline Packet")
						logging.info("Sent UpdateOnline Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

					elif packet["type"] == packetType.UpdatePeers:
						self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
						#print("Sent UpdatePeers Packet")
						logging.info("Sent UpdatePeers Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

					elif packet["type"] == packetType.Disconnect:
						self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
						#print("Sent Disconnect Packet")
						logging.info("Sent Disconnect Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])
						self.endCounter += 1
						print(self.disconnectedCounter)
						if self.endCounter == (self.n - 1 - self.disconnectedCounter):
							self.endProgramLock.acquire()
							try:
								self.endProgram = True
							except Exception as e:
								print(traceback.format_exc())
							finally:
								self.endProgramCond.notify()
								self.endProgramLock.release()
					elif packet["type"] == packetType.DisconnectACK:
						self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
						#print("Sent Disconnect Packet")
						logging.info("Sent Disconnect Packet ACK to : " + packet["receiverIP"] + " - " + packet["receiverPort"])
			except Exception as e:
				print(traceback.format_exc())
				continue
			finally:
				self.stopWaitCond.notify()
				self.stopWaitLock.release()
			time.sleep(.005)

	def sendingAck(self):
		while True:
			self.sendAckQueueLock.acquire()
			self.sendAckQueueCond.wait_for(lambda: not self.sendAckQueue.empty())
			try:
				if not self.sendAckQueue.empty():
					packet = self.sendAckQueue.get()
					packetJson = json.dumps(packet)
					logging.info(packet)
			except Exception as e:
				print(traceback.format_exc())
				logging.info((traceback.format_exc()))
			finally:
				self.sendAckQueueCond.notify()
				self.sendAckQueueLock.release()

			if packet["type"] == packetType.DiscoveryACK:
				logging.info("inside if statement for DiscoveryACK")
				# send ACK to sender to notify it has received it contact packet AND STOP THE DISCOVERY THREAD
				self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
				#print("Sent Discovery ACK")
				logging.info("Sent DiscveryACK Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

			elif packet["type"] == packetType.DiscoveryFinalACK:
				# send ACK to sender to notify it has received it contact packet AND STOP THE DISCOVERY THREAD
				self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
				#print("Sent Final Discovery Packet")
				logging.info("Sent Final Discovery ACK Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])
			elif packet["type"] == packetType.RTTsendACK:
				self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
				# print("Sent RTT Packet ACK")
				logging.info("Sent RTT Packet ACK to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

			elif packet["type"] == packetType.RTTSumACK:
				self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
				#print("Sent RTTSum Packet")
				logging.info("Sent RTTSum ACK Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

			elif packet["type"] == packetType.MessageToHubACK:
				self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
				logging.info("Sent MessageToHub ACK Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

			elif packet["type"] == packetType.MessageToPeersACK:
				self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
				logging.info("Sent MessageToPeers ACK Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

			elif packet["type"] == packetType.FileToHubACK:
				self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
				logging.info("Sent File to Hub ACK Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

			elif packet["type"] == packetType.FileToPeersACK:
				self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
				logging.info("Sent File to Peers ACK Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

			elif packet["type"] == packetType.HeartBeatACK:
				self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
				#print("Sent HeartBeatACK Packet")
				logging.info("Sent HeartBeatACK Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

			elif packet["type"] == packetType.UpdateOnlineACK:
				self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
				#print("Sent UpdateOnline Packet")
				logging.info("Sent UpdateOnline ACK Packet to : " + packet["receiverIP"] + " - " + packet["receiverPort"])

			elif packet["type"] == packetType.UpdatePeersACK:
				self.socket.sendto(packetJson.encode(), (packet["receiverIP"], int(packet["receiverPort"])))
				#print("Sent UpdatePeers Packet")
				logging.info("Sent UpdatePeers Packet ACK to : " + packet["receiverIP"] + " - " + packet["receiverPort"])


	def processing(self):
		while True:
			self.receiveQueueLock.acquire()
			self.receiveQueueCond.wait_for(lambda: not self.receiveQueue.empty())
			try:
				if not self.receiveQueue.empty():
					packet = self.receiveQueue.get()
					packet = json.loads(packet.decode())
			except Exception as e:
				print(traceback.format_exc())
				continue
			finally:
				self.receiveQueueCond.notify()
				self.receiveQueueLock.release()

			if "ACK" in str(packet["type"]):
				packetJson = json.dumps(packet)
				self.putReceiveACKQueue(packetJson.encode())

			else:
				if packet["type"] == packetType.Discovery:
					# when Starnode receives discovery packet, it must update its peers list and then send back a discovery ACK
					#print("Received Discovery Packet")
					logging.info("Received Discovery Packet from : " + packet["senderIP"] + " - " + packet["senderPort"])
					# print("Received Discovery Packet from : " + packet["senderIP"] + " - " + packet["senderPort"])
					self.peersLock.acquire()
					try:
						for id in packet["payload"].keys():
							if id is not self.peers.keys():
								self.peers[id] = {"name": packet["payload"][id]["name"], "ip": packet["payload"][id]["ip"], "port": packet["payload"][id]["port"], "rttSum": 0.0, "rtt": 0.0, "rttTimer": 0.0, "rttGlobal": 0.0, "rttCounter": 0, "online": 1, "heartBeatTimer": time.monotonic()}
								logging.info("Discovered new node: " + str(packet["payload"][id]["ip"]) + " - " + str(packet["payload"][id]["port"]))
								# print(self.peers)

						# print('put into send queue')
						self.putIntoSendACKQueue(packetType.DiscoveryACK, None, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])

						if len(self.peers.keys()) == self.n:
							for id in self.peers.keys():
								if id is not self.localID:
									self.putIntoSendQueue(packetType.DiscoveryFinal, self.peers, self.localIP, self.localPort, self.peers[id]["ip"], self.peers[id]["port"])
									#print("Placed Final Discovery Packet into Queue")
									self.receivedDiscoveryFinal = True
					except:
						print(traceback.format_exc())
					finally:
						self.peersCond.notify()
						self.peersLock.release()

				elif packet["type"] == packetType.DiscoveryFinal:
					#print("Received Final Discovery Packet")
					logging.info("Received Final Discovery Packet from : " + packet["senderIP"] + " - " + packet["senderPort"])
					self.peersLock.acquire()
					try:
						for id in packet["payload"].keys():
							if id is not self.peers.keys():
								self.peers[id] = {"name": packet["payload"][id]["name"], "ip": packet["payload"][id]["ip"], "port": packet["payload"][id]["port"], "rttSum": 0.0, "rtt": 0.0, "rttTimer": 0.0, "rttGlobal": 0.0, "rttCounter": 0, "online": 1, "heartBeatTimer": time.monotonic()}
								logging.info("Discovered new node: " + str(packet["payload"][id]["ip"]) + " - " + str(packet["payload"][id]["port"]))
						self.putIntoSendACKQueue(packetType.DiscoveryFinalACK, None, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])
						self.receivedDiscoveryFinal = True
					except Exception as e:
						print(traceback.format_exc())
						continue
					finally:
						self.peersCond.notify()
						self.peersLock.release()

				elif packet["type"] == packetType.RTTsend:
					#print("Received RTTsend packet")
					logging.info("Received RTT request from : " + str(packet["senderIP"]) + " - " + str(packet["senderPort"]))
					self.putIntoSendACKQueue(packetType.RTTsendACK, None, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])

				elif packet["type"] == packetType.RTTSum:
					#print("Received RTTSum packet")
					logging.info("Received RTTsum Packet from : " + packet["senderIP"] + " - " + packet["senderPort"])
					self.peersLock.acquire()
					try:
						self.putIntoSendACKQueue(packetType.RTTSumACK, None, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])
						if (packet["senderIP"] + packet["senderPort"]) in self.peers.keys():
							self.peers[packet["senderIP"] + packet["senderPort"]]["rttSum"] = packet["payload"]["rttSum"]
							self.peers[packet["senderIP"] + packet["senderPort"]]["rttGlobal"] += packet["payload"]["rttGlobal"]
							self.peers[packet["senderIP"] + packet["senderPort"]]["rttCounter"] += packet["payload"]["rttCounter"]
							logging.info("Updated RTT sum for : " + str(packet["senderIP"]) + " - " + str(packet["senderPort"]))
					except Exception as e:
						print(traceback.format_exc())
						continue
					finally:
						self.peersCond.notify()
						self.peersLock.release()

				elif packet["type"] == packetType.MessageToHub:
					print("Received Message Packet as hub")
					logging.info("Received Message Packet as hub from : " + packet["senderIP"] + " - " + packet["senderPort"])
					self.putIntoSendACKQueue(packetType.MessageToHubACK, None, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])
					self.peersLock.acquire()
					try:
						for id in self.peers.keys():
							if (str(self.peers[id]["ip"]) + str(self.peers[id]["port"]) != str(self.hubIP) + str(self.hubPort) and str(self.peers[id]["ip"]) + str(self.peers[id]["port"]) != str(packet["senderIP"]) + str(packet["senderPort"])):
								self.putIntoSendQueue(packetType.MessageToPeers, packet["payload"], self.localIP, self.localPort, self.peers[id]["ip"], self.peers[id]["port"])
								logging.info("Forwarding Message Packet as hub to : " + str(self.peers[id]["ip"]) + " - " + str(self.peers[id]["port"]))
						print(packet["payload"])
					except Exception as e:
						print(traceback.format_exc())
						continue
					finally:
						self.peersCond.notify()
						self.peersLock.release()

				elif packet["type"] == packetType.MessageToPeers:
					print("Received Message from hub")
					logging.info("Received Message Packet from hub : " + packet["senderIP"] + " - " + packet["senderPort"])
					self.putIntoSendACKQueue(packetType.MessageToPeersACK, None, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])
					print(packet["payload"])

				elif packet["type"] == packetType.FileToHub:
					print("Received File Packet as hub")
					logging.info("Received File Packet as hub from : " + packet["senderIP"] + " - " + packet["senderPort"])
					self.putIntoSendACKQueue(packetType.FileToHubACK, None, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])
					self.peersLock.acquire()
					try:
						for id in self.peers.keys():
							if (str(self.peers[id]["ip"]) + str(self.peers[id]["port"]) != str(self.hubIP) + str(self.hubPort) and str(self.peers[id]["ip"]) + str(self.peers[id]["port"]) != str(packet["senderIP"]) + str(packet["senderPort"])):
								self.putIntoSendQueue(packetType.FileToPeers, packet["payload"], self.localIP, self.localPort, self.peers[id]["ip"], self.peers[id]["port"])
								logging.info("Forwarding File Packet as hub to : " + str(self.peers[id]["ip"]) + " - " + str(self.peers[id]["port"]))
						f = open(packet["payload"]["filename"], "wb")
						f.write(packet["payload"]["data"].encode("latin1"))
						f.close()
						print("Retrieved and Saved File")
					except Exception as e:
						print(traceback.format_exc())
						continue
					finally:
						self.peersCond.notify()
						self.peersLock.release()

				elif packet["type"] == packetType.FileToPeers:
					print("Received File from hub")
					logging.info("Received File Packet from hub : " + packet["senderIP"] + " - " + packet["senderPort"])
					self.putIntoSendACKQueue(packetType.FileToPeersACK, None, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])
					try:
						f = open(packet["payload"]["filename"], "wb")
						f.write(packet["payload"]["data"].encode("latin1"))
						f.close()
						print("Retrieved and Saved File")
					except Exception as e:
						print(traceback.format_exc())
						continue

				elif packet["type"] == packetType.HeartBeat:
					logging.info("Received HeartBeat from : " + packet["senderIP"] + " - " + packet["senderPort"])
					self.putIntoSendACKQueue(packetType.HeartBeatACK, None, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])

				elif packet["type"] == packetType.UpdateOnline:
					logging.info("Received UpdateOnline from : " + packet["senderIP"] + " - " + packet["senderPort"])
					self.peersLock.acquire()
					try:
						self.putIntoSendACKQueue(packetType.UpdateOnlineACK, None, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])
						for id in packet["payload"].keys():
							self.peers[id]["online"] = packet["payload"][id]["online"]
					except Exception as e:
						print(traceback.format_exc())
						continue
					finally:
						self.peersCond.notify()
						self.peersLock.release()

				elif packet["type"] == packetType.UpdatePeers:
					logging.info("Received UpdatePeers from : " + packet["senderIP"] + " - " + packet["senderPort"])
					self.peersLock.acquire()
					try:
						self.putIntoSendACKQueue(packetType.UpdatePeersACK, None, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])
						self.peers = packet["payload"]
					except Exception as e:
						print(traceback.format_exc())
						continue
					finally:
						self.peersCond.notify()
						self.peersLock.release()

				elif packet["type"] == packetType.Disconnect:
					logging.info("Received Disconnect from : " + packet["senderIP"] + " - " + packet["senderPort"])
					self.peersLock.acquire()
					try:
						self.putIntoSendACKQueue(packetType.DisconnectACK, None, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])
						for id in packet["payload"].keys():
							self.peers[id]["online"] = packet["payload"][id]["online"]
					except Exception as e:
						print(traceback.format_exc())
						continue
					finally:
						self.peersCond.notify()
						self.peersLock.release()


	def processingAck(self):
		while True:
			self.receiveAckQueueLock.acquire()
			self.receiveAckQueueCond.wait_for(lambda: not self.receiveAckQueue.empty())
			try:
				if not self.receiveAckQueue.empty():
					packet = self.receiveAckQueue.get()
					packet = json.loads(packet.decode())
			except Exception as e:
				print(traceback.format_exc())
				continue
			finally:
				self.receiveAckQueueCond.notify()
				self.receiveAckQueueLock.release()

			self.stopWaitLock.acquire()
			self.packetInTransitLock.acquire()
			try:

				while self.stopWait == True:
					if str(self.packetInTransit["type"])+"ACK" != str(packet["type"]):
						packet = json.dumps(packet)
						self.putReceiveACKQueue(packet.encode())
						self.receiveAckQueueLock.acquire()
						self.receiveAckQueueCond.wait_for(lambda: not self.receiveAckQueue.empty())
						try:
							if not self.receiveAckQueue.empty():
								packet = self.receiveAckQueue.get()
								packet = json.loads(packet.decode())

						except Exception as e:
				 			print(traceback.format_exc())
						finally:
							self.receiveAckQueueCond.notify()
							self.receiveAckQueueLock.release()
					else:
						self.stopWait = False

			except Exception as e:
	 			print(traceback.format_exc())
			finally:
				self.stopWaitCond.notify()
				self.stopWaitLock.release()
				self.packetInTransitCond.notify()
				self.packetInTransitLock.release()

			if packet["type"] == packetType.DiscoveryACK:
				#print("Received Discovery ACK")
				logging.info("Received Discovery ACK : " + packet["senderIP"] + " - " + packet["senderPort"])

			elif packet["type"] == packetType.DiscoveryFinalACK:
				#print("Received Discovery ACK")
				logging.info("Received Final Discovery ACK : " + packet["senderIP"] + " - " + packet["senderPort"])

			elif packet["type"] == packetType.RTTsendACK:
				#print("Received RTTsendACK packet")
				logging.info("Received RTT response from : " + str(packet["senderIP"]) + " - " + str(packet["senderPort"]))
				self.peersLock.acquire()
				try:
					endTime = time.time()
					totalTime = endTime - (self.peers[packet["senderIP"] + packet["senderPort"]]["rttTimer"])
					# print((self.peers[packet["senderIP"] + packet["senderPort"]]["rttTimer"]))
					# print(endTime)
					# print(totalTime)
					self.peers[packet["senderIP"] + packet["senderPort"]]["rtt"] = totalTime
					# print(self.peers)
				except Exception as e:
					print(traceback.format_exc())
					continue
				finally:
					self.peersCond.notify()
					self.peersLock.release()

			elif packet["type"] == packetType.RTTSumACK:
				#print("Received Discovery ACK")
				logging.info("Received RTTSum ACK : " + packet["senderIP"] + " - " + packet["senderPort"])

			elif packet["type"] == packetType.MessageToHubACK:
				logging.info("Received MessageTo Hub ACK from : " + packet["senderIP"] + " - " + packet["senderPort"])

			elif packet["type"] == packetType.MessageToPeersACK:
				logging.info("Received Message To peers ACK from : " + packet["senderIP"] + " - " + packet["senderPort"])

			elif packet["type"] == packetType.FileToHubACK:
				logging.info("Received File to hub ACK from : " + packet["senderIP"] + " - " + packet["senderPort"])

			elif packet["type"] == packetType.FileToPeersACK:
				logging.info("Received File to peers ACK from : " + packet["senderIP"] + " - " + packet["senderPort"])

			elif packet["type"] == packetType.HeartBeatACK:
				logging.info("Received HeartBeatACK from : " + packet["senderIP"] + " - " + packet["senderPort"])
				self.peersLock.acquire()
				try:
					self.peers[str(packet["senderIP"])+str(packet["senderPort"])]["heartBeatTimer"] = time.monotonic()
					if self.peers[str(packet["senderIP"])+str(packet["senderPort"])]["online"] == 0:
						self.peers[str(packet["senderIP"])+str(packet["senderPort"])]["online"] = 1
						self.putIntoSendQueue(packetType.UpdatePeers, self.peers, self.localIP, self.localPort, packet["senderIP"], packet["senderPort"])
						for id in self.peers.keys():
							self.putIntoSendQueue(packetType.UpdateOnline, self.peers, self.localIP, self.localPort, self.peers[id]["ip"], self.peers[id]["port"])
				except Exception as e:
					print(traceback.format_exc())
					continue
				finally:
					self.peersCond.notify()
					self.peersLock.release()

			elif packet["type"] == packetType.UpdateOnlineACK:
				logging.info("Received UpdateOnline ACK from : " + packet["senderIP"] + " - " + packet["senderPort"])

			elif packet["type"] == packetType.UpdatePeersACK:
				logging.info("Received UpdatePeers ACK from : " + packet["senderIP"] + " - " + packet["senderPort"])

			elif packet["type"] == packetType.DisconnectACK:
				logging.info("Received Disconnect ACK from : " + packet["senderIP"] + " - " + packet["senderPort"])


	def receiving(self):
		while True:
			try:
				packet, address = self.socket.recvfrom(64000)
				self.putReceiveQueue(packet)
			except Exception as e:
				print(traceback.format_exc())
				continue


	def putIntoSendQueue(self, packetType, payload, senderIP, senderPort, receiverIP, receiverPort):
		packet = {"type" : packetType, "payload" : payload, "senderIP" : senderIP, "senderPort" : senderPort, "receiverIP" : receiverIP, "receiverPort" : receiverPort}
		self.sendQueueLock.acquire()
		try:
			self.sendQueue.put(packet)
		except Exception as e:
			print(traceback.format_exc())
		finally:
			self.sendQueueCond.notify()
			self.sendQueueLock.release()

	def putSendQueue(self, packet):
		self.sendQueueLock.acquire()
		try:
			self.sendQueue.put(packet)
		except Exception as e:
			print(traceback.format_exc())
		finally:
			self.sendQueueCond.notify()
			self.sendQueueLock.release()

	def putIntoReceiveQueue(self, packetType, payload, senderIP, senderPort, receiverIP, receiverPort):
		packet = {"type" : packetType, "payload" : payload, "senderIP" : senderIP, "senderPort" : senderPort, "receiverIP" : receiverIP, "receiverPort" : receiverPort}
		self.receiveQueueLock.acquire()
		try:
			self.receiveQueue.put(packet)
		except Exception as e:
			print(traceback.format_exc())
		finally:
			self.receiveQueueCond.notify()
			self.receiveQueueLock.release()

	def putReceiveQueue(self, packet):
		self.receiveQueueLock.acquire()
		try:
			self.receiveQueue.put(packet)
		except Exception as e:
			print(traceback.format_exc())
		finally:
			self.receiveQueueCond.notify()
			self.receiveQueueLock.release()

	def putIntoReceiveACKQueue(self, packetType, payload, senderIP, senderPort, receiverIP, receiverPort):
		packet = {"type" : packetType, "payload" : payload, "senderIP" : senderIP, "senderPort" : senderPort, "receiverIP" : receiverIP, "receiverPort" : receiverPort}
		self.receiveAckQueueLock.acquire()
		try:
			self.receiveAckQueue.put(packet)
		except Exception as e:
			print(traceback.format_exc())
		finally:
			self.receiveAckQueueCond.notify()
			self.receiveAckQueueLock.release()

	def putReceiveACKQueue(self, packet):
		self.receiveAckQueueLock.acquire()
		try:
			self.receiveAckQueue.put(packet)
		except Exception as e:
			print(traceback.format_exc())
		finally:
			self.receiveAckQueueCond.notify()
			self.receiveAckQueueLock.release()

	def putIntoSendACKQueue(self, packetType, payload, senderIP, senderPort, receiverIP, receiverPort):
		packet = {"type" : packetType, "payload" : payload, "senderIP" : senderIP, "senderPort" : senderPort, "receiverIP" : receiverIP, "receiverPort" : receiverPort}
		self.sendAckQueueLock.acquire()
		try:
			self.sendAckQueue.put(packet)
		except Exception as e:
			print(traceback.format_exc())
		finally:
			self.sendAckQueueCond.notify()
			self.sendAckQueueLock.release()

	def putSendQueue(self, packet):
		self.sendAckQueueLock.acquire()
		try:
			self.sendAckQueue.put(packet)
		except Exception as e:
			print(traceback.format_exc())
		finally:
			self.sendAckQueueCond.notify()
			self.sendAckQueueLock.release()





if __name__ == '__main__':
	node = starNode()
