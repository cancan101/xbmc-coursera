from xbmcswift2 import Plugin, xbmc
import xbmcswift2

import logging
import cookielib
import urllib2
import urllib
import json
import re

from course_utils import login_to_class, get_syllabus_url, parse_syllabus
from courseraLogin import login, saveCJ
import datetime
import time

##############################
DEBUG = False
CACHE_TIME = 24 * 60
##############################
plugin = Plugin()
##############################
if DEBUG:
	plugin.log.setLevel(level=logging.DEBUG)
##############################

def isSettingsBad(username, password):
	return username is None or password is None or username == "" or password == ""

def loadSavedCookies(cookies_raw):
	cookies = []
	for cookie in cookies_raw:
		cookies.append(cookielib.Cookie(**cookie))
		
	cj = cookielib.CookieJar()
	for cookie in cookies:
		cj.set_cookie(cookie)
		
	return cj

def getOpener(cj):
	return urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))

def getOpenerFromRawCookies(cookies_raw):
	cj = loadSavedCookies(cookies_raw=cookies_raw)
	opener = getOpener(cj=cj)
	
	return opener
	
def get_page(href, opener):
	req = urllib2.Request(href)
	return opener.open(req).read()

def getClasses(public_id, opener):
	href = "https://www.coursera.org/maestro/api/topic/list_my?user_id=%s" % public_id
	
	return json.loads(get_page(href, opener))

@plugin.cached(TTL=CACHE_TIME)
def loadClasses(username, password):
	user_data = plugin.get_storage(username, file_format='json')
	
	cookies_raw = user_data.get('cookies')
	external_id = user_data.get('external_id')
	public_id = user_data.get('public_id')
	
	did_login = False
	if cookies_raw is None or external_id is None or public_id is None:
		plugin.log.info("Logging in")
		external_id, public_id, cookies_raw = login(username, password)
		user_data['cookies'] = cookies_raw
		user_data['external_id'] = external_id
		user_data['public_id'] = public_id
		did_login = True
	else:
		plugin.log.debug("Loading data from store")

	plugin.log.debug("external_id=%s, public_id=%s" % (external_id, public_id))
#	plugin.log.debug("Cookies:\n%s" % '\n'.join([str(x) for x in cookies_raw]))
	
	opener = getOpenerFromRawCookies(cookies_raw=cookies_raw)
	
	try:
		classes = getClasses(public_id, opener)
	except urllib2.HTTPError, ex:
		if ex.code != 403:
			raise ex
		
		if did_login:
			raise ex
		
		plugin.log.info("Maybe cookies is old? Logging in")
		external_id, public_id, cookies_raw = login(username, password)
		user_data['cookies'] = cookies_raw
		user_data['external_id'] = external_id
		user_data['public_id'] = public_id

		opener = getOpenerFromRawCookies(cookies_raw=cookies_raw)
		classes = getClasses(public_id, opener)
		
	return classes

@plugin.route('/classes/', name="classes")
@plugin.route('/',name="index")
def index():
	username = plugin.get_setting('username')
	password = plugin.get_setting('password')
	
	if isSettingsBad(username, password):
		plugin.open_settings()
		username = plugin.get_setting('username')
		password = plugin.get_setting('password')
		
		if isSettingsBad(username, password):
			return []
	
	try:	
		classes = loadClasses(username, password)
	except urllib2.HTTPError, ex:
		if ex.code != 401:
			raise ex
		else:
			plugin.notify(msg="Unable to login to Coursera")
			print "Unable to login to Coursera"
			return []
	
#	plugin.log.debug(classes)
	plugin.add_sort_method(xbmcswift2.SortMethod.TITLE_IGNORE_THE)

	items = []
	for c in classes:
		url = plugin.url_for('listCourses', shortName=c["short_name"])
		
		items.append({
			'label': c["name"],
			'path': url,
			'is_playable': False,
			'label2':c["short_description"],
			'icon':c['large_icon'],
			'thumbnail':c['large_icon'],
#			'context_menu':[("test", "XBMC.RunPlugin(%s)" % url)],
		})
	
	return items

