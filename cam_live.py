#!/usr/bin/python3
"""
Copyright [2022] [roberto64 (mju7ki89@outlook.com)]

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""


import sys
import os
import signal
import socket
import threading
import time
import picamera
import picamera.array
import numpy as np
import gpiozero
import astral
import datetime
import io
import json
from ftplib import FTP

work = True

def flush_print(str):
    print(str)
    sys.stdout.flush()

class DayNight:
    def __init__(self, rpimotion):
        self.rpimotion = rpimotion
        self.is_day = False
        a = astral.Astral()
        self.city = a['Warsaw']
    
    def day(self):
        now = datetime.datetime.now()
        return now > self.city.sunrise().replace(tzinfo=None) and now < self.city.sunset().replace(tzinfo=None)
   
    def init(self):
        if self.day():
            self.is_day = True
            self.rpimotion.camera.exposure_mode = 'auto'
            if self.rpimotion.ircat:
                self.rpimotion.ir_cam.on()
                if self.rpimotion.ma:
                    self.rpimotion.ir_led.off()
        else:
            self.is_day = False
            self.rpimotion.camera.exposure_mode = 'night'
            if self.rpimotion.ircat:
                self.rpimotion.ir_cam.off()
                if self.rpimotion.ma:
                    self.rpimotion.ir_led.on()

    def processing(self):
        if self.day():
            if not self.is_day:
                self.is_day = True
                self.rpimotion.camera.exposure_mode = 'auto'
                if self.rpimotion.ircat:
                    self.rpimotion.ir_cam.on()
                    if self.rpimotion.ma:
                        self.rpimotion.ir_led.off()
        elif self.is_day:
            self.is_day = False
            self.rpimotion.camera.exposure_mode = 'night'
            if self.rpimotion.ircat:
                self.rpimotion.ir_cam.off()
                if self.rpimotion.ma:
                    self.rpimotion.ir_led.on()

class DetectMotion(picamera.array.PiMotionAnalysis):
    def __init__(self, rpimotion):
        super(DetectMotion,self).__init__(rpimotion.camera)
        self.rpimotion = rpimotion
        self.detect_time = 0.0;
        self.capture_time = 0.0;
        self.recording = False
        self.init = False
 
    def timeout_detect(self):
        return (self.detect_time + 4.0 < time.clock_gettime(time.CLOCK_MONOTONIC))
    
    def timeout_capture(self):
        return (self.capture_time + 12.0 < time.clock_gettime(time.CLOCK_MONOTONIC))

    def analyze(self, a):
        if not self.init:
            self.init = True
            self.top = self.rows * self.rpimotion.top // 100
            self.bottom = self.rows * self.rpimotion.bottom // 100
            self.left = self.cols * self.rpimotion.left // 100
            self.right = self.cols * self.rpimotion.right // 100
            self.mask = np.zeros((self.rows, self.cols), dtype=bool)
            self.mask[self.top : self.bottom, self.left : self.right] = True
        a = a[self.mask]
        a = np.sqrt(np.square(a['x'].astype(np.float)) + np.square(a['y'].astype(np.float))).clip(0, 255).astype(np.uint8)
        sum = (a > self.rpimotion.threshold()).sum()
        if sum > self.rpimotion.sensitive and sum < len(a):
            self.rpimotion.emit_message('detect_motion', (sum, np.amax(a)))
            self.detect_time = time.clock_gettime(time.CLOCK_MONOTONIC)
            if not self.recording:
                self.recording = True
                self.capture_time = time.clock_gettime(time.CLOCK_MONOTONIC)
                self.rpimotion.emit_message('start_capture', None)
            elif self.timeout_capture():
                self.rpimotion.emit_message('stop_capture', None)
                self.capture_time = time.clock_gettime(time.CLOCK_MONOTONIC)
                self.rpimotion.emit_message('start_capture', None)
        if self.recording and self.timeout_detect():
                self.recording = False
                self.rpimotion.emit_message('stop_capture', None)

class Session(io.IOBase):
    def __init__(self, connection):
        self.sock = connection
    def write(self, buf):
        return self.sock.sendall(buf)


class RPImotion:
    def __init__(self):
        self.ma = False
        self.ftp = False
        self.motion_count = 0
        self.detect_time = 0
        self.ftp_dir = socket.gethostname()
        self.capture_path = '/home/pi/capm/'
        self.camera = picamera.PiCamera()
        self.camera.video_stabilization = True
        self.camera.annotate_background = True
        self.camera.annotate_text_size = 20
        self.camera.resolution = (1296, 972)
        self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
        self.daynight = DayNight(self)
        self.server_socket = socket.socket()
        self.server_socket.setblocking(1)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.live_active = False
        self.filename_queue_lock = threading.Lock()
        self.filename_queue = []
        self.message_queue_lock = threading.Lock()
        self.message_queue = []
    
    def start(self):
        if self.ircat:
            self.ir_led = gpiozero.LED(26)
            self.ir_cam = gpiozero.LED(19)
        
        self.daynight.init()

        if self.ma:
            self.camera.start_recording('/dev/null', format='h264',  motion_output=DetectMotion(self), splitter_port = 1, inline_headers = True, sps_timing = True)
        if self.ftp:
            self.ftp_thread = threading.Thread(target=self.sending_by_ftp)
            self.ftp_thread.start()
        
        self.server_socket.bind(('0.0.0.0', 8000))
        self.server_socket.listen(0)
        self.accepting_thread = threading.Thread(target = self.accepting)
        self.accepting_thread.start()

    def parse_config(self, config):
        options = json.load(config)
        self.ircat = options['camera']['ircat']
        self.bitrate = options['camera']['bitrate']
        self.camera.framerate = options['camera']['framerate']
        self.camera.hflip = options['camera']['hflip']
        self.camera.vflip = options['camera']['vflip']
        self.ma = options['motion']['analyze']
        self.daythreshold = options['motion']['daythreshold']
        self.nightthreshold = options['motion']['nightthreshold']
        self.sensitive = options['motion']['sensitive']
        self.top = options['motion']['top']
        self.bottom = options['motion']['bottom']
        self.left = options['motion']['left']
        self.right = options['motion']['right']
        self.ftp = options['ftp']['active']
        self.ftp_address = options['ftp']['address']
        self.ftp_user = options['ftp']['user']
        self.ftp_pass = options['ftp']['pass']

    def emit_message(self, call, param):
        with self.message_queue_lock:
            if len(self.message_queue) < 10:
                self.message_queue.append((call, param))
    
    def threshold(self):
        if self.daynight.is_day:
            return self.daythreshold
        else:
            return self.nightthreshold

    def main_loop(self):
        global work
        ut = time.clock_gettime(time.CLOCK_MONOTONIC)
        while work:
            if ut + 0.9 < time.clock_gettime(time.CLOCK_MONOTONIC):
                ut = time.clock_gettime(time.CLOCK_MONOTONIC)
                self.update_annotate_text()
                self.daynight.processing()
            while len(self.message_queue) > 0:
                m = ('', None)
                with self.message_queue_lock:
                    m = self.message_queue[0]
                    del self.message_queue[0]
                if m[0] == 'detect_motion':
                    self.detect_motion(m[1])
                elif m[0] == 'start_capture':
                    self.start_capture()
                elif m[0] == 'stop_capture':
                    self.stop_capture()
                elif m[0] == 'start_live':
                    self.start_live(m[1])
                elif m[0] == 'stop_live':
                    self.stop_live()
            if self.live_active:
                self.wait_live()
            else:
                time.sleep(0.1);


    def update_annotate_text(self):
        self.camera.annotate_text = time.strftime('%d-%m-%Y %H:%M:%S') + ' : ' + str(self.motion_count) + ' : ' + time. strftime('%d-%m-%Y %H:%M:%S', time.localtime(self.detect_time)) + ']'

    def start_capture(self):
        try:
            self.filename = 'v' + time.strftime('%Y%m%d_%H%M%S-') + str(self.motion_count) + '.h264'
            flush_print('[' + self.filename + '] - start recording')
            fn = self.capture_path + self.filename
            self.camera.split_recording(fn, splitter_port = 1)
        except Exception as e:
            flush_print('Error start capture: ' + str(e))
    
    def stop_capture(self):
        try:
            self.camera.split_recording('/dev/null', splitter_port = 1)
            flush_print('[' + self.filename + '] - end recording')
            
            if self.ftp:
                with self.filename_queue_lock:
                    self.filename_queue.append(self.filename)
        except Exception as e:
            flush_print('Error stop capture: ' + str(e))

    def detect_motion(self, sum):
            self.motion_count += 1
            self.detect_time = time.time()
            flush_print('Detect motion [' + str(self.motion_count) + '],sum=' + str(sum[0]) + ',threshold=' + str(sum[1]))

    
    def start_live(self, soc):
        try:
            if self.ircat and not self.ma and not self.daynight.is_day:
                self.ir_led.on()
            flush_print('Start: sending live')
            self.live_active = True
            session = Session(soc)
            self.camera.start_recording(session, format='h264', bitrate = self.bitrate, splitter_port = 2)
        except Exception as e:
            if self.ircat and not self.ma:
                self.ir_led.off()
            flush_print('Error: sending live - ' + str(e))
            try:
                self.camera.stop_recording(splitter_port = 2)
            except:
                pass

    def wait_live(self):
        try:
            self.camera.wait_recording(0.1, splitter_port = 2)
        except Exception as e:
            if self.ircat and not self.ma:
                self.ir_led.off()
            flush_print('End: sending live - ' + str(e))
            try:
                self.camera.stop_recording(splitter_port = 2)
            except:
                pass
            self.live_active = False
    
    def stop_live(self):
        try:
            if self.ircat and not self.ma:
                self.ir_led.off()
            self.camera.stop_recording(splitter_port = 2)
            flush_print('End: sending live')
        except Exception as e:
            flush_print('End: sending live - ' + str(e))
        self.live_active = False
    
    def sending_by_ftp(self):
        global work
        while work:
            while work and len(self.filename_queue) > 0:
                try:
                    time.sleep(0.5)
                    filename = ''
                    with self.filename_queue_lock:
                        filename = self.filename_queue[0]
                    flush_print('start sending via ftp: ' + filename)
                    ftp = FTP(self.ftp_address)
                    ftp.login(user=self.ftp_user, passwd=self.ftp_pass)
                    ftp.cwd('/mnt/data/cams/' + self.ftp_dir)
                    f  = open(self.capture_path + filename,'rb')
                    ftp.storbinary('STOR ' + filename, f)
                    f.close()
                    ftp.quit()
                    with self.filename_queue_lock:
                        del self.filename_queue[0]
                    flush_print('stop sending via ftp: ' + filename)
                    os.remove(self.capture_path + filename)
                except Exception as e:
                    flush_print('Error: sending via ftp - ' + str(e))
            time.sleep(1.0)


    def accepting(self):
        global work
        while work:
            time.sleep(0.2)
            try:
                soc = None
                soc = self.server_socket.accept()[0]
                flush_print('accept session')
                if self.live_active:
                    self.emit_message('stop_live', None)
                self.emit_message('start_live', soc)
            except Exception as e:
                if soc is not None:
                    flush_print('Error: accepting - ' + str(e))
    
    def stop(self):
        if self.ma:
            try:
                self.camera.stop_recording(splitter_port = 1)
            except:
                pass
        self.server_socket.shutdown(socket.SHUT_RDWR)
        self.server_socket.close()
        self.accepting_thread.join()
        if self.ftp:
            self.ftp_thread.join()

def on_signal(sig,frame):
    global work
    work = False

def main():
    global work
    rpi_motion = None
    flush_print("cam_live.py START")
    np.set_printoptions(threshold=65000)
    try:
        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)
        
        rpi_motion = RPImotion()
        rpi_motion.parse_config(open(sys.argv[1]))
        rpi_motion.start()

        rpi_motion.main_loop()
        
        flush_print('cam_live.py ENDING...')
        rpi_motion.stop()

    except KeyError as e:
        work = False
        flush_print('Error config: ' + str(e))
    except Exception as e:
        work = False
        flush_print('Error:' + str(e))
        if rpi_motion != None:
            rpi_motion.stop()
    flush_print("cam_live.py STOP")

main()

