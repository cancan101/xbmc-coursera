'''
Created on Nov 5, 2012

@author: alex
'''
import random
import string

from xbmcswift2 import Plugin
import requests

plugin = Plugin()

BASE_CLASS_URL = "https://class.coursera.org"
LOGIN_URL = "https://accounts.coursera.org/api/v1/login"


def makeCSRFToken():
    csrftoken = ''.join(random.choice(string.ascii_uppercase + string.digits +
                                      string.ascii_lowercase)
                        for _ in xrange(24))
    return csrftoken


def login(username, password):
    csrftoken = makeCSRFToken()
    headers = {
        'Referer': 'https://www.coursera.org/account/signin',
        'Host': "accounts.coursera.org",
        'X-CSRFToken': csrftoken,
        'X-Requested-With': 'XMLHttpRequest',
        'Origin': 'https://accounts.coursera.org',
        'Cookie': 'csrftoken=%s' % csrftoken,
    }
    data = dict(email=username, password=password, webrequest='true')
    res = requests.post(LOGIN_URL, data=data, headers=headers)
    assert res.ok, "Could not login: %s" % res.content
    return res.cookies.get_dict()


def get_auth_url(className):
    return ("%s/%s/auth/auth_redirector?type=login&"
            "subtype=normal&email=&visiting=&minimal=true") % (
                BASE_CLASS_URL, className)


@plugin.cached()
def getClassCookies(className, username, password):
    user_data = plugin.get_storage(username, file_format='json')
    if user_data is None:
        return None

    cookies_raw = user_data.get('cookies')
    if cookies_raw is None:
        cookies_raw = login(username, password)
        if cookies_raw is None:
            return None
        user_data['cookies'] = cookies_raw

    res = requests.get(get_auth_url(className), allow_redirects=False,
                       cookies=cookies_raw)
    res.raise_for_status()
    cookies = res.cookies.get_dict()
    cookies.update(cookies_raw)
    return cookies


def loadSavedClassCookies(username):
    user_data = plugin.get_storage(username, file_format='json')

    cookies_class = user_data.get('cookies_class')
    if cookies_class is None:
        cookies_class = user_data['cookies_class'] = {}

    return cookies_class


def getClassCookieOrLogin(username, password, courseShortName):

    cookies_class = loadSavedClassCookies(username)

    class_cookies = cookies_class.get(courseShortName)
    if class_cookies is None:
        plugin.log.debug("Cookies for %s not found. Logging in to class",
                         courseShortName)
        class_cookies = getClassCookies(courseShortName, username, password)

        if class_cookies is not None:
            cookies_class[courseShortName] = class_cookies
        else:
            raise Exception("Unable to login to class")

    return class_cookies
