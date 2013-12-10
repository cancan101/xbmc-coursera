'''
Created on Nov 7, 2012

@author: alex
'''
import json
import urllib2
import urllib
from BeautifulSoup import BeautifulSoup
import re
import string
from urllib2 import HTTPError

def get_page(href, opener, data=None):
	req = urllib2.Request(href,data=data)
	try:
		return opener.open(req).read()
	except HTTPError:
		return None

def get_page_redirect(href, opener):
	req = urllib2.Request(href)
	return opener.open(req).geturl()	
	
def get_syllabus_url(className):
	"""Return the Coursera index/syllabus URL."""
	return "http://class.coursera.org/%s/lecture/index" % className


def get_auth_url(className):
	return "http://class.coursera.org/%s/auth/auth_redirector?type=login&subtype=normal&email=&visiting=&minimal=true" % className

def login_to_class(className, opener, username, password):
	auth_url = get_auth_url(className)
	ref = get_page_redirect(href=auth_url, opener=opener)
	
	print "Following login redirect from auth_url=%s to: %s" % (auth_url, ref)

	classLogin_txt = get_page(ref, opener)
	
	soup = BeautifulSoup(classLogin_txt)
	
	classLogin_title = soup.html.head.title.string.strip()
	
	if classLogin_title == "Coursera Login":
		print "We are not currently logged-in. Attempting login"
		data = urllib.urlencode({'email': username, 'password': password, 'login': 'Login'})
		classLogin_txt = get_page(href=ref, opener=opener, data=data)
		
		soup = BeautifulSoup(classLogin_txt)
	
		classLogin_title = soup.html.head.title.string.strip()

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
		print "Unknown state (from title): %s" % classLogin_title
		return False

def grab_hidden_video_url(href, opener):
	"""
	Follow some extra redirects to grab hidden video URLs (like those from
	University of Washington).
	"""
	page = get_page(href, opener)
	if page is None:
		return None
	
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
	file_format = re.search("(?:\.|format=)(\w+)(?:\?.*)?$", a)
	return file_format.group(1) if file_format else None

def parse_syllabus(page_txt, opener):
	if "Sorry, this class site is now closed" in page_txt:
		return "CLOSED"
		
	ret = {}
	
	soup = BeautifulSoup(page_txt)
#	import pdb;pdb.set_trace()
	
	name_tag = soup.find(attrs={'class':'course-instructor-name'}) or soup.find(attrs={'class':'course-topbanner-instructor'})
	if name_tag is not None:
		instructor_name = name_tag.string
	else:
		instructor_name = ""
#	print "instructor_name=%s" % instructor_name
		
	role_tag = soup.find(attrs={'class':'course-time'}) or soup.find(attrs={'class':'course-topbanner-time'})
	if role_tag is not None:
		instructor_role = role_tag.string.strip()
	else:
		instructor_role = ""
#	print "instructor_role=%s" % instructor_role
	
	course_logo = soup.find(attrs={'class':"course-logo-name"}) or soup.find(attrs={'class':"course-topbanner-logo-name"})
	if course_logo is not None:
#		print "Course name = %s" % course_logo.text
		course_name = course_logo.text
	else:
		course_name = ""
				
	sections = soup.findAll(attrs={'class':['list_header_link expanded', 'list_header_link contracted', "course-item-list-header expanded", "course-item-list-header contracted"]})
	for section_num,section in enumerate(sections):
		heading = section.find(attrs={'class':'list_header'}) or section.find("h3")
		if heading is None:
			print "Unable to parse section. no heading node"
			continue
#		else:
#			heading = heading.nextSibling
		
		heading_text = heading.find(text=True)# heading.string
		if heading_text is None:
			print "Unable to parse section. no heading text"
			continue
		
		heading_text = heading_text.replace("&nbsp;", " ").replace("&quot;", '"')
		
		heading_text = heading_text.strip()
#		print heading_text
		section_entry = ret[heading_text] = {}
		section_entry['section_num'] = section_num
		
		sections_entry = section_entry['sections'] = {}
		
		section_entries = section.nextSibling
		if section_entries is None:
			print "Unable to parse section: %s" % (heading_text)
			continue
		
		lectures = section_entries.findAll('li')
		for lecture_num, lecture in enumerate(lectures):
			lecture_title = lecture.find(attrs={'class':'lecture-link'})
			if lecture_title is None:
				print "Unable to parse lecture in %s (lecture_title is None)" % (heading_text)
				continue
			
			data_lecture_view_link = lecture_title.get('data-lecture-view-link') or lecture_title.get('data-modal-iframe')
			lecture_id = lecture_title.get('data-lecture-id')
			
			lecture_title_str = lecture_title.find(text=True)
			if lecture_title_str is None:
				print "Unable to parse lecture in %s" % (heading_text)
				continue
			
			lecture_title_str = lecture_title_str.strip().replace("&quot;", '"')
#			print "- %s (%s)" % (lecture_title_str, data_lecture_view_link)
			
			lecture_entry = sections_entry[lecture_title_str] = {}
			
			lecture_entry["viewed"] = lecture.get('class') in ['item_row viewed', 'viewed']
			
			lecture_entry['data_lecture_view_link'] = data_lecture_view_link
			lecture_entry["lecture_num"] = lecture_num
			lecture_entry["lecture_id"] = lecture_id
			resources_entry = lecture_entry['resources'] = {}
			
			resources = lecture.find(attrs={'class':['item_resource', "course-lecture-item-resource"]})
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
					resources_entry["Lecture Video"] = href
				elif resource_format == 'srt':
					resources_entry["Subtitle"] = href
					
				resources_entry[title] = href
				
			if not mp4_found:
				print "No MP4 resource found. Using hidden video url logic"
				resources_entry["Lecture Video"] = grab_hidden_video_url(data_lecture_view_link, opener)
				
	return {'sections':ret, 'instructor_name':instructor_name, 'instructor_role':instructor_role, 'course_name':course_name}

