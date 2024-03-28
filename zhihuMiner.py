import requests
import json
import sys
import sqlite3
import time
from datetime import datetime
import re
from haralyzer import HarParser
import glob


class zhihuMiner():
	def __init__(self, qid=None):
		self.start = time.time()
		self.total_time = 0
		self.date = datetime.now().date()
		self.qid = qid
		self.total_questions = 0
		self.total_answers = 0
		self.total_comments = 0
		self.total_children = 0
		self.delay = 1 # delay between requests (seconds)
		self.init_database()
		if self.qid:
			self.save_savepoint("qid", self.qid)

	def info(self):
		# this will slow down the script, if the database is large. 
		# consider not calling the function
		print("\033[F"*3)
		questions = len(self.c.execute("SELECT qid FROM questions").fetchall())
		answers = len(self.c.execute("SELECT cid FROM comments WHERE type ='answer' AND comment_count != 0").fetchall())
		comments = len(self.c.execute("SELECT cid FROM comments WHERE type ='comment' AND comment_count != 0").fetchall())
		questions_processed = len(self.c.execute("SELECT qid FROM questions WHERE done = 1").fetchall())
		answers_processed = len(self.c.execute("SELECT cid FROM comments WHERE done = 1 AND type ='answer' AND comment_count != 0").fetchall())
		comments_processed = len(self.c.execute("SELECT cid FROM comments WHERE done = 1 AND type ='comment' AND comment_count != 0").fetchall())
		print(f"Found {self.total_questions} questions, {self.total_answers} answers, {self.total_comments} comments, and {self.total_children} child comments ({self.total_answers + self.total_comments + self.total_children} total) in {round((time.time() - self.start + self.total_time) / 60, 1)} minutes.")
		print(f"Questions processed: {questions_processed}/{questions}, answers processed: {answers_processed}/{answers}, comments processed: {comments_processed}/{comments}")
	
	# database

	def init_database(self):
		self.conn = sqlite3.connect("zhihu.db")
		self.c = self.conn.cursor()
		self.c.execute("CREATE TABLE IF NOT EXISTS comments (cid INT, qid INT, pid INT, uid TEXT, created_time INT, content TEXT, comment_count INT, voteup_count INT, type TEXT, gender INT, user_type TEXT, location TEXT, saved_date TEXT, done INT)")
		# cid = comment id (also child id and answer id)
		# qid = question id
		# pid = parent id (pid of a child comment is the comment it replied to, pid of comment is the answer it replied to, answer pid is none)
		# uid = user id
		# created_time = unix timestamp of creation time of answer, comment, or child
		# content = content of answer, comment, or child (html)
		# comment_count = number of comments
		# voteup_count = number of upvotes
		# type = answer, comment, or child
		# gender = gender of user (int, 0 = female, 1 = male, -1 = None, 2 = ??, all not sure yet, have to check again)
		# user_type = type of user (e.g. people, organisation)
		# location = location of user
		# saved_date = date when it was saved in this database
		# done = whether or not all comments, children have been saved (int, 0 or 1)
		self.c.execute("CREATE TABLE IF NOT EXISTS questions (qid INT, title TEXT, description TEXT, visits INT, saved_date TEXT, done TEXT)")
		self.c.execute("CREATE TABLE IF NOT EXISTS savepoint (name TEXT, value BLOB)")
		savepoint = self.c.execute("SELECT * FROM savepoint").fetchall()
		if not savepoint:
			self.c.execute("INSERT INTO savepoint (name, value) VALUES (?, ?)", ("url", None))
			self.c.execute("INSERT INTO savepoint (name, value) VALUES (?, ?)", ("stage", None))
			self.c.execute("INSERT INTO savepoint (name, value) VALUES (?, ?)", ("total_time", 0))
		self.conn.commit()

	def save_comment(self):
		cids = [i[0] for i in self.c.execute("SELECT cid FROM comments").fetchall()]
		if self.cid not in cids:
			self.c.execute("INSERT INTO comments (cid, qid, pid, uid, created_time, content, comment_count, voteup_count, type, gender, user_type, location, saved_date, done) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (self.cid, self.qid, self.pid, self.uid, self.created_time, self.content, self.comment_count, self.voteup_count, self.type, self.gender, self.user_type, self.location, self.date, 0))
			self.conn.commit()

	def save_question(self):
		qids = [i[0] for i in self.c.execute("SELECT qid FROM questions").fetchall()]
		if int(self.qid) not in qids:
			self.total_questions += 1
			self.c.execute("INSERT INTO questions (qid, title, description, visits, saved_date, done) VALUES (?, ?, ?, ?, ?, ?)", (self.qid, self.title, self.description, self.visits, self.date, 0))
			self.conn.commit()

	def update_comment_done(self, cid):
		self.c.execute("UPDATE comments SET done = (?) WHERE cid = (?)", (1, cid))
		self.conn.commit()

	def update_question_done(self):
		self.c.execute("UPDATE questions SET done = (?) WHERE qid = (?)", (1, self.qid))
		self.conn.commit()
	
	def save_savepoint(self, name, value):
		self.c.execute("UPDATE savepoint SET value = (?) WHERE name = (?)", (value, name))
		self.conn.commit()

	def load_savepoint(self):
		url = self.c.execute("SELECT value FROM savepoint WHERE name = (?)", ("url",)).fetchone()[0]
		stage = self.c.execute("SELECT value FROM savepoint WHERE name = (?)", ("stage",)).fetchone()[0]
		self.total_time = self.c.execute("SELECT value FROM savepoint WHERE name = (?)", ("total_time",)).fetchone()[0]
		self.total_questions = len(self.c.execute("SELECT * FROM questions").fetchall())
		self.total_answers = len(self.c.execute("SELECT * FROM comments WHERE type = (?)", ("answer",)).fetchall())
		self.total_comments = len(self.c.execute("SELECT * FROM comments WHERE type = (?)", ("comment",)).fetchall())
		self.total_children = len(self.c.execute("SELECT * FROM comments WHERE type = (?)", ("child",)).fetchall())

		if stage == "answer":
			self.qid = url.split("/")[6]
			self.get_answers(url)
		if stage == "comment":
			self.get_comments()
		if stage == "child":
			self.get_children()

	# location

	def get_location(self):
		time.sleep(self.delay)
		url = f"https://www.zhihu.com/people/{self.uid}"
		response = requests.get(url).text
		pattern = re.compile(r'IP 属地(.*?)"', re.DOTALL)
		match = pattern.search(response)

		if match:
			return match.group(1)
		else:
			return None

	# questions

	def get_questions(self):
		for file in glob.glob("*.har"):
			with open(file, "r", encoding="utf-8") as f:
				har_parser = HarParser(json.loads(f.read()))

			for page in har_parser.pages:
				for entry in page.entries:
					response = json.loads(entry.response.text)
					data = response["data"]
					for i in data:
						if i["type"] == "search_result":
							q_object = i["object"]
							question = q_object["question"]
							self.qid = question["id"]
							self.title = q_object["title"]
							self.description = q_object["description"]
							self.visits = q_object["visits_count"]
							self.save_question()
							self.save_savepoint("total_time", time.time() - self.start + self.total_time)
							self.info()
		self.get_answers()

	# answers

	def get_answers(self, url=None):
		self.save_savepoint("stage", "answer")
		qids = [i[0] for i in self.c.execute("SELECT qid FROM questions WHERE done = 0").fetchall()]
		if not qids:
			qids = [self.qid]
		
		for qid in qids:
			self.qid = qid
			if url and str(self.qid) in url:
				url = url
			else:
				url = f"https://www.zhihu.com/api/v4/questions/{self.qid}/feeds?&include=data[*].comment_count,content,voteup_count,created_time,excerpt&limit=5&offset=0&order=default&platform=desktop"
			is_end = False

			while not is_end:
				self.save_savepoint("url", url)
				response = requests.get(url).json()
				answers = response["data"]
				self.get_answer_info(answers)
				paging = response["paging"]
				is_end = paging["is_end"]
				url = paging["next"]

			self.update_question_done()
		
		self.get_comments()

	def get_answer_info(self, answers):
		self.pid = None
		for i in answers:
			target = i["target"]
			author = target["author"]
			self.cid = target["id"]
			self.uid = author["id"]
			self.created_time = target["created_time"]
			self.content = target["content"]
			self.comment_count = target["comment_count"]
			self.voteup_count = target["voteup_count"]
			self.type = "answer"
			self.gender = author["gender"]
			self.user_type = author["user_type"]
			self.location = self.get_location()
			self.save_comment()
			self.save_savepoint("total_time", time.time() - self.start + self.total_time)
			self.total_answers += 1
			self.info()

	# comments to answer

	def get_comments(self):
		self.save_savepoint("stage", "comment")
		to_do = [[i[0], i[1]] for i in self.c.execute("SELECT cid, qid FROM comments WHERE comment_count > 0 AND type = 'answer' AND done = 0").fetchall()]

		for i in to_do:
			cid = i[0]
			self.qid = i[1]
			offset = ""
			is_end = False
			while not is_end:
				# using \\ instead of / works for some reason, see https://www.zhihu.com/question/532925796/answer/2486670460
				url = f"https://www.zhihu.com/api/v4/comment_v5/answers\\{cid}/root_comment?order_by=score&limit=20&offset={offset}"
				response = requests.get(url).json()
				comments = response["data"]
				self.get_comment_info(comments, cid)
				paging = response["paging"]
				is_end = paging["is_end"]
				next_url = paging["next"]
				if not is_end:
					offset = next_url.split("&")[1].replace("offset=", "")
					# the returned next url doesn't work, so we only use the offset part to build our own
				time.sleep(self.delay)

			self.update_comment_done(cid)
		self.get_children()

	def get_comment_info(self, comments, cid):
		self.pid = cid
		for i in comments:
			author = i["author"]
			ip = i["comment_tag"]
			self.cid = i["id"]
			self.uid = author["id"]
			self.created_time = i["created_time"]
			self.content = i["content"]
			self.comment_count = i["child_comment_count"]
			self.voteup_count = i["like_count"]
			self.type = "comment"
			self.gender = author["gender"]
			self.user_type = author["user_type"]
			if ip and ip[0]["type"] == "ip_info":
				self.location = ip[0]["text"].replace("IP 属地", "")
			else:
				self.location = self.get_location()
			self.save_comment()
			self.save_savepoint("total_time", time.time() - self.start + self.total_time)
			self.total_comments += 1
			self.info()

	# children

	def get_children(self):
		self.save_savepoint("stage", "child")
		to_do = [[i[0], i[1]] for i in self.c.execute("SELECT cid, qid FROM comments WHERE comment_count > 0 AND type = 'comment'AND done = 0").fetchall()]
		
		for i in to_do:
			cid = i[0]
			self.qid = i[1]
			is_end = False
			url = f"https://www.zhihu.com/api/v4/comment_v5/comment/{cid}/child_comment?order_by=ts&limit=20&offset="

			while not is_end:
				self.pid = cid
				response = requests.get(url).json()
				children = response["data"]
				self.get_child_info(children)
				paging = response["paging"]
				is_end = paging["is_end"]
				url = paging["next"]
				time.sleep(self.delay)

			self.update_comment_done(cid)

		self.update_question_done()

	def get_child_info(self, children):
		for i in children:
			author = i["author"]
			ip = i["comment_tag"]
			self.cid = i["id"]
			self.uid = author["id"]
			self.created_time = i["created_time"]
			self.content = i["content"]
			self.comment_count = None
			self.voteup_count = i["like_count"]
			self.type = "child"
			self.gender = author["gender"]
			self.user_type = author["user_type"]
			if ip and ip[0]["type"] == "ip_info":
				self.location = ip[0]["text"].replace("IP 属地", "")
			else:
				self.location = self.get_location()
			self.save_comment()
			self.save_savepoint("total_time", time.time() - self.start + self.total_time)
			self.total_children += 1
			self.info()


if __name__ == "__main__":
	args = sys.argv
	all_args = ["-qid", "-load", "-har"]
	if len(args) < 2 or args[1] not in all_args:
		print(
			"How to use:",
			"\n-qid <zhihu question id>",
			"\nOR",
			"\n-load (continue from last savepoint)",
			"\nOR",
			"\n-har (load several questions from .har files)"
		)

		quit()

	if args[1] == "-qid":
		if len(args) != 3:
			print("qid not provided")
			quit()
		
		qid = args[2]
		miner = zhihuMiner(qid)
		miner.get_answers()

	if args[1] == "-load":
		miner = zhihuMiner()
		miner.load_savepoint()

	if args[1] == "-har":
		miner = zhihuMiner()
		miner.get_questions()