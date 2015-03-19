# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-

import codecs
import csv
import math
import sys
import threading
import time
import urllib.error
import urllib.request
from base64 import b64decode
from collections import deque
from itertools import islice
from locale import gettext as _

from gi.repository import GObject, Gtk

from vpngate_gtk.AboutVpngateGtkDialog import AboutVpngateGtkDialog
from vpngate_gtk.PreferencesVpngateGtkDialog import PreferencesVpngateGtkDialog
from vpngate_gtk_lib import Window

import ovpnclient

# logger = logging.getLogger('vpngate_gtk')

COL_HOSTNAME = 0
COL_IP = 1
COL_COUNTRY = 2
COL_UPTIME = 3
COL_SESSIONS = 4
COL_SPEED = 5
COL_PING = 6
COL_UPTIME_TEXT = 7
COL_SESSIONS_TEXT = 8
COL_SPEED_TEXT = 9
COL_PING_TEXT = 10
COL_OPENVPN_DATA = 11

URL_VPNGATE_LIST = "http://www.vpngate.net/api/iphone/"


def skip_last_n(iterator, n=1):
    it = iter(iterator)
    prev = deque(islice(it, n), n)
    for item in it:
        yield prev.popleft()
        prev.append(item)


def miliseconds_to_human(num):
    x = num / 1000
    seconds = math.floor(x % 60)
    x /= 60
    minutes = math.floor(x % 60)
    x /= 60
    hours = math.floor(x % 24)
    x /= 24
    days = math.floor(x)

    if days:
        ret = str(days) + ' day' + ('s' if days > 1 else '')
    elif hours:
        ret = str(hours) + ' hour' + ('s' if hours > 1 else '')
    elif minutes:
        ret = str(minutes) + ' minute' + ('s' if minutes > 1 else '')
    else:
        ret = str(seconds) + ' second' + ('s' if seconds > 1 else '')

    return ret


class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self, *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self.__stop = False

    def stop(self):
        self.__stop = True

    def stopped(self):
        return self.__stop


def get_vpngate_list(callback):
    thread = threading.currentThread()
    list = []
    try:
        response = urllib.request.urlopen(URL_VPNGATE_LIST)

        # stop if we've been told to do so
        if thread.stopped():
            response.close()
            return

        reader = codecs.getreader("utf-8")(response)
        reader.readline()
        csvlist = csv.DictReader(skip_last_n(reader, 1))
        for row in csvlist:
            # stop if we've been told to do so
            if thread.stopped():
                response.close()
                return

            try:
                uptime = int(row['Uptime'])
                uptime_text = miliseconds_to_human(uptime)
            except ValueError:
                uptime = None
                uptime_text = 'n/a'
            try:
                numsessions = int(row['NumVpnSessions'])
                numsessions_text = row['NumVpnSessions'] + ' sessions'
            except ValueError:
                numsessions = None
                numsessions_text = 'n/a'
            try:
                speed = int(row['Speed'])
                speed_text = str(round(speed / 1000000, 2)) + ' Mbps'
            except ValueError:
                speed = Nonestore = Gtk.ListStore(str, str, float)
                speed_text = 'n/a'
            try:
                ping = int(row['Ping'])
                ping_text = row['Ping'] + ' ms'
            except ValueError:
                ping = None
                ping_text = 'n/a'

            list.append([
                row['#HostName'] + '.opengw.net',
                row['IP'],
                row['CountryLong'],
                uptime,
                numsessions,
                speed,
                ping,
                uptime_text,
                numsessions_text,
                speed_text,
                ping_text,
                row['OpenVPN_ConfigData_Base64'],
            ])

        reader.close()
        response.close()

        # stop if we've been told to do so
        if thread.stopped():
            return

        GObject.idle_add(callback, list)

    except urllib.error.URLError:
        print("Couldn't get the VPN servers list.")


# See vpngate_gtk_lib.Window.py for more details about how this class works
class VpngateGtkWindow(Window):
    __gtype_name__ = "VpngateGtkWindow"


    def finish_initializing(self, builder):
        """Set up the main window"""
        super(VpngateGtkWindow, self).finish_initializing(builder)

        self.toolbar = self.builder.get_object("toolbar")
        context = self.toolbar.get_style_context()
        context.add_class(Gtk.STYLE_CLASS_PRIMARY_TOOLBAR)

        self.AboutDialog = AboutVpngateGtkDialog
        self.PreferencesDialog = PreferencesVpngateGtkDialog

        self.updatelistbutton = self.builder.get_object("updatelistbutton")
        self.connectbutton = self.builder.get_object("connectbutton")
        self.disconnectbutton = self.builder.get_object("disconnectbutton")
        self.statusbar = self.builder.get_object("statusbar")
        self.statusbarcontext = self.statusbar.get_context_id("status bar")
        self.updatelistdialog = self.builder.get_object("updatelistdialog")

        self.vpntreeview = self.builder.get_object("vpntreeview")
        self.vpnliststore = self.vpntreeview.get_model()

        self.on_updatelistbutton_clicked(self.updatelistbutton)

        self.disconnectbutton.set_sensitive(True)

        self.connection = ovpnclient.Connection(closecb=self.openvpn_disconnect_callback)


    def set_statusbar(self, text):
        self.statusbar.remove_all(self.statusbarcontext)
        self.statusbar.push(self.statusbarcontext, text)


    def on_updatelistbutton_clicked(self, widget):
        widget.set_sensitive(False)

        self.updatelistdialog.show()

        self.set_statusbar(_("Loading VPN servers list..."))

        self.updatelistthread = StoppableThread(
            target=get_vpngate_list,
            args=(self.populate_vpngate_list,),
            daemon=True
        )
        self.updatelistthread.start()


    def on_cancelupdatelistbutton_clicked(self, widget):
        if self.updatelistthread.is_alive():
            self.updatelistthread.stop()

        self.set_statusbar(_("Loading VPN servers list cancelled"))
        self.updatelistdialog.hide()


    def populate_vpngate_list(self, list):
        vpnliststore = self.vpntreeview.get_model()
        vpnliststore.clear()
        [vpnliststore.append(row) for row in list]
        self.updatelistbutton.set_sensitive(True)
        self.updatelistdialog.hide()
        self.set_statusbar(
            _("VPN servers list updated on ") +
            time.strftime("%a, %d %b %Y %H:%M:%S", time.gmtime())
        )


    def on_connectbutton_clicked(self, widget):
        selection = self.vpntreeview.get_selection()
        model, treeiter = selection.get_selected()
        if (treeiter is not None):
            self.openvpn_connect(model[treeiter][COL_OPENVPN_DATA])


    def on_disconnectbutton_clicked(self, widget):
        if self.connection is not None:
            self.connection.close()


    def on_vpntreeviewselection_changed(self, selection):
        model, treeiter = selection.get_selected()
        self.connectbutton.set_sensitive(treeiter is not None)


    def on_vpntreeview_row_activated(self, treeview, treepath, treeviewcolumn):
        model = treeview.get_model()
        self.openvpn_connect(model[treepath][COL_OPENVPN_DATA])


    def openvpn_connect_callback(self):
        GObject.idle_add(self.on_openvpn_connected)


    def on_openvpn_connected(self):
        print('on_openvpn_connected')


    def openvpn_disconnect_callback(self):
        GObject.idle_add(self.on_openvpn_disconnected)


    def on_openvpn_disconnected(self):
        print('on_openvpn_disconnected')


    def openvpn_connect(self, config):
        self.connection.set_config(b64decode(config))
        self.connection.open()
