# -*- coding: utf-8 -*-

import time
import threading

import serial

# Commands
# A2B : AIBOX to BT-01
# B2A : BT-01 to AIBOX
# format : <DLE><STX>[command1byte][parameter0～128byte][checksum1byte]<DLE><ETX>
# checksum : sum (lowest 8 bit) of command & parameter
# if 0x10 appears in command & parameter, add 0x10 just after 0x10 as escape of <DLE>
DLE = bytearray([0x10])
STX = bytearray([0x02])
ETX = bytearray([0x03])

# HEART BEAT timer (default : 5 min. period)
HB_TIME_PERIOD = 300        # should be 300


# デコレーター for DEBUG
def print_more(func):
    def wrapper(*args, **kwargs):
        print('func:', func.__name__)
        print('args:', args)
        print('kwargs:', kwargs)
        result = func(*args, **kwargs)
        print('result:', result)
        return result
    return wrapper


# デコレーター for DEBUG
def print_info(func):
    def wrapper(*args, **kwargs):
        print('start---')
        result = func(*args, **kwargs)
        print('---end')
        return result
    return wrapper



#
# AI BOX Serial Communication Class to BT-01
#
class BtComm(object):
    def __init__(self, tty, baudrate, timeoutvalue=0.1):
        # port open flag
        self.isPortOpen = False
        # Rx
        self.recvData = bytearray()
        self.recvCommand = bytearray()
        self.recvChecksumByte = bytearray()
        self.afterEscapeSequence = bytearray()
        # Generate event
        self.event = threading.Event()

        # Open Serial Port. wait til success
        while True:
            try:
                self.comm = serial.Serial(tty, baudrate, timeout=timeoutvalue)
                self.isPortOpen = True
                break
            except serial.SerialException:
                self.isPortOpen = False

        return

    # Receiving Data with time out setting[sec]
    def recv(self, timeout=300):
        # for time out
        time_start = time.time()
        # Clear event to wait thread
        self.event.clear()
        # Clear Rx Buffer
        self.recvData.clear()
        # Rx result : True (success) False (fault: time out)
        rx_result = False

        # Wait for Rx
        while not self.event.is_set():
            # Check time out
            time_end = time.time()
            if time_end - time_start > timeout:
                # Time out process
                rx_result = False
                self.stop()

                # for DEBUG
                print("Rx timeout:{0}sec".format(timeout))
                break

            # Received !  read Rx
            buff = self.comm.read()

            # Check Rx data 
            if len(buff) > 0:
                # Read Rx
                self.recvData.extend(buff)
                # <DLE(0x10)><ETX(0x03) Received ? 
                if (self.recvData.find(b'\x10\x03')) >= 0:
                    # Stop receiving data (success)
                    rx_result = True
                    self.stop()
                    break

        # Return Result
        if rx_result:
            # DEBUG
            # print('self.recvData = ', self.recvData)

            #
            # here, process checksum, 0x10 escape process, & discriminating the command
            #
            # received command
            self.recvCommand = self.recvData[2]
            # extract data for checksum
            recvdataforchecksum = self.recvData[2:-3]
            # extract payload for 0x10 escape sequence
            recvdataforescapesequence = self.recvData[3:-3]
            # received data checksum
            self.recvChecksumByte = self.recvData[-3]
            # check checksum
            num_sum = 0
            for num in recvdataforchecksum:
                num_sum += num
            checksumbyte = num_sum & 0xFF
            if checksumbyte == self.recvChecksumByte:
                rx_checksum = True
            else:
                rx_checksum = False
            # send CMD_UNKNOWN_RES
            # not need now

            # retrieve 0x10 from escape sequence
            self.afterEscapeSequence = bytearray()
            pnum = 0  # non 0x10
            for num in recvdataforescapesequence:
                if pnum == 16 & num == 16:
                    pnum = 0
                    continue
                else:
                    pnum = num
                    self.afterEscapeSequence.append(num)
            # print("afterEscapeSequence = ", afterEscapeSequence)

        return rx_result, self.recvData

    # Send Data
    def send(self, data):
        # check 0x10 escape
        sendbytearray = bytearray()
        sendbytearray.clear()
        for i in data:
            sendbytearray.append(i)
            if i == 0x10:  # 0x10 escape required ?
                sendbytearray.append(i)  # yes

        # Add DLE+STX, checkSum, DLE+ETX
        #  calculate check sum
        num_sum = 0
        for i in sendbytearray:
            num_sum = num_sum + i
        sumbyte = num_sum & 0xFF  # extract only lowest byte
        csum = bytearray([sumbyte])
        #  make a command
        senddata = DLE + STX + sendbytearray + csum + DLE + ETX

        # print("debug: senddata = " + str(senddata))

        try:
            self.comm.write(senddata)
            self.isPortOpen = True
            # DEBUG
            # print('senddata = ', senddata)

        except serial.SerialException:
            self.isPortOpen = False
            # logging.error("Can't send data through serial port.")
            # print("senddata fault")

        return self.isPortOpen, senddata

    # Stop Serial Comm
    def stop(self):
        self.event.set()

    # Close Serial Port
    def close(self):
        self.stop()
        if self.isPortOpen:
            self.comm.close()
        self.isPortOpen = False