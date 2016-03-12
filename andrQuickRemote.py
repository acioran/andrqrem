'''
Created on Mar 12, 2016

@author: Andrei Cioran
'''

'''
Quick and dirty android remote control through ADB

Pretty slow (4-5FPSs), but works.
Text writing works ok.
NOTE: screen can be turned off, see latests app on phone

VERSION 2.0 uses minicap on phone: much faster
VERSION 3.0 uses Remote keyboard and is much faster at writing

TODO:
    -clean-up and refactoring
    -autostart of services on phone and adb forward commands
    -sleep when out of focus (needs img display reimplementation)
    -faster swipes/touches

BUGS:
    -does not configure phone on start (start minicap, adb forward)
    -start might freeze
    -keyboard does not work on lockscreen (but mouse does)
    -ocasionally it freezes (not sure why, the image receive does not work)
    -no clean exit

USE:
    -install minicap on phone (see repository for howto)
    -install "Remote keyboard" app on phone from Play Store
    -run "adb shell LD_LIBRARY_PATH=/data/local/tmp/minicap-devel /data/local/tmp/minicap-devel/minicap -P 320x480@320x480/0"
    -run "adb forward tcp:1313 localabstract:minicap" for minicap
    -run "adb forward tcp:2323 tcp:2323" for keyboard
    -left-click on screen for touch event
    -right-click, drag and let go for swipe
    -type for inputting text to the current field
    -CTRL+V for pasting text :)
'''
import subprocess
import io
from PIL import Image, ImageTk
import tkinter as tk
import queue
import threading
import time
import random
import socket
import struct
import telnetlib

