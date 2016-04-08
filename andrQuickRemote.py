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
    -[DONE]clean-up and refactoring
    -[DONE, needs more testing]autostart of services on phone and adb forward commands
    -sleep when out of focus (needs img display reimplementation)
    -faster swipes/touches

BUGS:
    -[FIXED, in testing]does not configure phone on start (start minicap, adb forward)
    -[FIXED? not sure]start might freeze
    -long start time due to sleep in Minicap part....should find better solution!
    -keyboard does not work on lockscreen (but mouse does)
    -[FIXED? not sure]ocasionally it freezes (not sure why, the image receive does not work)
    -[FIXED] no clean exit

USE:
    -install minicap on phone (see repository for howto)
    -install "Remote keyboard" app on phone from Play Store
    -left-click on screen for touch event
    -right-click, drag and let go for swipe
    -type for inputting text to the current field
    -CTRL+V for pasting text :)

COMMANDS THAT ARE RUN BY THE APP ON STARTUP:
    -run "adb shell LD_LIBRARY_PATH=/data/local/tmp/minicap-devel /data/local/tmp/minicap-devel/minicap -P 320x480@320x480/0"
    -run "adb forward tcp:1313 localabstract:minicap" for minicap
    -run "adb forward tcp:2323 tcp:2323" for keyboard

COMMANDS THAT ARE RUN BY THE APP ON STOP:
    -run "adb forward --remove tcp:1313"
    -run "adb forward --remove tcp:2323"

'''
import select
import io
from PIL import Image, ImageTk
import tkinter as tk
import queue
import threading
import time
import random
import socket
import struct
import pexpect
import telnetlib
import subprocess

class LiveAndroidFeed():
    def __init__(self, parent, xsize=320, ysize=480):
        self.parent = parent

        self.time_refresh = 1 #ms

        self.tmp_swipeInfo = [-1, -1, -1, -1]

        self.counter_imgs = 0
        self.counter_emptyimgs = 0

        self.job_imgUpdateCanvas = None

        self.queue_adb = queue.Queue()
        self.queue_img = queue.Queue()
        self.queue_kbd = queue.Queue()

        self.MAX_EMPTYIMGS = 180
        self.IP_LOCAL = '127.0.0.1'
        self.PORT_KBD = 2323
        self.PORT_IMG = 1313

        self.w_adb = ADBWorker(self.queue_adb)
        self.w_img = MinicapWorker(self.queue_img, self.IP_LOCAL, self.PORT_IMG)
        self.w_kbd = KBDWorker(self.queue_kbd, self.IP_LOCAL, self.PORT_KBD)

        self.tk_canvas = tk.Canvas(self.parent, width=xsize, height=ysize)
        self.tk_canvas.grid(row=0, column=0)
        self.tk_img_on_canvas = self.tk_canvas.create_image(xsize/2, ysize/2, image=None)

        #Init everything
        self.initMouse()
        self.initKeys()
        self.parent.protocol("WM_DELETE_WINDOW", self.closeAll)

        #Workers for ADB sends and minicap
        self.w_adb.start()
        self.w_img.start()
        self.w_kbd.start()

        #Displays the image and schedules the next refresh
        self.imgUpdateCanvas()

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

    def closeAll(self):
        self.queue_adb.put(None)
        self.queue_kbd.put(None)
        self.w_img.closeMinicap()

        self.parent.destroy()


    '''
    -----------------------SCREEN PROCESSING
    '''
    def imgUpdateCanvas(self):
        #Just a small stat
        self.dbg("called", self.counter_imgs, self.counter_emptyimgs, "\r")
        self.counter_imgs += 1

        #Only do this if the app has focus
        bad = False
        try:
            testImg = self.queue_img.get(block=False)
        except queue.Empty:
            bad = True

        try:
            tkimg = ImageTk.PhotoImage(testImg)
        except:
            bad = True

        if bad is True:
            self.dbg("EMPTY IMAGE")
            self.counter_emptyimgs += 1
        else:
            self.counter_emptyimgs = 0

            self.tmp_image = tkimg #KEEP REFERENCE TO IMAGE!! OTHERWISE IT DOESN"T SHOW!

            self.tk_canvas.itemconfig(self.tk_img_on_canvas, image=tkimg)
            self.queue_img.task_done()
        
        #Reschedule the task
        self.job_imgUpdateCanvas = self.parent.after(self.time_refresh, self.imgUpdateCanvas)

    '''
    -----------------------MOUSE CALLBACKS
    '''
    def cbTouch(self, event):
        self.dbg("Touched at", event.x, event.y)
        self.adbSendTouch(event.x, event.y)

    def cbSwipeStart(self, event):
        if self.tmp_swipeInfo[0] == -1:
            self.tmp_swipeInfo[0] = event.x
            self.tmp_swipeInfo[1] = event.y

    def cbSwipeEnd(self, event):
        if self.tmp_swipeInfo[0] != -1:
            self.dbg("Swipe ended at ", event.x, event.y)
            self.tmp_swipeInfo[2] = event.x
            self.tmp_swipeInfo[3] = event.y

            #Send event
            self.adbSendSwipe(list(self.tmp_swipeInfo))

            #cleanup
            self.tmp_swipeInfo = [-1, -1, -1, -1]

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
    -----------------------Keyboard typing -> send to worker
    '''
    def kbdSendText(self, text):
        if len(text) == 0:
            return
        self.queue_kbd.put(text)

    '''
    -----------------------ADB CALLS TODO: replace with sendevent
    '''
    def adbSendTouch(self, x, y):
        self.queue_adb.put("input tap " + str(x) + " " + str(y))

    def adbSendSwipe(self, swipeCoords):
        if(swipeCoords[0] == -1):
            return
        self.queue_adb.put("input swipe " + str(swipeCoords[0]) + " " \
                                          + str(swipeCoords[1]) + " " \
                                          + str(swipeCoords[2]) + " " \
                                          + str(swipeCoords[3]))

    '''
    -----------------------DEBUG
    '''
    def dbg(self, *args):
        #print(*args)
        return


