'''
Created on Nov 7, 2012

@author: alex
'''
import datetime
import operator
import re
import string

from BeautifulSoup import BeautifulSoup
from xbmcswift2 import Plugin
import requests

from coursera_login import (getClassCookies, getClassCookieOrLogin,
                            loadSavedClassCookies, login)

plugin = Plugin()

BASE_CLASS_URL = "https://class.coursera.org"

COURSES_LIST_URL = (
    "https://www.coursera.org/api/memberships.v1?fields=courseId,"
    "enrolledTimestamp,grade,id,lastAccessedTimestamp,role,v1SessionId,vc,"
    "vcMembershipId,courses.v1(partnerIds,photoUrl,specializations,startDate,"
    "description, v1Details),partners.v1(homeLink,name),v1Details.v1("
    "sessionIds),v1Sessions.v1(dbEndDate,durationString,hasSigTrack,startDay,"
    "startMonth,startYear),specializations.v1(logo,name,partnerIds,shortName)"
    "&includes=courseId,vcMembershipId,courses.v1(partnerIds,specializations,"
    "v1Details),v1Details.v1(sessionIds),specializations.v1(partnerIds)&q=me&"
    "filter=archived,current")


def isSettingsBad(username, password):
    return not username or not password


@plugin.cached()
def loadClasses(username, password):
    user_data = plugin.get_storage(username, file_format='json')

    cookies_raw = user_data.get('cookies')

    did_login = False
    if cookies_raw is None:
        plugin.log.info("Logging in")
        cookies_raw = login(username, password)
        user_data['cookies'] = cookies_raw
        did_login = True
    else:
        plugin.log.debug("Loading data from store")

    try:
        classes = getClasses(cookies=cookies_raw)
    except requests.HTTPError as ex:
        if ex.code not in [403, 401]:
            raise ex

        if did_login:
            raise Exception('Login failed')

        plugin.log.info("Maybe cookies is old? Logging in")
        cookies_raw = login(username, password)
        user_data['cookies'] = cookies_raw

        classes = getClasses(cookies=cookies_raw)

    return classes


def get_page(href, json=False, **kwargs):
    res = requests.get(href, **kwargs)
    if not res.ok:
        res.raise_for_status()
    return res.content if not json else res.json()


def get_syllabus_url(className):
    """Return the Coursera index/syllabus URL."""
    return "%s/%s/lecture" % (BASE_CLASS_URL, className)


@plugin.cached()
def getSylabus(className, username, password):
    plugin.log.info("getSylabus for %s." % className)

    cookies, didLogin = getClassCookieOrLogin(username, password, className,
                                              indicateDidLogin=True)
    url = get_syllabus_url(className=className)

    sylabus_txt = get_page(url, cookies=cookies, allow_redirects=False)
    plugin.log.debug("sylabus_txt = %s", sylabus_txt)
    not_logged_in = 'with a Coursera account' in sylabus_txt or (
        "// First check the URL and line number of the error" in sylabus_txt)

    if not_logged_in:
        if didLogin:
            raise Exception("Unable to login to class")
        else:
            plugin.log.info("Cookies for %s are old. Logging in to class",
                            className)
            cookies = getClassCookies(className, username, password)
            sylabus_txt = get_page(url, cookies=cookies, allow_redirects=False)
            plugin.log.debug("sylabus_txt = %s", sylabus_txt)
            not_logged_in = 'with a Coursera account' in sylabus_txt or (
                "// First check the URL and line number of the error"
                in sylabus_txt)
            if not_logged_in:
                raise Exception("Unable to login to class")
            else:
                cookies_class = loadSavedClassCookies(username)
                cookies_class[className] = cookies.get_dict()

    parsed = parse_syllabus(sylabus_txt)

    return parsed


def get_start_date_string(session):
    if all(session.get(d) for d in ['startYear', 'startMonth']):
        date = datetime.date(year=session.get('startYear'),
                             month=session.get('startMonth'),
                             day=session.get('startDay', 1))
        return date.strftime("%d %B %Y") if (
            session.get('startDay')) else date.strftime("%B %Y")
    return "Self study"


def parse_classes(classes_data):
    """
    Takes a json response of session/courses, returns a dictionary of the
    following form:
    { 'v1-987': {
        'id': 'v1-987',
        'name': 'Principles of Reactive Programming',
        'partnerIds': ['16'],
        'photoUrl': '<class-photo.jpg>',
        'slug': 'reactive',
        'sessions': [{
            'courseId': 'v1-987',
            'courseType': 'v1.session',
            'dbEndDate': 1387756800000,
            'durationString': '7 weeks',
            'hasSigTrack': False,
            'homeLink': 'https://class.coursera.org/reactive-001/',
            'sessionId': 971465,
            'specializations': [],
            'startDay': 4,
            'startMonth': 11,
            'startYear': 2013,
            'startDateString': '04-11-2013'
        }, ...  # more sessions ],
    }, ...  # more classes }
    """
    classes = {}
    course_metadata = {}
    for course in classes_data['linked']['courses.v1']:
        course_metadata[course['id']] = course

    sorted_sessions = sorted(classes_data['linked']['v1Sessions.v1'],
                             key=operator.itemgetter('id'), reverse=True)
    for session in sorted_sessions:
        course_id = session['courseId']
        session['startDateString'] = get_start_date_string(session)
        if course_id not in classes:
            classes[course_id] = course_metadata[course_id].copy()
        if 'sessions' not in classes[course_id]:
            classes[course_id]['sessions'] = []
        classes[course_id]['sessions'].append(session)
    return classes


def getClasses(**kwargs):
    data = get_page(COURSES_LIST_URL, json=True, **kwargs)
    return parse_classes(data)


