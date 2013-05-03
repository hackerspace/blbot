# -*- coding: utf-8 -*-
import time, sys, json

from twisted.python import log
from twisted.words.protocols import irc
from twisted.web import server, resource
from twisted.internet import task, reactor, protocol, ssl

import settings as cfg
import wol

has_gpio = False
try:
    import RPi.GPIO as GPIO
    has_gpio = True
except ImportError:
    print('GPIO not available')

# these should probably go somewhere into the reactor, but i'd have to read the
# documentation to know where ...
base_open = False
last_change = '1337'

def gpio_setup():
    if not has_gpio:
        return
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(cfg.GPIO_OUT_PIN, GPIO.OUT)
    # set up GPIO input with pull-up control
    #   (pull_up_down be PUD_OFF, PUD_UP or PUD_DOWN, default PUD_OFF)
    GPIO.setup(cfg.GPIO_IN_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    cs = GPIO.input(cfg.GPIO_IN_PIN)
    if cs:
        GPIO.output(cfg.GPIO_OUT_PIN, GPIO.HIGH)
    else:
        GPIO.output(cfg.GPIO_OUT_PIN, GPIO.LOW)

def gpio_cleanup():
    if not has_gpio:
        return
    GPIO.cleanup()

def should_replace(str_a, str_b):
    if len(str_b) < len(str_a):
        return False

    similar = len(str_a) - sum(
        map(lambda (x,y): int(x == y), zip(str_a, str_b)))
    return similar < cfg.REPLACE_THRESHOLD

class BlBot(irc.IRCClient):
    username = cfg.USERNAME
    nickname = cfg.NICKNAME
    password = cfg.PASSWORD
    ready = False
    ctopic = ''
    ticho = 0
    global base_open, last_change

    task = None
    hw_task = None
    topic_task = None

    def hw_poll(self, *args, **kwargs):
        new_state = GPIO.input(cfg.GPIO_IN_PIN)
        if base_open != new_state:
            last_change = time.time()

        base_open = new_state
        if base_open:
            GPIO.output(cfg.GPIO_OUT_PIN, GPIO.HIGH)
        else:
            GPIO.output(cfg.GPIO_OUT_PIN, GPIO.LOW)

    def poll(self, *args, **kwargs):
        if not self.ready:
            print('not ready')
            return

        if self.ticho > 0:
            self.ticho -= cfg.POLL_INTERVAL
            print(self.ticho)
            return

        if base_open:
            new = self.ctopic.replace(cfg.C, cfg.O)
        else:
            new = self.ctopic.replace(cfg.O, cfg.C)

        if cfg.C not in new and cfg.O not in new:
            state = cfg.C
            if base_open:
                state = cfg.O

            new = '%s %s' % (state, self.ctopic)
            if should_replace(state, self.ctopic):
                tok = state.split()
                ttok = self.ctopic.split()

                if len(ttok) > len(tok):
                    new = ' '.join(tok + ttok[len(tok):])
                else:
                    new = state

            self.describe(cfg.CHAN, 'is disappoint')

        if new != self.ctopic:
            self.topic(cfg.CHAN, new)

    def check_topic(self, *args, **kwargs):
        self.topic(cfg.CHAN)

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        print('connected')
        if not self.hw_task and has_gpio:
            self.hw_task = task.LoopingCall(self.hw_poll, (self,))
            self.hw_task.start(cfg.HW_POLL_INTERVAL)

    def joined(self, channel):
        print('joined %s' % channel)
        self.ready = True
        if not self.task:
            self.task = task.LoopingCall(self.poll, (self,))
            self.task.start(cfg.POLL_INTERVAL, now=False)

        if not self.topic_task:
            self.topic_task = task.LoopingCall(self.check_topic, (self,))
            self.topic_task.start(cfg.TOPIC_INTERVAL)

    def left(self, channel):
        print('left %s' % channel)
        self.ready = False

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)
        print('disconnected')

    def signedOn(self):
        self.join(cfg.CHAN)

    def privmsg(self, user, channel, msg):
        user = user.split('!', 1)[0]
        print("<%s> %s" % (user, msg))

        out = ''
        if user == 'rmarko' and ':' in msg:
            tokens = map(lambda x: x.strip(), msg.split(':'))
            print('tok: %s' % tokens)
            if 'ticho' in tokens:
                self.ticho = cfg.TICHO
                out = "%s: :-x" % user

            if 'zmizni' in tokens:
                reactor.stop()
        elif (user == 'rmarko' or user == 'hexo') and ':' in msg:
            tokens = map(lambda x: x.strip(), msg.split(':'))
            ts = tokens[1].split(' ')
            if ts[0] == 'wolinfo' and ts[1] == cfg.WOL_PWD:
                out = str(WOL_HOSTS)
            if ts[0] == 'wol' and ts[2] == cfg.WOL_PWD
                and cfg.WOL_PWD.has_key(ts[1]):
                out = 'waking %s (%s)' % (cfg.WOL_HOSTS[ts[1]], ts[1])
                wol.wake_on_lan(cfg.WOL_HOStS[ts[1]], cfg.WOL_BROADCAST)

        if out:
            self.msg(channel, out)

    def handleCommand(self, command, prefix, params):
        irc.IRCClient.handleCommand(self, command, prefix, params)
        print('%s %s %s' % (command, prefix, params))

    def topicUpdated(self, user, channel, newtopic):
        self.ctopic = newtopic
        print("topic update: %s %s" % (user, newtopic))

    # irc callbacks
    def irc_NICK(self, prefix, params):
        """Called when an IRC user changes their nickname."""
        old_nick = prefix.split('!')[0]
        new_nick = params[0]
        print("%s is now known as %s" % (old_nick, new_nick))

    # For fun, override the method that determines how a nickname is changed on
    # collisions. The default method appends an underscore.
    def alterCollidedNick(self, nickname):
        """
        Generate an altered version of a nickname that caused a collision in an
        effort to create an unused related name for subsequent registration.
        """
        return nickname + 'o'

