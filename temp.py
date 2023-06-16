#!/usr/bin/python3


import Adafruit_MCP9808.MCP9808 as MCP9808

def main():
    temp_sensor = MCP9808.MCP9808()
    temp_sensor.begin()
    print("{0:0.2F} C".format(temp_sensor.readTempC()))


main()
