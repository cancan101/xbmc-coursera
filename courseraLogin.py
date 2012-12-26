'''
Created on Nov 5, 2012

@author: alex
'''

import urllib2, urllib
import cookielib
import random
import string
import json

#########

def saveUserData(cookies, external_id, public_id):
	data = {'cookies':cookies, 'external_id': external_id, 'public_id':public_id}	
	
	cookie_file = open('cookie.txt', 'w')
	
	json.dump(obj=data, fp=cookie_file, indent=3)	
	
	cookie_file.close()	

CSRFT_TOKEN_COOKIE_NAME = "csrftoken"

def cookieToDict(cookie):
	ret = {}
	for name in ("version", "name", "value",
				 "port", "port_specified",
				 "domain", "domain_specified", "domain_initial_dot",
				 "path", "path_specified",
				 "secure", "expires", "discard", "comment", "comment_url",
				 ):
		attr = getattr(cookie, name)
		ret[name] = attr
	ret["rest"] = cookie._rest
	ret["rfc2109"] = cookie.rfc2109
	return ret


def saveCJ(cj):
	cookies = []
	for cookie in cj:
		cookies.append(cookieToDict(cookie))

	return cookies

def makeCSRFToken():
	csrftoken = ''.join(random.choice(string.ascii_uppercase + string.digits + string.ascii_lowercase) for _ in xrange(24))
	return csrftoken


def makeLoginRequest(username, password, csrftoken):
	params = urllib.urlencode({'email_address':username, 'password':password})
	req = urllib2.Request("https://www.coursera.org/maestro/api/user/login", params)
	req.add_header('Referer','https://www.coursera.org/account/signin')
	req.add_header('Host',"www.coursera.org")
	req.add_header('X-CSRFToken', csrftoken)
	req.add_header('X-Requested-With', 'XMLHttpRequest')
	
	return req

def login(username, password):
	cj = cookielib.CookieJar()
	opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
	#req = urllib2.Request('https://www.coursera.org/account/signin')
	#req.add_header('Host',"www.coursera.org")
	#opener.open(req)
	
	csrftoken = makeCSRFToken()
	
	#print "%s=%s" % (CSRFT_TOKEN_COOKIE_NAME, csrftoken)
	
	c = cookielib.Cookie(None, CSRFT_TOKEN_COOKIE_NAME, csrftoken, None, None, "", None, None, "/", None, True, None, None, None, None, None, None)
	cj.set_cookie(c)
	
	
	req = makeLoginRequest(username, password, csrftoken)
	response = opener.open(req)
	logIn_resp = response.read()
	
	logIn_resp_dict = json.loads(logIn_resp)
	
	#print logIn_resp_dict
	
	external_id = str(logIn_resp_dict["external_id"])
	public_id = str(logIn_resp_dict["id"])
	
	cj.clear("", "/", CSRFT_TOKEN_COOKIE_NAME)
	
	#cj.clear("www.coursera.org", "/", "maestro_login")
	#cj.clear("www.coursera.org", "/", "sessionid")
	
	
	return external_id, public_id, saveCJ(cj) 

