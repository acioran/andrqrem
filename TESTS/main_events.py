import subprocess
import io
from PIL import Image, ImageTk
import tkinter as tk

class LiveAndroidFeed():
    def __init__(self, parent):
        self.parent = parent
        self.buf = io.BytesIO()

        testImg = self.getImage()
        xsize, ysize = testImg.size

        self.canvas = tk.Canvas(self.parent, width=xsize, height=ysize)
        self.canvas.grid(row=0, column=0)

        tkimg = ImageTk.PhotoImage(testImg)
        self.tmp_image = tkimg #KEEP REFERENCE TO IMAGE!! OTHERWISE IT DOESN"T SHOW!
        self.image_on_canvas = self.canvas.create_image(xsize/2, ysize/2, image=tkimg)

        self.parent.bind("<Button-1>", self.touchCallback)
        self.parent.bind("<B1-Motion>", self.swipeCallback)
        self.parent.bind("<Key>", self.keypressCallback)
        self.parent.bind("<BackSpace>", self.backspaceCallback)
        self.parent.bind("<space>", self.spaceCallback)
        self.parent.bind("<Return>", self.enterCallback)

        self.updateImg()

    def getImage(self):
        proc = subprocess.Popen("adb shell screencap -p | sed \'s/\r$//\'", stdout = subprocess.PIPE, stderr = subprocess.STDOUT, shell=True)

        self.buf.seek(0)
        for line in proc.stdout:
            self.buf.write(line)
        self.buf.seek(0)

        img = Image.open(self.buf)
        return img

    def updateImg(self):
        print("called")
        testImg = self.getImage()
        tkimg = ImageTk.PhotoImage(testImg)
        self.tmp_image = tkimg #KEEP REFERENCE TO IMAGE!! OTHERWISE IT DOESN"T SHOW!

        self.canvas.itemconfig(self.image_on_canvas, image=tkimg)
        self.parent.after(1, self.updateImg)

    def touchCallback(self, event):
        print("Touched at", event.x, event.y)
        proc = subprocess.Popen("adb shell input tap " + str(event.x) + " " + str(event.y), shell=True)

    def swipeCallback(self, event):
        print("Swipe at", event.x, event.y)
        #TODO!

    def keypressCallback(self, event):
        print("Key pressed", event.char)
        proc = subprocess.Popen("adb shell input text " + event.char, shell=True)

    def backspaceCallback(self, event):
        print("backspace")
        proc = subprocess.Popen("adb shell input keyevent 67", shell=True)

    def spaceCallback(self, event):
        print("space")
        proc = subprocess.Popen("adb shell input keyevent 62", shell=True)

    def enterCallback(self, event):
        print("enter")
        proc = subprocess.Popen("adb shell input keyevent 66", shell=True)

root = tk.Tk()
laf = LiveAndroidFeed(root)
root.mainloop()
