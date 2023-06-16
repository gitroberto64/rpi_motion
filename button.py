
#!/usr/bin/python3

import os
from gpiozero import Button

button = Button(26)
button.wait_for_press()
os.system('halt')
