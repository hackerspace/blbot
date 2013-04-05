# -*- coding: utf-8 -*-
# No UTF-8 support in twisted.words?!
#O = u'space open ♥'
#C = u'space closed ♡'

O = 'space open \\o/'
C = 'space closed /o\\'

TICHO = 60
POLL_INTERVAL = 5.0
HW_POLL_INTERVAL = 0.7
TOPIC_INTERVAL = 60.0

REPLACE_THRESHOLD = 5

CHAN = '#coze'
USERNAME = 'blbot'
NICKNAME = 'blbot'
PASSWORD = ''
SERVER = 'irc.freenode.net'
PORT = 7070
SSL = True

SPACEAPI_ENABLED = True
SPACEAPI_PORT = 8080
SPACE_NAME = 'dolanspace'
SPACE_WEB = 'http://example.org/'
SPACE_LOGO = 'http://example.org/logo.png'
ICON_OPEN = 'http://example.org/open.png'
ICON_CLOSED = 'http://example.org/closed.png'
CONTACT_ADDR = 'Odfuknute 48, 66642 Warsaw, Poland'
CONTACT_IRC = 'irc://freenode/#blbot'
CONTACT_ML = 'public@lists.exampl.org'
CONTACT_LAT = 0.0
CONTACT_LON = 0.0
FEED_NEWS = 'http://example.org/news.rss'
FEED_EVENTS = 'http://example.org/events.ics'

try:
    execfile('local_settings.py')
except:
    pass
