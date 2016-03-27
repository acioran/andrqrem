import subprocess
import io
from PIL import Image, ImageTk
import tkinter



def getImage(event = None):
    proc = subprocess.Popen("adb shell screencap -p | sed \'s/\r$//\'", stdout = subprocess.PIPE, stderr = subprocess.STDOUT, shell=True)

    buf = io.BytesIO()
    for line in proc.stdout:
        buf.write(line)

    buf.seek(0)

    img = Image.open(buf)
    return img

root = tkinter.Tk()
testImg = getImage()
xsize, ysize = testImg.size

canvas = tkinter.Canvas(root, width=xsize, height=ysize)
canvas.pack()

tkimg = ImageTk.PhotoImage(testImg)
imagesprite = canvas.create_image(xsize/2, ysize/2, image=tkimg)


root.mainloop()
