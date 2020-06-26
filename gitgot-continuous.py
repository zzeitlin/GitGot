#!/usr/bin/env python3
import github
import sys
import time
import logging
import threading
import os
import json


# This thread takes in a file as input, and processes it.
class Inquisitor(threading.Thread):
	# Where to store logging information
	LOGFILE = 'continuous/logs/log.txt'
	# Number of seconds between git queries
	DELAY = 7
	
	def __init__(self, callback=None, callback_args=None, *args, **kwargs):
		#target = kwargs.pop('target')
		target = self.processFile
		filepath = kwargs.pop('filepath')
		token = kwargs.pop('token')
		
		super(Inquisitor, self).__init__(target=self.target_with_callback, *args, **kwargs)
		self.callback = callback
		self.method = target
		self.filepath = filepath
		self.token = token
		self.g = github.Github(self.token)
		self.callback_args = callback_args
		
		# Setup logging
		self.logfh = logging.FileHandler(Inquisitor.LOGFILE)
		self.logfh.setLevel(logging.DEBUG)
		#self.formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
		self.formatter = logging.Formatter('{"datetime": "%(asctime)s", "name":"%(name)s", "result": %(message)s}')
		self.logfh.setFormatter(self.formatter)
		self.logger = logging.getLogger('namehere')
		self.logger.setLevel(logging.DEBUG)
		self.logger.addHandler(self.logfh)
		
	def target_with_callback(self):
		self.method(self.filepath)
		if self.callback is not None:
			self.callback(*self.callback_args)
			
	def processFile(self,filepath):
		with open(filepath, "r") as fp:
			queries = [line.rstrip() for line in fp.readlines()]
		for subquery in queries:
			try:
				query = subquery
				repositories = self.g.search_code(query)
				result = {
					'totalCount': repositories.totalCount,
					'query': query
				}
				self.logger.info(json.dumps(result))
			except github.RateLimitExceededException:
				print("Rate Limit Exceeded on query")
			
			# Delay between queries
			time.sleep(Inquisitor.DELAY)


class InquisitorController():
	
	def __init__(self, tokens=None, maxThreads=None):
		self.threadCount = 0
		if maxThreads is None:
			self.maxThreads = len(tokens)
		else:
			self.maxThreads = maxThreads
		
		# A list of GitHub auth token strings
		self.tokens = tokens
		self.currentTokenIndex = 0

		# A list of file paths
		self.queue = []
		
	def enqueue(self, filepath):
		self.queue.append(filepath)
		print("enqueue() called. curent queue: " + str(self.queue))
		
	def process(self):
		print ("process() called")
		if len(self.queue) > 0 and self.threadCount < self.maxThreads:
			fileToProcess = self.queue.pop(0)
			self.threadCount += 1
			print("processing "+fileToProcess)
			thread = Inquisitor(
				name='inquisitor',
				callback=self.dequeue,
				callback_args=[fileToProcess],
				filepath=fileToProcess,
				token=self.tokens[self.currentTokenIndex]
			)
			thread.start()
			
			# Increment to next token (round-robin)
			self.currentTokenIndex = (self.currentTokenIndex + 1) % len(self.tokens)
			
	def dequeue(self, filepath):
		print("dequeue called: "+str(filepath))
		# Remove from queue
		while filepath in self.queue:
			self.queue.remove(filepath)
		
		# Decrement number of threads
		self.threadCount -= 1
		
		# Delete file
		os.remove(filepath)


# Not using python watchdog as the Thread-calling mechanism above required object-passing to keep things synchronized.
# This is simpler: a single loop.
def main():
	PATH_TO_WATCH = "./continuous/ingestor"
	TOKENFILE = os.path.join(os.getcwd(),"tokenfile")
	tokens = []
	
	with open(TOKENFILE, "r") as fp:
		tokens = [line.rstrip() for line in fp.readlines()]
	controller = InquisitorController(tokens=tokens)
	
	# Ingest existing files

	# Setup the directory watcher
	before = dict ([(f, None) for f in os.listdir (PATH_TO_WATCH)])
	try:
		while True:
			time.sleep(1)
			
			# Detect and queue any new files for processing
			after = dict ([(f, None) for f in os.listdir (PATH_TO_WATCH)])
			added = [f for f in after if not f in before]
			removed = [f for f in before if not f in after]
			if added:
				for f in added:
					controller.enqueue(os.path.join(PATH_TO_WATCH,f))
			if removed: print("Removed: ", ", ".join (removed))
			before = after
			
			# Process the queue
			controller.process()
			
	except KeyboardInterrupt:
		pass


if __name__ == "__main__":
	main()
	
	
	
	
	
	
	
	
	
	