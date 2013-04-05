# -*- coding: utf-8 -*-
import sys
import time
import json
import subprocess

from twisted.python import log
from twisted.words.protocols import irc
from twisted.web import server, resource
from twisted.internet import task, reactor, protocol, ssl

import settings as cfg

has_gpio = False

IN1 = 32
IN2 = 33
OUT1 = 34
OUT2 = 35
OUT3 = 37

BELL = IN1
SWITCH = IN2

DATA = OUT1
CLOCK = OUT3
LATCH = OUT2

BASE_RED = 0
BASE_GREEN = 1
STATUS_GREEN_1 = 2
STATUS_GREEN_2 = 3
RED = 4
YELLOW = 5


def gpio_setup():
    if has_gpio:
        p = subprocess.Popen(['wrap_setup_gpio'])
        p.wait()


def should_replace(str_a, str_b):
    if len(str_b) < len(str_a):
        return False

    similar = len(str_a) - sum(
        map(lambda (x, y): int(x == y), zip(str_a, str_b)))
    return similar < cfg.REPLACE_THRESHOLD


class BlBot(irc.IRCClient):
    username = cfg.USERNAME
    nickname = cfg.NICKNAME
    password = cfg.PASSWORD
    ready = False
    ctopic = ''
    ticho = 0
    last_state = False

    task = None
    hw_task = None
    topic_task = None
    broadcast_task = None

    def poll(self, *args, **kwargs):
        if self.factory.base_open != self.last_state:
            self.factory.last_change = time.time()
            self.last_state = self.factory.base_open

        if not self.ready:
            print('not ready')
            return

        if self.ticho > 0:
            self.ticho -= cfg.POLL_INTERVAL
            print(self.ticho)
            return

        if self.factory.base_open:
            new = self.ctopic.replace(cfg.C, cfg.O)
        else:
            new = self.ctopic.replace(cfg.O, cfg.C)

        if cfg.C not in new and cfg.O not in new:
            state = cfg.C
            if self.factory.base_open:
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

    def poll_broadcast(self, *args, **kwargs):
        while self.factory.broadcast:
            msg = self.factory.broadcast.pop()
            self.describe(cfg.CHAN, msg)

    def check_topic(self, *args, **kwargs):
        self.topic(cfg.CHAN)

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        print('connected')

    def joined(self, channel):
        print('joined %s' % channel)
        self.ready = True
        if not self.task:
            self.task = task.LoopingCall(self.poll, (self,))
            self.task.start(cfg.POLL_INTERVAL, now=False)

        if not self.topic_task:
            self.topic_task = task.LoopingCall(self.check_topic, (self,))
            self.topic_task.start(cfg.TOPIC_INTERVAL)

        if not self.broadcast_task:
            self.broadcast_task = task.LoopingCall(self.poll_broadcast, (self,))
            self.broadcast_task.start(1)

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
    def __init__(self):
        self.base_open = False
        self.last_change = 1337
        self.broadcast = []

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

    def __init__(self, irc_factory):
        self.irc_factory = irc_factory

    def render_GET(self, request):
        request.setHeader("Content-Type", "application/json")
        request.setHeader("Access-Control-Allow-Origin", "*")
        request.setHeader("Cache-Control", "no-cache")
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
            'open': self.irc_factory.base_open,
            'lastchange': long(self.irc_factory.last_change),
            'feeds': [
                {'name': 'news', 'type': 'application/rss+xml', 'url': cfg.FEED_NEWS},
                {'name': 'events', 'type': 'text/calendar', 'url': cfg.FEED_EVENTS}
            ]

        }
        return json.dumps(status, indent=2)


