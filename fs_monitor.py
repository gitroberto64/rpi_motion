#!/usr/bin/python3

import sys
import os
import signal
import time
import pathlib as lp

work = True


def flush_print(str):
    sys.stdout.write(str + '\n')
    sys.stdout.flush()

class FSMonitor:
    def __init__(self, path, percent, interval):
        self.path = lp.Path(path)
        self.percent = percent
        self.interval = interval
        self.fl = []

    def disk_stat(self):
        disk = os.statvfs(str(self.path))
        percent = (disk.f_blocks - disk.f_bfree) * 100 / (disk.f_blocks - disk.f_bfree + disk.f_bavail) + 1
        return percent

    def list_files(self, item):
        try:
            if item.is_dir():
                for item2 in item.iterdir():
                    self.list_files(item2)
            elif item.is_file():
                self.fl.append(item)
        except Exception as e:
            flush_print(str(e))

    def delete(self):
        for i in self.fl:
            i.unlink()


    def analyze(self):
        global work
        counter = 0
        while work:
            time.sleep(0.1)
            counter += 1
            if counter == self.interval * 10:
                counter = 0
                if self.disk_stat() > self.percent:
                    self.list_files(self.path)
                    self.fl.sort(reverse = True, key = lambda item: item.stat().st_mtime)
                    del self.fl[0 : len(self.fl) - int(len(self.fl) / 10)]
                    flush_print('Use: ' + str(self.disk_stat()) + '%')
                    flush_print('Delete: ' + str(len(self.fl)) + ' files')
                    self.delete()
                    flush_print('Use: ' + str(self.disk_stat()) + '%')
                    self.fl = []


def on_signal(sig, f):
    global work
    work = False


def main():
    flush_print('fs_monitor.py START')
    
    try:
        
        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)
        if len(sys.argv) == 4:
            fs_monitor = FSMonitor(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
            fs_monitor.analyze()
        else:
            flush_print("fs_monitor.py path percent(free) interval(sekonds)")

    except Exception as e:
        flush_print(str(e))
    
    flush_print('fs_monitor.py STOP')

main()