@plugin.route('/clearcache/')
def clearcache():
	plugin.log.info("clearing cache")

	username = plugin.get_setting('username')
	if username is not None and username != "":
		user_cache = plugin.get_storage(username, file_format='json')
		user_cache.clear()
		user_cache.sync()
		
	func_cache = plugin.get_storage('.functions', file_format='pickle')
	func_cache.clear()
	func_cache.sync()
	
	main_cache = plugin.get_storage('main', file_format='pickle')
	main_cache.clear()
	main_cache.sync()

def getCourseShortName(course):
	home_link = course["home_link"]
	
	short_name = home_link.replace("https://class.coursera.org/", "")[:-1]
	
	return short_name

def listCoursesForEntry(classEntry):
#	classShortName = classEntry["short_name"]
	courses = classEntry["courses"]

	if len(courses) == 1:
#		plugin.log.debug("one item case")
		return listCourseContents(courseShortName=getCourseShortName(courses[0]))
	
	ret = []
	for course in courses:
		short_name = getCourseShortName(course)
		
		url = plugin.url_for('listCourseContents', courseShortName=short_name)
		
		start_date_string = course.get('start_date_string')
		if start_date_string is None or start_date_string == "":
			if course.get('start_year') is None and course.get('start_month') is None and course.get('start_day') is None:
				start_date_string = "Self study"
			elif course.get('start_year') is not None and course.get('start_month') is not None and course.get('start_day') is not None:
				date = datetime.date(year=course.get('start_year'), month=course.get('start_month'), day=course.get('start_day'))
				start_date_string = date.strftime("%d %B %Y")
			elif course.get('start_year') is not None and course.get('start_month') is not None:
				date = datetime.date(year=course.get('start_year'), month=course.get('start_month'))
				start_date_string = date.strftime("%B %Y")				
			else:
				start_date_string = "Unknown"
		
		duration_string = course.get('duration_string')
		
		label = start_date_string
		
		if duration_string is not None and duration_string != "":
			label = "%s (%s)" % (label, duration_string)
		
		ret.append({
			'label': label,
			'path': url,
			'icon':classEntry['large_icon'],
			'thumbnail':classEntry['large_icon'],
			'is_playable': False
		})
	return ret

@plugin.cached_route('/classes/<shortName>/')
def listCourses(shortName):
	username = plugin.get_setting('username')
	password = plugin.get_setting('password')
	
	if isSettingsBad(username, password):
		return []
		
	classes = loadClasses(username, password)
	for c in classes:
		if c["short_name"] == shortName:
			return listCoursesForEntry(c)
	else:
		plugin.log.error("%s not found: %s" % (shortName, [x["short_name"] for x in classes]))
	
	return []

@plugin.cached(TTL=CACHE_TIME)
def getClassCookies(className, username, password):
	user_data = plugin.get_storage(username, file_format='json')
	if user_data is None:
		return None
	
	cookies_raw = user_data.get('cookies')
	if cookies_raw is None:
		external_id, public_id, cookies_raw = login(username, password)
		if cookies_raw is None:
			return None
		user_data['cookies'] = cookies_raw
		user_data['external_id'] = external_id
		user_data['public_id'] = public_id

	cj = loadSavedCookies(cookies_raw=cookies_raw)
	
	opener = getOpener(cj=cj)
	
	plugin.log.debug("Logging in to class: %s" % className)
	logged_in = login_to_class(className, opener, username, password)
	
	if logged_in == False:
		return None
	
	CSRFT_TOKEN_COOKIE_NAME = "csrf_token"
	cj.clear(domain="class.coursera.org", path="/%s" % className, name=CSRFT_TOKEN_COOKIE_NAME)
	#cj.clear(domain="class.coursera.org", path="/%s" % className, name="session")
	cj.clear(domain="www.coursera.org", path="/" , name="maestro_login")
	cj.clear(domain="www.coursera.org", path="/" , name="sessionid")
	
	return saveCJ(cj)

