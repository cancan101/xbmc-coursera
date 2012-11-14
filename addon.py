from xbmcswift2 import Plugin
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

DEBUG = True
CACHE_TIME = 10

plugin = Plugin()

if DEBUG:
	plugin.log.setLevel(level=logging.DEBUG)

	settings_fp = open("settings.json", 'r')
	settings = json.load(settings_fp)
	settings_fp.close()
	
	username = settings["username"]
#	print "username=%s" % (username)
	plugin.set_setting('username', username)
	plugin.set_setting('password', settings["password"])

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

@plugin.cached_route('/classes/', name="classes")
@plugin.cached_route('/')
def index():
	username = plugin.get_setting('username')
	password = plugin.get_setting('password')
	
	if isSettingsBad(username, password):
		plugin.open_settings()
		username = plugin.get_setting('username')
		password = plugin.get_setting('password')
		
		if isSettingsBad(username, password):
			return []
		
	classes = loadClasses(username, password)
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
			'thumbnail':c['large_icon']
		})
	
	return items

def getCourseShortName(course):
	home_link = course["home_link"]
	
	short_name = home_link.replace("https://class.coursera.org/", "")[:-1]
	
	return short_name

def listCoursesForEntry(classEntry):
#	classShortName = classEntry["short_name"]
	courses = classEntry["courses"]
	
	if len(courses) == 1:
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
	
	return []

@plugin.cached(TTL=CACHE_TIME)
def getClassCookies(className, username, password):
	user_data = plugin.get_storage(username, file_format='json')
	if user_data is None:
		return None
	
	cookies_raw = user_data.get('cookies')
	if cookies_raw is None:
		return None

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
	
	cookies_class = loadSavedClassCookies(username)
		
	cookies = cookies_class.get(className)
	didLogin = False
	if cookies is None:
		plugin.log.debug("Cookies for %s not found. Logging in to class" % className)
		cookies = getClassCookies(className, username, password)
		didLogin = True
		cookies_class[className] = cookies
	

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
				cookies_class[className] = cookies
	
	parsed = parse_syllabus(sylabus_txt, opener)
	
	return parsed

@plugin.cached_route('/courses/<courseShortName>/')
def listCourseContents(courseShortName):
	username = plugin.get_setting('username')
	password = plugin.get_setting('password')
	
	if isSettingsBad(username, password):
		return []
	
	sylabus = getSylabus(courseShortName, username, password)
	if sylabus is None:
		return []
	
	sylabus = sylabus['sections']
	
	ret = []
	for lecture in sorted(sylabus.keys(), key=lambda x: sylabus[x]["section_num"]):
		section_num = sylabus[lecture]["section_num"]
		ret.append({
			'label': lecture,
			'path': plugin.url_for(endpoint="listLectureContents", courseShortName=courseShortName, section_num=str(section_num)),
			'is_playable': False,
			'info':{
				'season': section_num+1,
			}			
		})
	return ret

title_re1 = re.compile("^(.*) \((\d+\:\d{2})\)$")
title_re2 = re.compile("^\d+\-\d+\: (.*) \((\d+m\d{2})s\)$")
def extractDuration(section):
	match = title_re1.match(section)
	if match is None:
		match = title_re2.match(section)
		if match is None:
			return section, None
		else:
			return match.group(1).strip(), match.group(2).replace('m', ":")
	else:
		return match.group(1).strip(), match.group(2)

@plugin.cached_route('/courses/<courseShortName>/<section_num>/')
def listLectureContents(courseShortName, section_num):
	username = plugin.get_setting('username')
	password = plugin.get_setting('password')
	
	if isSettingsBad(username, password):
		return []
	
	sylabus = getSylabus(courseShortName, username, password)
	if sylabus is None:
		return []
	
	instructor_name = sylabus['instructor_name']
	sylabus = sylabus['sections']
	
	lecture_desired = None
	for lecture_contents in sylabus.values():
		if str(lecture_contents['section_num']) == section_num:
			lecture_desired = lecture_contents
			break
		
	if lecture_desired is None:
		plugin.log.error("Lecture %d for $s not found" % (section_num, courseShortName))
		return []
	
	class_cookies = loadSavedClassCookies(username).get(courseShortName)
	
#	cookies = dict(zip([x["name"] for x in class_cookies], [x["value"] for x in class_cookies]))
	
	cookies = '&'.join(["%s=%s" % (x["name"], x["value"]) for x in class_cookies])
	
	cookies_str = urllib.urlencode({'Cookie':cookies})
	
	sections = lecture_desired["sections"]
	
	ret = []
	for section_name, section in sections.iteritems():
		title, duration = extractDuration(section_name)
		url = section['resources']["Lecture Video"]
		lecture_num = section['lecture_num']
		
		info = {
			'episode': lecture_num+1,
			'season': int(section_num)+1,
			'title': title,	
			'cast': instructor_name
		}
		
		if duration is not None:
			info["duration"] = duration
		
		path = "%s|%s" % (url, cookies_str)
			
		ret.append({
			'label': title,
			'path': path,
			'is_playable': True,
			'info':info,
		})
	plugin.add_sort_method(xbmcswift2.SortMethod.EPISODE)
#	print(dir(xbmcswift2.SortMethod))
	return ret

if __name__ == '__main__':
	plugin.run()