class GPIOProto(protocol.ProcessProtocol):
    def __init__(self, irc_factory):
        self.data = ""
        self.on = False
        self.base_open = False
        self.shiftreg = 0
        self.bell_count = 0
        self.irc_factory = irc_factory

    def shift(self, val=None):
        if not val:
            val = self.shiftreg

        self.transport.write(
            "SHIFT %d %d %d %d\n" % (DATA, CLOCK, LATCH, val))

    def base_update(self):
        if self.base_open:
            self.shiftreg &= ~(1 << BASE_RED)
            self.shiftreg |= (1 << BASE_GREEN)
        else:
            self.shiftreg &= ~(1 << BASE_GREEN)
            self.shiftreg |= (1 << BASE_RED)

        self.shift()

    def blink_keep_alive(self):
        self.shiftreg ^= (1 << STATUS_GREEN_1)
        self.shift()
        self.shiftreg ^= (1 << STATUS_GREEN_2)
        self.shift()
        self.shiftreg &= ~(1 << STATUS_GREEN_1)
        self.shift()
        self.shiftreg &= ~(1 << STATUS_GREEN_2)
        self.shift()

    def bell_update(self):
        assert self.bell_count >= 0
        self.shiftreg &= ~(1 << RED)
        self.shiftreg &= ~(1 << YELLOW)

        if self.bell_count >= 2:
            self.shiftreg |= (1 << RED)

        if self.bell_count >= 4:
            self.irc_factory.broadcast.append('doorbell suckers')
            self.shiftreg |= (1 << YELLOW)
        self.shift()

    def clear_bell(self):
        if self.bell_count == 0:
            return

        self.bell_count -= 1
        self.bell_update()

    def connectionMade(self):
        print "spawned"
        self.shift(0)
        self.transport.write('IN %d\n' % BELL)
        self.transport.write('IN %d\n' % SWITCH)
        self.transport.write('WATCH %d\n' % IN1)
        self.transport.write('WATCH %d\n' % IN2)

        self.blink_task = task.LoopingCall(self.blink_keep_alive)
        self.blink_task.start(3, now=False)

        self.clear_bell_task = task.LoopingCall(self.clear_bell)
        self.clear_bell_task.start(5, now=False)

    def outReceived(self, data):
        print data
        for line in data.splitlines():
            if 'S' in line:
                _, pin, state = line.split()
                if int(pin) == SWITCH:
                    self.base_open = state == '1'
                    self.irc_factory.base_open = self.base_open
                    self.base_update()

            if 'IN2' in data:
                self.base_open = not self.base_open
                self.irc_factory.base_open = self.base_open
                self.base_update()

            if 'IN1' in data:
                # we receive *EVERY* state change
                # so for one bell ring we count to 2
                self.bell_count += 1
                self.bell_update()

    def errReceived(self, data):
        pass
        #print "errReceived! with %d bytes!" % len(data)
        #print data

    def inConnectionLost(self):
        print "inConnectionLost! stdin is closed! (we probably did it)"

    def outConnectionLost(self):
        print "outConnectionLost! The child closed their stdout!"
        print "out:", self.data

    def errConnectionLost(self):
        print "errConnectionLost! The child closed their stderr."

    def processExited(self, reason):
        print "processExited, status %d" % (reason.value.exitCode,)

    def processEnded(self, reason):
        print "processEnded, status %d" % (reason.value.exitCode,)
        print "quitting"
        reactor.stop()


if __name__ == '__main__':
    log.startLogging(sys.stdout)
    f = BlBotFactory()

    gpio_setup()

    if cfg.SSL:
        reactor.connectSSL(cfg.SERVER, cfg.PORT, f, ssl.ClientContextFactory())
    else:
        reactor.connectTCP(cfg.SERVER, cfg.PORT, f)

    if cfg.SPACEAPI_ENABLED:
        reactor.listenTCP(cfg.SPACEAPI_PORT, server.Site(BlBotWebResource(f)))

    if has_gpio:
        pp = GPIOProto(f)
        reactor.spawnProcess(pp, "wrap_wrap_gpio", ["wrap_wrap_gpio"], {})
    reactor.run()
