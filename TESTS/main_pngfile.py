import subprocess

outfile = open("test.png", "wb")

proc = subprocess.Popen("adb shell screencap -p | sed \'s/\r$//\'", stdout = subprocess.PIPE, stderr = subprocess.STDOUT, shell=True)

for line in proc.stdout:
    outfile.write(line)

outfile.close()
