#!/usr/bin/env python3

'''
Author:		Zachary Zeitlin
Purpose:	Continuously query GitHub for sensitive data and output search results.
Notes:      - This file takes input from other relative filepaths, listed below.
Usage:      ./gitgot-continuous.py
'''

import github
import sys
import time
import logging
import threading
import os
import json
import yaml


# This thread takes in a file as input, and processes it.
class Inquisitor(threading.Thread):
	# Where to store logging information
	OUTPUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),"continuous/output/")
	# Number of seconds between git queries per thread
	DELAY = 8
	
	def __init__(self, callback=None, callback_args=None, *args, **kwargs):
		#target = kwargs.pop('target')
		target = self.processFile
		filepath = kwargs.pop('filepath')
		token = kwargs.pop('token')
		tag = kwargs.pop('tag')
		searchAugmentor = kwargs.pop('searchAugmentor')
		searchParameters = kwargs.pop('searchParameters')
    
		super(Inquisitor, self).__init__(target=self.target_with_callback, *args, **kwargs)
		self.callback = callback
		self.method = target
		self.filepath = filepath
		self.token = token
		self.g = github.Github(self.token)
		self.callback_args = callback_args
		self.tag = tag
		self.searchAugmentor = searchAugmentor
		self.searchParameters = searchParameters

		# Log for every query
		self.querylogger = logging.getLogger('queryLog')
		# Log for main script
		self.logger = logging.getLogger('main')
		# Log for only hits
		self.hitslogger = logging.getLogger('hits'+self.tag)
		
	def target_with_callback(self):
		self.method(self.filepath)
		if self.callback is not None:
			self.callback(*self.callback_args)
	
	def doQuery(self,query):  
		self.logger.info("Inquisitor.doQuery: Token=" + self.token[:4] + "... Tag=" + self.tag + " Query='" + query + "'")
		for attempt in range(10):
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
				delay = (attempt+1) * Inquisitor.DELAY
				self.logger.error("Rate Limit Exceeded. Delaying " + str(delay) + " seconds. Query='" + query + "'")
				print("Rate Limit Exceeded. Delaying " + str(delay) + " seconds. Query='" + query + "'")
				time.sleep(delay)
			else: # Query succeeded, break from attempt loop. Should never get here because of return statement.
				break
		else: # 10 Attempts all resulted in rate limit exceptions. Give up and return empty.
			result = {
					'totalCount': 0,
					'query': query,
					'urls': []
				}
			return result
		
	def processFile(self,filepath):
		
		# Parse search parameters file
		if(os.path.isfile(self.searchParameters)):
			with open(self.searchParameters, "r") as sp:
				searchParameters = sp.readline().strip()
		else:
			searchParameters = ""

		if(os.path.isfile(filepath)):

			with open(filepath, "r") as fp:
				subqueries = [line.rstrip() for line in fp.readlines()]
				
				# Check if query terms should be augmented with dirty words
				if("DO_NOT_AUGMENT" not in filepath):
					with open(self.searchAugmentor, "r") as sa:
						searchAugmentors = [line.rstrip() for line in sa.readlines()]
						for subquery in subqueries:
							for searchAugmentor in searchAugmentors:
								query = subquery + " " + searchAugmentor + " " + searchParameters
								result = self.doQuery(query)
								result['tag'] = self.tag
								
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
						result = self.doQuery(query)
						result['tag'] = self.tag
						
						# Log results 
						self.querylogger.info(json.dumps(result))
						if(result['totalCount'] > 0):
							self.hitslogger.info(json.dumps(result))
							
						# Delay between queries
						time.sleep(Inquisitor.DELAY)
							