def loadSavedClassCookies(username):
	user_data = plugin.get_storage(username, file_format='json')

	cookies_class = user_data.get('cookies_class')
	if cookies_class is None:
		cookies_class = user_data['cookies_class'] = {}
	
	return cookies_class	

@plugin.cached(TTL=CACHE_TIME)				
def getSylabus(className, username, password):
	plugin.log.info("getSylabus for %s." % className)
	
	cookies, didLogin = getClassCookieOrLogin(username, password, className, indicateDidLogin=True)
	url = get_syllabus_url(className=className)
	plugin.log.debug("syllabus_url=%s" % url)
	opener = getOpenerFromRawCookies(cookies_raw=cookies)

	sylabus_txt = get_page(url, opener)
#	print "sylabus_txt = %s" % sylabus_txt
	not_logged_in = 'with a Coursera account' in sylabus_txt
	
	if not_logged_in:
		if didLogin:
			raise Exception("Unable to login to class")
		else:
			plugin.log.info("Cookies for %s are old. Logging in to class" % className)
			cookies = getClassCookies(className, username, password)
			opener = getOpenerFromRawCookies(cookies_raw=cookies)
		
			sylabus_txt = get_page(url, opener)
	#		print "sylabus_txt = %s" % sylabus_txt
			not_logged_in = 'with a Coursera account' in sylabus_txt
			if not_logged_in:
				raise Exception("Unable to login to class")
			else:
				cookies_class = loadSavedClassCookies(username)
				cookies_class[className] = cookies
	
	parsed = parse_syllabus(sylabus_txt, opener)
	
	return parsed

@plugin.cached_route('/courses/<courseShortName>/')
def listCourseContents(courseShortName):
	username = plugin.get_setting('username')
	password = plugin.get_setting('password')
	number_episodes = plugin.get_setting('number_episodes')
	
	if isSettingsBad(username, password):
		return []
	
	sylabus = getSylabus(courseShortName, username, password)
	if sylabus is None:
		return []
	elif sylabus == "CLOSED":
		return [{
			'label': "%s is no longer available on Coursera" % courseShortName,
			 'path':plugin.url_for(endpoint="index")
		}]
	
	
	sylabus = sylabus['sections']
	
	ret = []
	for lecture in sorted(sylabus.keys(), key=lambda x: sylabus[x]["section_num"]):
		section_num = sylabus[lecture]["section_num"]
		label = lecture
		if number_episodes:
			label = "%d. %s" % (section_num+1, label)
		ret.append({
			'label': label,
			'path': plugin.url_for(endpoint="listLectureContents", courseShortName=courseShortName, section_num=str(section_num)),
			'is_playable': False,
			'info':{
				'season': section_num+1,
				'title':lecture,
#				'episode': section_num+1,
			}			
		})
#	plugin.add_sort_method(xbmcswift2.SortMethod.SEASON)
	return ret

title_re1 = re.compile("^(.*) \((\d+\:\d{2})\)$")
title_re2 = re.compile("^\d+\-\d+\: (.*) \((\d+m\d{2})s\)$")
title_re3 = re.compile("^(.*) \((\d+m\d{2})s\)$")
def extractDuration(section):
	match = title_re1.match(section)
	if match is None:
		match = title_re2.match(section)
		if match is None:
			match = title_re3.match(section)
			if match is None:
				return section, None
			else:
				return match.group(1).strip(), match.group(2).replace('m', ":")
		else:
			return match.group(1).strip(), match.group(2).replace('m', ":")
	else:
		return match.group(1).strip(), match.group(2)

def getClassCookieOrLogin(username, password, courseShortName, indicateDidLogin=False):
	didLogin = False
	
	cookies_class = loadSavedClassCookies(username)
	
	class_cookies = cookies_class.get(courseShortName)
	if class_cookies is None:
		plugin.log.debug("Cookies for %s not found. Logging in to class" % courseShortName)
		class_cookies = getClassCookies(courseShortName, username, password)
		
		if class_cookies is not None:
			didLogin = True
			cookies_class[courseShortName] = class_cookies
		else:
			raise Exception("Unable to login to class")	
	
	if indicateDidLogin:
		return class_cookies, didLogin
	else:
		return class_cookies