class BlBotFactory(protocol.ClientFactory):
    def buildProtocol(self, addr):
        p = BlBot()
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        """If we get disconnected, reconnect to server."""
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print("connection failed:", reason)
        reactor.stop()

class BlBotWebResource(resource.Resource):
    isLeaf = True

    def render_GET(self, request):
        request.setHeader("Content-Type", "application/json")
        request.setHeader("Access-Control-Allow-Origin", "*")
        request.setHeader("Cache-Control", "no-cache")
        global base_open, last_change
        status = {
            'api': '0.12',
            'space': cfg.SPACE_NAME,
            'logo': cfg.SPACE_LOGO,
            'icon': {'open': cfg.ICON_OPEN, 'closed': cfg.ICON_CLOSED},
            'url': cfg.SPACE_WEB,
            'address': cfg.CONTACT_ADDR,
            'contact': {
                'irc': cfg.CONTACT_IRC,
                'ml': cfg.CONTACT_ML,
            },
            'lat': cfg.CONTACT_LAT,
            'lon': cfg.CONTACT_LON,
            'open': base_open,
            'lastchange': long(last_change),
            'feeds': [
                {'name': 'news', 'type': 'application/rss+xml', 'url': cfg.FEED_NEWS},
                {'name': 'events', 'type': 'text/calendar', 'url': cfg.FEED_EVENTS}
            ]

        }
        return json.dumps(status, indent=2)

if __name__ == '__main__':
    log.startLogging(sys.stdout)
    f = BlBotFactory()

    gpio_setup()

    if cfg.SSL:
        reactor.connectSSL(cfg.SERVER, cfg.PORT, f , ssl.ClientContextFactory())
    else:
        reactor.connectTCP(cfg.SERVER, cfg.PORT, f)
    if cfg.SPACEAPI_ENABLED:
        reactor.listenTCP(cfg.SPACEAPI_PORT, server.Site(BlBotWebResource()), interface='::')
    reactor.addSystemEventTrigger('before', 'shutdown', gpio_cleanup)
    reactor.run()