title_re1 = re.compile("^(.*) \((\d+\:\d{2})\)$")
title_re2 = re.compile("^\d+\-\d+\: (.*) \((\d+m\d{2})s\)$")
title_re3 = re.compile("^(.*) \((\d+m\d{2})s\)$")


def extractDuration(section):
    match = title_re1.match(section)
    if match:
        return match.group(1).strip(), match.group(2)
    match = title_re2.match(section)
    if match:
        return match.group(1).strip(), match.group(2).replace('m', ":")
    match = title_re3.match(section)
    if match:
        return match.group(1).strip(), match.group(2).replace('m', ":")
    return section, None


def getContentURL(section, cookies):
    url = section['resources']["Lecture Video"]
    if url is None:
        return None
    res = requests.head(section['resources']["Lecture Video"], cookies=cookies)
    if res.is_redirect and 'location' in res.headers:
        return res.headers['location']  # get video after another jump
    return url


def clean_filename(s):
    """Sanitize a string to be used as a filename."""
    # strip paren portions which contain trailing time length (...)
    s = re.sub("\([^\(]*$", "", s)
    s = s.strip().replace(':', '-').replace(' ', '_')
    valid_chars = "-_.()%s%s" % (string.ascii_letters, string.digits)
    return ''.join(c for c in s if c in valid_chars)


def get_anchor_format(a):
    """Extract the resource file-type format from the anchor"""
    # (. or format=) then (file_extension) then (? or $)
    # e.g. "...format=txt" or "...download.mp4?..."
    file_format = re.search("(?:\.|format=)(\w+)(?:\?.*)?$", a)
    return file_format.group(1) if file_format else None


def parse_syllabus(page_txt):
    if "Sorry, this class site is now closed" in page_txt:
        return "CLOSED"

    ret = {}

    soup = BeautifulSoup(page_txt)

    name_tag = soup.find(
        attrs={'class': 'course-instructor-name'}) or soup.find(
            attrs={'class': 'course-topbanner-instructor'})
    if name_tag is not None:
        instructor_name = name_tag.string
    else:
        instructor_name = ""

    role_tag = soup.find(
        attrs={'class': 'course-time'}) or soup.find(
            attrs={'class': 'course-topbanner-time'})
    if role_tag is not None:
        instructor_role = role_tag.string.strip()
    else:
        instructor_role = ""

    course_logo = soup.find(
        attrs={'class': "course-logo-name"}) or soup.find(
            attrs={'class': "course-topbanner-logo-name"})
    if course_logo is not None:
        course_name = course_logo.text
    else:
        course_name = ""

    sections = soup.findAll(
        attrs={'class': [
            'list_header_link expanded', 'list_header_link contracted',
            "course-item-list-header expanded",
            "course-item-list-header contracted"]})
    for section_num, section in enumerate(sections):
        heading = section.find(
            attrs={'class': 'list_header'}) or section.find("h3")
        if heading is None:
            plugin.log.debug("Unable to parse section. no heading node")
            continue

        heading_text = heading.find(text=True)  # heading.string
        if heading_text is None:
            plugin.log.debug("Unable to parse section. no heading text")
            continue

        heading_text = heading_text.replace(
            "&nbsp;", " ").replace("&quot;", '"')

        heading_text = heading_text.strip()
        plugin.log.debug(heading_text)
        section_entry = ret[heading_text] = {}
        section_entry['section_num'] = section_num

        sections_entry = section_entry['sections'] = {}

        section_entries = section.nextSibling
        if section_entries is None:
            plugin.log.debug("Unable to parse section: %s", heading_text)
            continue

        lectures = section_entries.findAll('li')
        for lecture_num, lecture in enumerate(lectures):
            lecture_title = lecture.find(attrs={'class': 'lecture-link'})

            if lecture_title is None:
                plugin.log.debug("Unable to parse lecture in %s ("
                                 "lecture_title is None)", heading_text)
                continue

            data_lecture_view_link = lecture_title.get(
                'data-lecture-view-link') or lecture_title.get(
                    'data-modal-iframe')
            lecture_id = lecture_title.get('data-lecture-id')

            lecture_title_str = lecture_title.find(text=True)
            if lecture_title_str is None:
                plugin.log.debug("Unable to parse lecture in %s", heading_text)
                continue

            lecture_title_str = lecture_title_str.strip().replace("&quot;", '"')
            plugin.log.debug("- %s (%s)", lecture_title_str,
                             data_lecture_view_link)

            lecture_entry = sections_entry[lecture_title_str] = {}

            lecture_entry["viewed"] = lecture.get('class') in [
                'item_row viewed', 'viewed']

            lecture_entry['data_lecture_view_link'] = data_lecture_view_link
            lecture_entry["lecture_num"] = lecture_num
            lecture_entry["lecture_id"] = lecture_id
            resources_entry = lecture_entry['resources'] = {}

            resources = lecture.find(
                attrs={'class': [
                    'item_resource', "course-lecture-item-resource"
                ]})
            if resources is None:
                plugin.log.debug("Unable to find resources for lecture %s in"
                                 "%s", lecture_title_str, heading_text)
                continue

            mp4_found = False
            for resource in resources.findAll('a'):
                href = resource['href']
                title = resource['title']
                resource_format = get_anchor_format(href)

                plugin.log.debug("-- %s (%s) format=%s",
                                 title, href, resource_format)
                if resource_format == 'mp4':
                    mp4_found = True
                    resources_entry["Lecture Video"] = href
                elif resource_format == 'srt':
                    resources_entry["Subtitle"] = href

                resources_entry[title] = href

            if not mp4_found:
                plugin.log.error("No MP4 resource found. Using hidden video "
                                 "url logic")

    return {
        'sections': ret,
        'instructor_name': instructor_name,
        'instructor_role': instructor_role,
        'course_name': course_name
    }
