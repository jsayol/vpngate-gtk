import asynchat
import asyncore
import socket
import sys


class AsyncManagerHandler(asynchat.async_chat):
    def __init__(self, connection, addr, port, onopen=None, onclose=None, stateparser=None):
        super(AsyncManagerHandler, self).__init__()
        self.connection = connection
        self.port = port
        self.buffer = []
        self.onopen = onopen
        self.onclose = onclose
        self.stateparser = stateparser

        print('AsyncManagerHandler connecting to '+addr+':'+str(port)+' ...')
        self.set_terminator(b'\n')
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect((addr, port))


    def set_open_callback(self, fn):
        self.onopen = fn


    def set_close_callback(self, fn):
        self.onclose = fn


    def handle_error(self):
        super(AsyncManagerHandler, self).handle_error()


    def handle_expt(self):
        self.close()


    def handle_connect(self):
        super(AsyncManagerHandler, self).handle_connect()
        if hasattr(self.onopen, "__call__"):
            self.onopen()


    def handle_close(self):
        super(AsyncManagerHandler, self).handle_close()
        if hasattr(self.onclose, "__call__"):
            self.onclose()


    def collect_incoming_data(self, data):
        self.buffer.append(data.decode('utf-8'))


    def found_terminator(self):
        msg = ''.join(self.buffer)
        if msg.startswith(">PASSWORD:Need 'Auth'"):
            print('Auth needed!')
            # self.send('username "Auth" {0}\n'.format(username))
            # self.send('password "Auth" "{0}"\n'.format(escapePassword(password)))
        elif msg.startswith('>HOLD:Waiting for hold release'):
            self.send(b'log on all\n') # enable logging
            self.send(b'state on all\n') # enable state reporting
            self.send(b'hold release\n') # continue start procedure
        elif msg.startswith('>LOG:'):
            pass
        elif msg.startswith('>STATE:'):
            if hasattr(self.stateparser, "__call__"):
                self.stateparser(msg[7:])

        self.buffer = []


    def __exit__(self, *err):
        del self.connection
