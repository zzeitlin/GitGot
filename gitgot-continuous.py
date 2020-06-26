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
	QUERYLOG = 'continuous/logs/queries.txt'
	OUTPUTDIR = 'continuous/output/'
	# Number of seconds between git queries
	DELAY = 7
	
	def __init__(self, callback=None, callback_args=None, *args, **kwargs):
		#target = kwargs.pop('target')
		target = self.processFile
		filepath = kwargs.pop('filepath')
		token = kwargs.pop('token')
		tagDelimiter = kwargs.pop('tagDelimiter')
		
		super(Inquisitor, self).__init__(target=self.target_with_callback, *args, **kwargs)
		self.callback = callback
		self.method = target
		self.filepath = filepath
		self.token = token
		self.g = github.Github(self.token)
		self.callback_args = callback_args
		self.tagDelimiter = tagDelimiter
		
		# Setup logging
		self.logFormatter = logging.Formatter('{"datetime": "%(asctime)s", "name":"%(name)s", "result": %(message)s}')
		
		# Log for every query
		self.querylogfh = logging.FileHandler(Inquisitor.QUERYLOG)
		self.querylogfh.setLevel(logging.DEBUG)
		self.querylogfh.setFormatter(self.logFormatter)
		self.querylogger = logging.getLogger('inquisitor')
		self.querylogger.setLevel(logging.DEBUG)
		self.querylogger.addHandler(self.querylogfh)
		
		# Log for only hits
		self.hitslogger = logging.getLogger('hits')
		self.hitslogger.setLevel(logging.DEBUG)
		
		
	def target_with_callback(self):
		self.method(self.filepath)
		if self.callback is not None:
			self.callback(*self.callback_args)
			
	def processFile(self,filepath):
		if(os.path.isfile(filepath)):
			# If queryfile is in directory beneath ingestor/, make the directory a tag.
			tag = os.path.dirname(filepath.split(self.tagDelimiter)[-1])[1:]
			
			# Setup logging for hit-only logs
			outputDir = os.path.join(Inquisitor.OUTPUTDIR, tag)
			if(not os.path.isdir(outputDir)):
				os.makedirs(outputDir, exist_ok=True)
			hitlogfh = logging.FileHandler(os.path.join(outputDir,'hits.json'))
			hitlogfh.setFormatter(self.logFormatter)
			self.hitslogger.addHandler(hitlogfh)
			
			
			with open(filepath, "r") as fp:
				queries = [line.rstrip() for line in fp.readlines()]
			for subquery in queries:
				try:
					query = subquery
					repositories = self.g.search_code(query)
					
					result = {
						'totalCount': repositories.totalCount,
						'query': query,
						'tag': tag
					}
					
					# Log results 
					self.querylogger.info(json.dumps(result))
					# TODO: make this only fire when totalCount>0
					self.hitslogger.info(json.dumps(result))
					
				except github.RateLimitExceededException:
					print("Rate Limit Exceeded on query")
				
				# Delay between queries
				time.sleep(Inquisitor.DELAY)
				
			# Remove where the hit log is pointing
			self.hitslogger.removeHandler(hitlogfh)


class InquisitorController():
	
	# tagDelimiter is the same as the ingestor folder path. Everything after tagDelimiter, but before filename, is a tag.
	def __init__(self, tokens=None, maxThreads=None, tagDelimiter=None):
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
		
		self.tagDelimiter = tagDelimiter
		
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
				token=self.tokens[self.currentTokenIndex],
				tagDelimiter=self.tagDelimiter
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
	PATH_TO_WATCH = "continuous/ingestor"
	TOKENFILE = os.path.join(os.getcwd(),"tokenfile")
	tokens = []
	
	with open(TOKENFILE, "r") as fp:
		tokens = [line.rstrip() for line in fp.readlines()]
	controller = InquisitorController(tokens=tokens, tagDelimiter=PATH_TO_WATCH)
	
	# Ingest existing files (every file in PATH_TO_WATCH recursively)
	filesToIngest = [os.path.join(dp, f) for dp, dn, fn in os.walk(os.path.join(os.getcwd(),PATH_TO_WATCH)) for f in fn]
	# Remove unwatched files
	for f in filesToIngest:
		filename = f.split('/')[-1]
		if filename == '.gitignore' or filename.upper() == 'README' or filename.upper() == 'README.MD':
			filesToIngest.remove(f)
		else:
			controller.enqueue(f)
	

	# Setup the directory watcher
	before = [os.path.join(dp, f) for dp, dn, fn in os.walk(os.path.join(os.getcwd(),PATH_TO_WATCH)) for f in fn]
	try:
		while True:
			time.sleep(1)
			
			# Detect and queue any new files for processing
			after= [os.path.join(dp, f) for dp, dn, fn in os.walk(os.path.join(os.getcwd(),PATH_TO_WATCH)) for f in fn]
			added = [f for f in after if not f in before]
			removed = [f for f in before if not f in after]
			if added:
				for f in added:
					filepath = os.path.join(PATH_TO_WATCH,f)
					if(os.path.isfile(filepath)):
						controller.enqueue(filepath)
			if removed: 
				pass
				#print("Removed: ", ", ".join (removed))
			before = after
			
			# Process the queue
			controller.process()
			
	except KeyboardInterrupt:
		pass


if __name__ == "__main__":
	main()
	
	
	
	
	
	
	
	
	
	