@plugin.route('/courses/<courseShortName>/lecture/<lecture_id>/')
def playLecture(courseShortName, lecture_id):
	username = plugin.get_setting('username')
	password = plugin.get_setting('password')
	
	if isSettingsBad(username, password):
		return []
	
	sylabus = getSylabus(courseShortName, username, password)
	if sylabus is None:
		return []
	
	sections = sylabus['sections']
	
	for lecture_contents in sections.values():
		sections = lecture_contents["sections"]
		for section_name, section in sections.iteritems():
			if section["lecture_id"] == lecture_id:
				print "FOUND!: %s" % section_name
				url = section['resources']["Lecture Video"]
				
				class_cookies = getClassCookieOrLogin(username, password, courseShortName)
				
				cookies = '&'.join(["%s=%s" % (x["name"], x["value"]) for x in class_cookies])
				
				cookies_str = urllib.urlencode({'Cookie':cookies})
				path = "%s|%s" % (url, cookies_str)
				
				plugin.log.info('Handle: ' + str(plugin.handle))
				
				ret = plugin.set_resolved_url(path)
				
				if "Subtitle" in section['resources']:
					player = xbmc.Player()
					while not player.isPlaying():
						time.sleep(1)
					player.setSubtitles(section['resources']["Subtitle"])
				
#				return ret
				break
		
#	return []

def alwaysSubtiles():
	return plugin.get_setting('enable_subtitles')

@plugin.cached_route('/courses/<courseShortName>/sections/<section_num>/')
def listLectureContents(courseShortName, section_num):
	username = plugin.get_setting('username')
	password = plugin.get_setting('password')
	
	if isSettingsBad(username, password):
		return []
	
	sylabus = getSylabus(courseShortName, username, password)
	if sylabus is None:
		return []
	
	instructor_name = sylabus['instructor_name']
	instructor_role = sylabus['instructor_role']
	
	sections = sylabus['sections']
	
	lecture_desired = None
	for lecture_contents in sections.values():
		if str(lecture_contents['section_num']) == section_num:
			lecture_desired = lecture_contents
			break
		
	if lecture_desired is None:
		plugin.log.error("Lecture %d for %s not found" % (section_num, courseShortName))
		return []
	
	class_cookies = getClassCookieOrLogin(username, password, courseShortName)
	
	cookies = '&'.join(["%s=%s" % (x["name"], x["value"]) for x in class_cookies])
	
	cookies_str = urllib.urlencode({'Cookie':cookies})
	
	section_lecture = lecture_desired["sections"]
	
	ret = []
	for section_name, section in section_lecture.iteritems():
		title, duration = extractDuration(section_name)
		url = section['resources']["Lecture Video"]
		lecture_num = section['lecture_num'] # int(section["lecture_id"])
		
		play_url = plugin.url_for(endpoint="playLecture", courseShortName=courseShortName, lecture_id=str(section["lecture_id"]))
		
		info = {
			'episode': lecture_num+1,
			'season': int(section_num)+1,
			'title': title,	
			'watched':section["viewed"],
		}
		
		if instructor_name is not None and instructor_name != "":
			if instructor_role is not None and instructor_role != "":
				info['castAndRole'] = [(instructor_name, instructor_role)]
			else:
				info['cast'] = [instructor_name]
		
		if sylabus["course_name"] != "":
			info['tvshowtitle'] = sylabus["course_name"]
		
		if duration is not None:
			info["duration"] = duration
		
		path = "%s|%s" % (url, cookies_str)
		
		if alwaysSubtiles():
			path = play_url
			
#		print info
			
		ret.append({
			'label': title,
			'path': path,
			'is_playable': True,
			'info':info,
			'context_menu':[
						("Play with subtitles", "XBMC.RunPlugin(%s)" % play_url),
						("Play with subtitles2", "XBMC.PlayMedia(%s)" % play_url)
						],
		})
	plugin.add_sort_method(xbmcswift2.SortMethod.EPISODE)
#	print(dir(xbmcswift2.SortMethod))
	return ret

if __name__ == '__main__':
	plugin.run()
