'''
Quick and dirty android remote control through ADB

Pretty slow (4-5FPSs), but works.
Text writing works ok.
NOTE: screen can be turned off, see latests app on phone

USAGE:
    -left-click on screen for touch event
    -right-click, drag and let go for swipe
    -type for inputting text to the current field
    -CTRL+V for pasting text :)

TODO:
    -cannot write "?"
    -make faster (although VNC apps were not faster): one idea is to move the image getting in another thread
    and another is to use the bbq app on the phone, but I think it has some bugs and it uses TCP packets that need
    to be reversed-engineered
    -another idea is to replace the screencap binary with a faster one, but not sure if it is possible
'''
import subprocess
import io
from PIL import Image, ImageTk
import tkinter as tk
import queue
import threading
import time
import random

class LiveAndroidFeed():
    def __init__(self, parent):
        self.parent = parent
        self.buf = io.BytesIO()
        self.wordToSend = []
        self.swipeInfo = [-1, -1, -1, -1]
        self.imgCounter = 0
        self.refreshTime = 1 #ms
        self._job = None

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
        self.initSleepControls()

        #Periodically flush the text to the screen
        self.PER_flushWordToSend()

        #Worker for ADB sends
        self.queue = queue.Queue()
        ADBWorker(self.queue).start()

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
        self.parent.bind("<BackSpace>", self.cbBackspacePress)
        self.parent.bind("<space>", self.cbSpacePress)
        self.parent.bind("<Return>", self.cbReturnPress)
        self.parent.bind("<Control-v>", self.cbPaste)

    def initSleepControls(self):
        self.parent.bind("<FocusIn>", self.cbInFocus)
        self.parent.bind("<FocusOut>", self.cbOutFocus)


    '''
    -----------------------SCREEN PROCESSING
    '''
    def imgGetFromDevice(self):
        proc = subprocess.Popen("adb shell screencap -p | sed \'s/\r$//\'", stdout = subprocess.PIPE, stderr = subprocess.STDOUT, shell=True)

        self.buf.seek(0)
        for line in proc.stdout:
            self.buf.write(line)
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
    '''
    def cbInFocus(self, event):
        self.dbg("in focus")
        self.refreshTime = 1    #ms
        self.parent.after_cancel(self._job)
        self.imgUpdateCanvas()

    def cbOutFocus(self, event):
        self.dbg("LOST FOCUS")
        self.refreshTime = 60000 #ms = 30s

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
        self.dbg("Key pressed", event.char)

        #Update internal word counter, will be sent on enter or space
        self.wordToSend.append(event.char)

    def cbBackspacePress(self, event):
        self.dbg("backspace")
        self.backspaceWordToSend()
        self.adbSendKeyEvent(67)

    def cbSpacePress(self, event):
        self.dbg("space")
        self.flushWordToSend()          #Send what is left
        self.adbSendKeyEvent(62)        #Send space

    def cbReturnPress(self, event):
        self.dbg("enter")
        self.flushWordToSend()          #Send what is left
        self.adbSendKeyEvent(66)        #Send enter

    def cbPaste(self, event):
        txt = self.parent.clipboard_get()
        for elem in txt:
            self.wordToSend.append(elem)
        self.dbg("added text: " + txt)
        self.flushWordToSend()

    '''
    -----------------------UI STUFF
    '''
    def flushWordToSend(self):
        if len(self.wordToSend) == 0:
            return

        self.dbg("Sending:", self.wordToSend)
        exceptions = {")":163, "(":162, "*":155 }
        tmp = ""
        for elem in self.wordToSend:

            add = True
            for ex in exceptions:
                if elem == ex:
                    self.adbSendText("".join(tmp))
                    tmp=""
                    self.adbSendKeyEvent(exceptions[elem])
                    add = False

            if elem == '':
                add = False

            if elem == '?':
                self.adbSendText("".join(tmp))
                tmp=""
                add = False
                print("SPECIAL ?")
                self.queue.put("adb shell input text \"\\\\\\?\"")

            if add is True:
                tmp += elem

        #send what is left
        self.adbSendText("".join(tmp))

        self.wordToSend = [] #prepare for next one

    def backspaceWordToSend(self):
        if len(self.wordToSend) == 0:
            return

        self.wordToSend.pop()

    def PER_flushWordToSend(self):
        self.flushWordToSend()
        self.parent.after(500, self.PER_flushWordToSend)
    '''
    -----------------------ADB CALLS
    '''
    def adbSendText(self, text):
        if len(text) == 0:
            return
        self.queue.put("adb shell input text " + text)

    def adbSendKeyEvent(self, keyNo):
        self.queue.put("adb shell input keyevent " + str(keyNo))

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