class LiveAndroidFeed():
    def __init__(self, parent):
        self.parent = parent
        self.buf = io.BytesIO()
        self.wordToSend = b""
        self.swipeInfo = [-1, -1, -1, -1]
        self.imgCounter = 0
        self.refreshTime = 1 #ms
        self._job = None
        self.LOCAL_IP = '127.0.0.1'
        self.IMG_PORT = 1313
        self.KBD_PORT = 2323

        self.sock = self.initMinicap(self.LOCAL_IP, self.IMG_PORT)
        self.keyboard = telnetlib.Telnet(self.LOCAL_IP, self.KBD_PORT)
        self.parseGlobalHeader()

        testImg = self.imgGetFromDevice()
        xsize, ysize = testImg.size

        self.canvas = tk.Canvas(self.parent, width=xsize, height=ysize)
        self.canvas.grid(row=0, column=0)

        tkimg = ImageTk.PhotoImage(testImg)
        self.tmp_image = tkimg #KEEP REFERENCE TO IMAGE!! OTHERWISE IT DOESN"T SHOW!
        self.image_on_canvas = self.canvas.create_image(xsize/2, ysize/2, image=tkimg)

        #Init everything
        self.initMouse()
        self.initKeys()
        #self.initSleepControls()

        #Worker for ADB sends
        self.queue = queue.Queue()
        ADBWorker(self.queue).start()

        #Displays the image and schedules the next refresh
        self.PER_kbdSendText()
        self.imgUpdateCanvas()

    def initMinicap(self, TCP_IP, TCP_PORT):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((TCP_IP, TCP_PORT))

        return sock

    def parseGlobalHeader(self):
        data = self.sock.recv(24)
        vers = struct.unpack_from("B", data, 0)[0]
        print("VERSION =", vers)

        header_size = struct.unpack_from("B", data, 1)[0]
        print("H SIZE =", header_size)

        proc_pid = struct.unpack_from("I", data, 2)[0]
        print("PID =", proc_pid)

        x_real = struct.unpack_from("I", data, 6)[0]
        y_real = struct.unpack_from("I", data, 10)[0]
        print("Real display size: ", x_real, "x", y_real)

        x_virt = struct.unpack_from("I", data, 14)[0]
        y_virt = struct.unpack_from("I", data, 18)[0]
        print("Real display size: ", x_virt, "x", y_virt)

        disp_or = struct.unpack_from("B", data, 22)[0]
        print("ORIENTATION =", disp_or)
        qirks = struct.unpack_from("B", data, 23)[0]
        print("qirks =", qirks)

    def initMouse(self):
        #Use b1 for touch events
        self.parent.bind("<Button-1>", self.cbTouch)

        #And use B2 for swipe events
        self.parent.bind("<Button-3>", self.cbSwipeStart)
        self.parent.bind("<ButtonRelease-3>", self.cbSwipeEnd)

    def initKeys(self):
        self.parent.bind("<Key>", self.cbKeyPress)
        self.parent.bind("<Return>", self.cbReturnPress)
        self.parent.bind("<Control-v>", self.cbPaste)

    def initSleepControls(self):
        self.parent.bind("<FocusIn>", self.cbInFocus)
        self.parent.bind("<FocusOut>", self.cbOutFocus)


    '''
    -----------------------SCREEN PROCESSING
    '''
    def imgGetFromDevice(self):
        data = self.sock.recv(4)
        frame_size = struct.unpack_from("I", data, 0)[0]

        self.buf.seek(0)
        len_read = 0
        while len_read < frame_size:
            print("SOCK RECV")
            data = self.sock.recv(8192)
            print("SOCK RECVed")
            len_read += len(data)

            self.buf.write(data)
        self.buf.seek(0)

        img = Image.open(self.buf)
        return img

    def imgUpdateCanvas(self):
        #Just a small stat
        self.dbg("called", self.imgCounter)
        self.imgCounter += 1

        #Only do this if the app has focus
        testImg = self.imgGetFromDevice()
        tkimg = ImageTk.PhotoImage(testImg)
        self.tmp_image = tkimg #KEEP REFERENCE TO IMAGE!! OTHERWISE IT DOESN"T SHOW!

        self.canvas.itemconfig(self.image_on_canvas, image=tkimg)
        self._job = self.parent.after(self.refreshTime, self.imgUpdateCanvas)
    '''
    -----------------------FOCUS CALLBACKS
    def cbInFocus(self, event):
        self.dbg("in focus")
        self.refreshTime = 1    #ms
        self.parent.after_cancel(self._job)
        self.imgUpdateCanvas()

    def cbOutFocus(self, event):
        self.dbg("LOST FOCUS")
        self.refreshTime = 60000 #ms = 30s
    '''

    '''
    -----------------------MOUSE CALLBACKS
    '''
    def cbTouch(self, event):
        self.dbg("Touched at", event.x, event.y)
        self.adbSendTouch(event.x, event.y)

    def cbSwipeStart(self, event):
        if self.swipeInfo[0] == -1:
            self.swipeInfo[0] = event.x
            self.swipeInfo[1] = event.y

    def cbSwipeEnd(self, event):
        if self.swipeInfo[0] != -1:
            self.dbg("Swipe ended at ", event.x, event.y)
            self.swipeInfo[2] = event.x
            self.swipeInfo[3] = event.y

            #Send event
            self.adbSendSwipe(list(self.swipeInfo))

            #cleanup
            self.swipeInfo = [-1, -1, -1, -1]

    '''
    -----------------------Keyboard CALLBACKS
    '''
    def cbKeyPress(self, event):
        self.dbg("Key pressed ", event.char)
        self.kbdSendText(event.char)

    #QUICK HACK: not sure why needed
    def cbReturnPress(self, event):
        self.dbg("enter")
        self.kbdSendText(event.char)
        self.kbdSendText(event.char)

    def cbPaste(self, event):
        txt = self.parent.clipboard_get()
        self.dbg("added text: " + txt)
        self.kbdSendText(txt)

    '''
    -----------------------Telnet calls to Remote Keyboard
    '''
    def kbdSendText(self, text):
        if len(text) == 0:
            return
        self.wordToSend += str.encode(text)

    #Use a periodic function to stop flooding the telnet when typing fast
    def PER_kbdSendText(self):
        self.parent.after(50, self.PER_kbdSendText)
        if len(self.wordToSend) == 0:
            return

        self.keyboard.write(self.wordToSend)
        self.wordToSend = b""

    '''
    -----------------------ADB CALLS TODO: replace with sendevent
    '''
    def adbSendTouch(self, x, y):
        self.queue.put("adb shell input tap " + str(x) + " " + str(y))

    def adbSendSwipe(self, swipeCoords):
        if(swipeCoords[0] == -1):
            return
        self.queue.put("adb shell input swipe " + str(swipeCoords[0]) + " " \
                                                + str(swipeCoords[1]) + " " \
                                                + str(swipeCoords[2]) + " " \
                                                + str(swipeCoords[3]))

    '''
    -----------------------DEBUG
    '''
    def dbg(self, *args):
        print(*args)


class ADBWorker(threading.Thread):
    def __init__(self, queue):
        self.__queue = queue
        threading.Thread.__init__(self)

    def run(self):
        while True:
            item = self.__queue.get()
            if item is None:
                break

            subprocess.call(item, shell=True)

            self.__queue.task_done()
root = tk.Tk()
laf = LiveAndroidFeed(root)
root.mainloop()
