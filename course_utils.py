'''
Created on Nov 7, 2012

@author: alex
'''
import json
import cookielib
import urllib2
import urllib
from BeautifulSoup import BeautifulSoup
import re
import string


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

def get_page(href, opener):
	req = urllib2.Request(href)
	return opener.open(req).read()

def loadProfile(external_id, opener):
	try:
		profile_str = get_page("https://www.coursera.org/maestro/api/user/profile?user-id=%s" % external_id, opener)
		return profile_str
	except urllib2.HTTPError as httperr:
		if httperr.code == 403:
			print "Verbotten"
		else:
			print httperr
		return None
	
def getClasses(public_id, opener):
	href = "https://www.coursera.org/maestro/api/topic/list_my?user_id=%s" % public_id
	
	return json.loads(get_page(href, opener))
		

def get_syllabus_url(className):
	"""Return the Coursera index/syllabus URL."""
	return "http://class.coursera.org/%s/lecture/index" % className


def get_auth_url(className):
	return "http://class.coursera.org/%s/auth/auth_redirector?type=login&subtype=normal&email=&visiting=&minimal=true" % className

def login_to_class(className, opener, username, password):
	auth_url = get_auth_url(className)
	print "auth_url=%s" % auth_url
	req = urllib2.Request(auth_url)
	ref = opener.open(req).geturl()
	
	print "Following login redirect to: %s" % ref

	classLogin_txt = get_page(ref, opener)
	
	soup = BeautifulSoup(classLogin_txt)
	
	classLogin_title = soup.html.head.title.string.strip()
	
	if classLogin_title == "Coursera Login":
		print "We are not currently logged-in. Attempting login"
		data = urllib.urlencode({'email': username, 'password': password, 'login': 'Login'})
		req = urllib2.Request(ref, data)
		classLogin_txt = opener.open(req).read()
		
		soup = BeautifulSoup(classLogin_txt)
	
		classLogin_title = soup.html.head.title.string.strip()

#		print classLogin_title
		if classLogin_title == "Authentication":
			print "We successfully logged-in."
			return True
		else:
			print "We unsuccessfully logged-in: %s" % classLogin_title
			return False
	elif classLogin_title == "Authentication":
		print "We are currently logged-in."
		return True
	else:
		print "Unknown state: %s" % classLogin_title
		return False

def grab_hidden_video_url(href, opener):
	"""
	Follow some extra redirects to grab hidden video URLs (like those from
	University of Washington).
	"""
	page = get_page(href, opener)
	soup = BeautifulSoup(page)
	l = soup.findAll('source', attrs={'type': 'video/mp4'})
	return l[0]['src']

def clean_filename(s):
	"""Sanitize a string to be used as a filename."""
	# strip paren portions which contain trailing time length (...)
	s = re.sub("\([^\(]*$", "", s)
	s = s.strip().replace(':','-').replace(' ', '_')
	valid_chars = "-_.()%s%s" % (string.ascii_letters, string.digits)
	return ''.join(c for c in s if c in valid_chars)

def get_anchor_format(a):
	"""Extract the resource file-type format from the anchor"""
	# (. or format=) then (file_extension) then (? or $)
	# e.g. "...format=txt" or "...download.mp4?..."
	format = re.search("(?:\.|format=)(\w+)(?:\?.*)?$", a)
	return format.group(1) if format else None

def parse_syllabus(page_txt, opener):
	ret = {}
	
	soup = BeautifulSoup(page_txt)
	
	name_tag = soup.find(attrs={'class':'course-instructor-name'})
	if name_tag is not None:
		instructor_name = name_tag.string
	else:
		instructor_name = ""
	
	sections = soup.findAll(attrs={'class':['list_header_link expanded', 'list_header_link contracted']})
	for section_num,section in enumerate(sections):
		heading = section.find(attrs={'class':'list_header'})
		if heading is None:
			print "Unable to parse section"
			continue
		
		heading_text = heading.string
		if heading_text is None:
			print "Unable to parse section"
			continue
		
		heading_text = heading_text.strip()
#		print heading_text
		section_entry = ret[heading_text] = {}
		section_entry['section_num'] = section_num
		
		sections_entry = section_entry['sections'] = {}
		
		section_entries = section.nextSibling
		if section_entries is None:
			print "Unable to parse section: %s" (heading_text)
			continue
		
		lectures = section_entries.findAll('li')
		for lecture_num, lecture in enumerate(lectures):
			lecture_title = lecture.find(attrs={'class':'lecture-link'})
			if lecture_title is None:
				print "Unable to parse lecture in %s (lecture_title is None)" % (heading_text)
				continue
			
			data_lecture_view_link = lecture_title.get('data-lecture-view-link')
			
			lecture_title_str = lecture_title.find(text=True)
			if lecture_title_str is None:
				print "Unable to parse lecture in %s" % (heading_text)
				continue
			
			lecture_title_str = lecture_title_str.strip()
#			print "- %s (%s)" % (lecture_title_str, data_lecture_view_link)
			
			lecture_entry = sections_entry[lecture_title_str] = {}
			lecture_entry['data_lecture_view_link'] = data_lecture_view_link
			lecture_entry["lecture_num"] = lecture_num
			resources_entry = lecture_entry['resources'] = {}
			
			resources = lecture.find(attrs={'class':'item_resource'})
			if resources is None:
				print "Unable to find resources for lecture %s in %s" % (lecture_title_str, heading_text)
				continue
			
			mp4_found = False				
			for resource in resources.findAll('a'):
				href = resource['href']
				title = resource['title']
				resource_format = get_anchor_format(href)
				
#				print "-- %s (%s) format=%s" % (title, href, resource_format)
				if resource_format == 'mp4':
					mp4_found = True
				resources_entry[title] = href
				resources_entry["Lecture Video"] = href
				
			if not mp4_found:
				print "No MP4 resource found. Using hidden video url logic"
				resources_entry["Lecture Video"] = grab_hidden_video_url(data_lecture_view_link, opener)
				
	return {'sections':ret, 'instructor_name':instructor_name}