class MinicapWorker(threading.Thread):
    def __init__(self, queue, ip, port):
        self.port = port
        self.__queue = queue
        self.frame = io.BytesIO()
        self.keepRunning = True

        self.adb_minicap = pexpect.spawn("adb shell LD_LIBRARY_PATH=/data/local/tmp/minicap-devel /data/local/tmp/minicap-devel/minicap -P 320x480@320x480/0")
        time.sleep(5)
        subprocess.call("adb forward tcp:" + str(port) + " localabstract:minicap", shell=True)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(1)
        self.sock.connect((ip, port))

        self.parseGlobalHeader()
        threading.Thread.__init__(self)

    def closeMinicap(self):
        self.keepRunning = False

    def cleanUp(self):
        self.sock.shutdown(socket.SHUT_WR)
        self.sock.close()
        subprocess.call("adb forward --remove tcp:" + str(self.port), shell=True)
        self.adb_minicap.close()
        print("Minicap CLOSING!")

    def parseGlobalHeader(self):
        data = self.sockReceive(24)

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
        print("Virt display size: ", x_virt, "x", y_virt)

        disp_or = struct.unpack_from("B", data, 22)[0]
        print("ORIENTATION =", disp_or)
        qirks = struct.unpack_from("B", data, 23)[0]
        print("qirks =", qirks)

    def getImageFromDevice(self):
        data = self.sockReceive(4)
        frame_size = struct.unpack_from("I", data, 0)[0]

        self.frame.seek(0)
        len_read = 0
        while len_read < frame_size:
            data = self.sockReceive(1024)
            self.frame.write(data)
            if len(data) != 0:
                len_read += len(data)
            else:
                print("EMPTY READ", len_read)

        self.frame.seek(0)
        img = Image.open(self.frame)

        return img

    def sockReceive(self, length):
        data = b""
        try:
            data, address = self.sock.recvfrom(length, 1024)
        except socket.timeout:
            print("TIMEOUT OCCURED")

        return data

    def run(self):
        while self.keepRunning is True:
            image = self.getImageFromDevice()

            self.__queue.put(image)

        self.cleanUp()


class ADBWorker(threading.Thread):
    def __init__(self, queue):
        self.__queue = queue
        self.adb_shell = pexpect.spawn("adb shell")
        threading.Thread.__init__(self)

    def cleanUp(self):
        self.adb_shell.close()
        print("ADB CLOSING!")

    def run(self):
        while True:
            item = self.__queue.get()
            if item is None:
                break

            self.adb_shell.sendline(item)

            self.__queue.task_done()

        self.cleanUp()

class KBDWorker(threading.Thread):
    def __init__(self, queue, ip, port, sleep_time_ms=30):
        self.__queue = queue
        self.port = port

        print("Connecting to keyboard....")
        subprocess.call("adb forward tcp:" + str(port) + " tcp:" + str(port), shell=True)
        self.keyboard = telnetlib.Telnet(ip, port, 5)
        print("DONE!")
        self.time_wait = sleep_time_ms #in ms

        threading.Thread.__init__(self)

    def cleanUp(self):
        self.keyboard.close()
        subprocess.call("adb forward --remove tcp:" + str(self.port), shell=True)
        print("KDB CLOSING")

    def run(self):
        while True:
            wordToSend = b""

            try:
                item = self.__queue.get(block=False)
                if item is None:
                    break

                wordToSend += str.encode(item)
                self.keyboard.write(wordToSend)

                self.__queue.task_done()
            except queue.Empty:
                pass

            time.sleep(self.time_wait/1000)

        self.cleanUp()

root = tk.Tk()
laf = LiveAndroidFeed(root)
root.mainloop()
