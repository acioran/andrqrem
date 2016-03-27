import pexpect

proc = pexpect.spawn('adb shell')
while True:
    input("press")
    proc.sendline('input text test')
