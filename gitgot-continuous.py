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
	# Number of seconds between git queries per thread
	DELAY = 7
	
	def __init__(self, callback=None, callback_args=None, *args, **kwargs):
		#target = kwargs.pop('target')
		target = self.processFile
		filepath = kwargs.pop('filepath')
		token = kwargs.pop('token')
		tagDelimiter = kwargs.pop('tagDelimiter')
		searchAugmentor = kwargs.pop('searchAugmentor')
		searchParameters = kwargs.pop('searchParameters')
		
		super(Inquisitor, self).__init__(target=self.target_with_callback, *args, **kwargs)
		self.callback = callback
		self.method = target
		self.filepath = filepath
		self.token = token
		self.g = github.Github(self.token)
		self.callback_args = callback_args
		self.tagDelimiter = tagDelimiter
		self.searchAugmentor = searchAugmentor
		self.searchParameters = searchParameters

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
	
	def doQuery(self,query):  
		try:
			repositories = self.g.search_code(query)
			numURLs = min(repositories.totalCount,5)

			result = {
				'totalCount': repositories.totalCount,
				'query': query,
        'urls': [repository.html_url for repository in repositories[:numURLs]]
			}
			return result
		except github.RateLimitExceededException:
			print("Rate Limit Exceeded on query")
		
	def processFile(self,filepath):
		
		# Parse search parameters file
		if(os.path.isfile(self.searchParameters)):
			with open(self.searchParameters, "r") as sp:
				searchParameters = sp.readline().strip()
		else:
			searchParameters = ""

		if(os.path.isfile(filepath)):
			# If queryfile is in directory beneath ingestor/, make the directory a tag.
			tag = os.path.dirname(filepath.split(self.tagDelimiter)[-1])[1:]
			# Remove exception tag: the DO_NOT_AUGMENT folder
			tag = tag.replace("/DO_NOT_AUGMENT","")

			# Setup logging for hit-only logs
			outputDir = os.path.join(Inquisitor.OUTPUTDIR, tag)
			if(not os.path.isdir(outputDir)):
				os.makedirs(outputDir, exist_ok=True)
			hitlogfh = logging.FileHandler(os.path.join(outputDir,'hits.json'))
			hitlogfh.setFormatter(self.logFormatter)
			self.hitslogger.addHandler(hitlogfh)
			
			with open(filepath, "r") as fp:
				subqueries = [line.rstrip() for line in fp.readlines()]

				# Check if query terms should be augmented with dirty words
				if("DO_NOT_AUGMENT" not in filepath):
					with open(self.searchAugmentor, "r") as sa:
						searchAugmentors = [line.rstrip() for line in sa.readlines()]
						for subquery in subqueries:
							for searchAugmentor in searchAugmentors:
								query = subquery + " " + searchAugmentor + " " + searchParameters
								print(query)
								result = self.doQuery(query)
								result['tag'] = tag
								
								# Log results 
								self.querylogger.info(json.dumps(result))
								if(result['totalCount'] > 0):
									self.hitslogger.info(json.dumps(result))
								
								# Delay between queries
								time.sleep(Inquisitor.DELAY)
				
				# Do not augment:
				else:
					for subquery in subqueries:
						query = subquery + " " + searchParameters
						print(query)
						result = self.doQuery(query)
						result['tag'] = tag
						
						# Log results 
						self.querylogger.info(json.dumps(result))
						if(result['totalCount'] > 0):
							self.hitslogger.info(json.dumps(result))
							
						# Delay between queries
						time.sleep(Inquisitor.DELAY)
							
				# Remove log handlers
				self.hitslogger.removeHandler(hitlogfh)
				self.querylogger.removeHandler(self.querylogfh)


class InquisitorController():
	
	# tagDelimiter is the same as the ingestor folder path. Everything after tagDelimiter, but before filename, is a tag.
	def __init__(self, tokens=None, maxThreads=None, tagDelimiter=None, searchAugmentor=None, searchParameters=None):
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
		self.searchAugmentor = searchAugmentor
		self.searchParameters = searchParameters

	def enqueue(self, filepath):
		self.queue.append(filepath)
		print("enqueue() called. curent queue: " + str(self.queue))
		
	def process(self):
		#print ("process() called")
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
				tagDelimiter=self.tagDelimiter,
				searchAugmentor=self.searchAugmentor,
				searchParameters=self.searchParameters
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
	PATH_TO_WATCH = os.path.join(os.getcwd(),"continuous/ingester")
	TOKENFILE = os.path.join(os.getcwd(),"tokenfile")
	SEARCH_AUGMENTOR = os.path.join(os.getcwd(),"continuous/search_augmentor")
	SEARCH_PARAMETERS = os.path.join(os.getcwd(),"continuous/search_parameters")
	tokens = []
	
	with open(TOKENFILE, "r") as fp:
		tokens = [line.rstrip() for line in fp.readlines()]
	controller = InquisitorController(
    tokens=tokens, 
    tagDelimiter=PATH_TO_WATCH, 
    searchAugmentor=SEARCH_AUGMENTOR,
    searchParameters=SEARCH_PARAMETERS
  )
	
	# Ingest existing files (every file in PATH_TO_WATCH recursively)
	filesToIngest = [os.path.join(dp, f) for dp, dn, fn in os.walk(os.path.join(os.getcwd(),PATH_TO_WATCH)) for f in fn]
	# Enqueue all but blacklisted filenames
	for f in filesToIngest:
		filename = f.split('/')[-1]
		if filename != '.gitignore' and filename.upper() != 'README' and filename.upper() != 'README.MD':
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
	
	
	
	
	
	
	
	
	
	
