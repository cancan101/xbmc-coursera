import time

from xbmcswift2 import Plugin, xbmc, SortMethod, logger
import requests

from course_utils import (extractDuration, getContentURL, getSylabus,
                          isSettingsBad, loadClasses)
from coursera_login import getClassCookies

plugin = Plugin()

if plugin.get_setting('enable_debug', bool):
    plugin.log.setLevel(level=logger.logging.DEBUG)


@plugin.route('/classes/', name="classes")
@plugin.route('/', name="index")
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
    except requests.HTTPError as ex:
        if ex.code != 401:
            raise ex

        plugin.notify(msg="Unable to login to Coursera")
        plugin.log.warn("Unable to login to Coursera")
        return []

    plugin.log.debug(classes)
    plugin.add_sort_method(SortMethod.TITLE_IGNORE_THE)

    items = []
    for slug, c in classes.iteritems():
        url = plugin.url_for('listCourses', slug=slug)
        items.append({
            'label': c["name"],
            'path': url,
            'is_playable': False,
            'label2': c.get("description", ""),
            'icon': c['photoUrl'],
            'thumbnail': c['photoUrl'],
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


def get_session_short_name(course):
    home_link = course["homeLink"]
    return home_link.replace("https://class.coursera.org/", "")[:-1]


@plugin.cached_route('/classes/<slug>/')
def listCourses(slug):
    username = plugin.get_setting('username')
    password = plugin.get_setting('password')

    if isSettingsBad(username, password):
        return []

    classes = loadClasses(username, password)
    if slug not in classes:
        plugin.log.warn("%s not found in classes: %s",
                        slug, [x["slug"] for x in classes])
        return []

    course = classes[slug]
    sessions = course['sessions']

    if len(sessions) == 1:
        plugin.log.debug("Only one item found")
        return listCourseContents(
            courseShortName=get_session_short_name(sessions[0]))

    ret = []
    for session in sessions:
        label = session.get('startDateString', 'Unknown')
        duration_string = session.get('durationString')
        if duration_string:
            label = "%s (%s)" % (label, duration_string)
        short_name = get_session_short_name(session)
        url = plugin.url_for('listCourseContents', courseShortName=short_name)

        ret.append({
            'label': label,
            'path': url,
            'icon': course['photoUrl'],
            'thumbnail': course['photoUrl'],
            'is_playable': False
        })
    return ret


@plugin.cached_route('/courses/<courseShortName>/')
def listCourseContents(courseShortName):
    username = plugin.get_setting('username')
    password = plugin.get_setting('password')
    number_episodes = plugin.get_setting('number_episodes', bool)

    if isSettingsBad(username, password):
        return []

    sylabus = getSylabus(courseShortName, username, password)
    if sylabus is None:
        return []
    elif sylabus == "CLOSED":
        return [{
            'label': "%s is no longer available on Coursera" % courseShortName,
            'path': plugin.url_for(endpoint="index")
        }]

    sylabus = sylabus['sections']

    ret = []
    for lecture in sorted(sylabus.keys(),
                          key=lambda x: sylabus[x]["section_num"]):
        section_num = sylabus[lecture]["section_num"]
        label = lecture
        if number_episodes:
            label = "%d. %s" % (section_num+1, label)
        ret.append({
            'label': label,
            'path': plugin.url_for(endpoint="listLectureContents",
                                   courseShortName=courseShortName,
                                   section_num=str(section_num)),
            'is_playable': False,
            'info': {
                'season': section_num+1,
                'title': lecture,
            }
        })
    return ret


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
                plugin.log.debug("FOUND!: %s", section_name.encode(
                    'ascii', 'ignore'))

                cookies = getClassCookies(courseShortName, username, password)
                path = getContentURL(section, cookies)
                if path is not None:
                    plugin.log.info('Handle: ' + str(plugin.handle))

                    plugin.set_resolved_url(path)

                    if "Subtitle" in section['resources']:
                        player = xbmc.Player()
                        while not player.isPlaying():
                            time.sleep(1)
                        player.setSubtitles(section['resources']["Subtitle"])

                break


@plugin.cached_route('/courses/<courseShortName>/sections/<section_num>/')
def listLectureContents(courseShortName, section_num):
    username = plugin.get_setting('username')
    password = plugin.get_setting('password')
    number_episodes = plugin.get_setting('number_episodes', bool)

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
        plugin.log.warn("Lecture %d for %s not found",
                        section_num, courseShortName)
        return []

    section_lecture = lecture_desired["sections"]

    ret = []
    for section_name, section in section_lecture.iteritems():
        title, duration = extractDuration(section_name)

        lecture_num = section['lecture_num']  # int(section["lecture_id"])

        play_url = plugin.url_for(endpoint="playLecture",
                                  courseShortName=courseShortName,
                                  lecture_id=str(section["lecture_id"]))

        episode_num = lecture_num+1

        if number_episodes:
            title = "%d. %s" % (episode_num, title)

        info = {
            'episode': episode_num,
            'season': int(section_num)+1,
            'title': title,
            'watched': section["viewed"],
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

        if plugin.get_setting('enable_subtitles', bool):
            path = play_url
            if section['resources']["Lecture Video"] is None:
                path = None
        else:
            cookies = getClassCookies(courseShortName, username, password)
            path = getContentURL(section, cookies)

        plugin.log.debug(info)
        if path is not None:
            ret.append({
                'label': title,
                'path': path,
                'is_playable': True,
                'info': info,
                'context_menu': [
                    ("Play with subtitles", "XBMC.RunPlugin(%s)" % play_url),
                    ("Play with subtitles2", "XBMC.PlayMedia(%s)" % play_url)
                ],
            })
    plugin.add_sort_method(SortMethod.EPISODE)
    plugin.log.debug(dir(SortMethod))
    return list(sorted(ret, key=lambda x: x["info"]["episode"]))

if __name__ == '__main__':
    plugin.run()