class InquisitorController():
	
	# tagDelimiter is the same as the ingestor folder path. Everything after tagDelimiter, but before filename, is a tag.
	def __init__(self, tokens=None, maxThreads=None, tagDelimiter=None, searchAugmentor=None, searchParameters=None, outputDirectory=None):
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
		self.outputDirectory = outputDirectory
		self.logger = logging.getLogger('main')

	def enqueue(self, filepath):
		self.queue.append(filepath)
		self.logger.info("InquisitorController.enqueue: Adding to file queue: " + filepath)
		
	def process(self):
		if len(self.queue) > 0 and self.threadCount < self.maxThreads:
			fileToProcess = self.queue.pop(0)
			print("processing "+fileToProcess)
			self.logger.info("InquisitorController.process: Processing: " + fileToProcess)
			
			# If queryfile is in directory beneath ingestor/, make the directory a tag.
			tag = os.path.dirname(fileToProcess.split(self.tagDelimiter)[-1])[1:]
			# Remove exception tag: the DO_NOT_AUGMENT folder
			tag = tag.replace("/DO_NOT_AUGMENT","")
			
			# Setup logging for hit-only logs
			hitslogger = logging.getLogger('hits'+tag)
			# Only add handler once. Skip if it already exists.
			if(not len(hitslogger.handlers)):
				outputDir = os.path.join(self.outputDirectory, tag)
				if(not os.path.isdir(outputDir)):
					os.makedirs(outputDir, exist_ok=True)
				hitlogfh = logging.FileHandler(os.path.join(outputDir,'hits.json'))
				hitlogfh.setFormatter(logging.Formatter('{"datetime": "%(asctime)s", "name":"%(name)s", "result": %(message)s}'))
				hitslogger.setLevel(logging.DEBUG)
				hitslogger.addHandler(hitlogfh)

		
			thread = Inquisitor(
				name='inquisitor',
				callback=self.dequeue,
				callback_args=[fileToProcess],
				filepath=fileToProcess,
				token=self.tokens[self.currentTokenIndex],
				tag=tag,
				searchAugmentor=self.searchAugmentor,
				searchParameters=self.searchParameters
			)
			thread.start()
			self.threadCount += 1
			self.logger.info("InquisitorController.process: Current running threads: " + str(self.threadCount))
			
			# Increment to next token (round-robin)
			self.currentTokenIndex = (self.currentTokenIndex + 1) % len(self.tokens)
			
	def dequeue(self, filepath):
		print("dequeue called: "+str(filepath))
		self.logger.info("InquisitorController.dequeue: Removing from file queue: " + filepath)
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

	# Set working directory to the script's directory:
	working_dir = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))

	# Parse configuration file
	config = yaml.safe_load(open(os.path.join(working_dir,"config/config.yml")))
	PATH_TO_WATCH = config['input_directory']
	TOKENFILE = config["token_file"]
	SEARCH_AUGMENTOR = config["search_augmentor_file"]
	SEARCH_PARAMETERS = config["search_parameters_file"]
	LOGFILE = config["log_file"]
	QUERYLOGFILE = config["querylog_file"]
	OUTPUTDIR = config['output_directory']
	
	# Setup Logging
	mainLogFormatter = logging.Formatter('%(asctime)s: %(message)s')
	queryLogFormatter = logging.Formatter('{"datetime": "%(asctime)s", "name":"%(name)s", "result": %(message)s}')

	# Log for queries
	querylogfh = logging.FileHandler(QUERYLOGFILE)
	querylogfh.setFormatter(queryLogFormatter)
	querylogger = logging.getLogger('queryLog')
	querylogger.setLevel(logging.DEBUG)
	querylogger.addHandler(querylogfh)

	# Log for script
	logfh = logging.FileHandler(LOGFILE)
	logfh.setFormatter(mainLogFormatter)
	logger = logging.getLogger('main')
	logger.setLevel(logging.DEBUG)
	logger.addHandler(logfh)
	logger.info("Starting Inquisitor.")

	# Parse tokens
	tokens = []
	with open(TOKENFILE, "r") as fp:
		tokens = [line.rstrip() for line in fp.readlines()]
	logger.info("Parsed " + str(len(tokens)) + " GitHub tokens.")

	# Create thread controller
	controller = InquisitorController(
	tokens=tokens, 
	tagDelimiter=PATH_TO_WATCH, 
	searchAugmentor=SEARCH_AUGMENTOR,
	searchParameters=SEARCH_PARAMETERS,
	outputDirectory=OUTPUTDIR
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
				logger.info("Directory monitor observed files created: " + ", ".join(added))
				for f in added:
					filepath = os.path.join(PATH_TO_WATCH,f)
					if(os.path.isfile(filepath)):
						controller.enqueue(filepath)
			if removed: 
				logger.info("Directory monitor observed files deleted: " + ", ".join(removed))
			before = after
			
			# Process the queue
			controller.process()
			
	except KeyboardInterrupt:
		logger.info("Caught keyboard interrupt.")


if __name__ == "__main__":
	main()
	
	
	
	
	
	
	
	
	
	
