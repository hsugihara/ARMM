# -*- coding: utf-8 -*-

import time
import threading
import sys

import serial

# Commands
# A2B : AIBOX to BT-01/11
# B2A : BT-01 to AIBOX
# format : <DLE><STX>[command1byte][parameter0～128byte][checksum1byte]<DLE><ETX>
# checksum : sum (lowest 8 bit) of command & parameter
# if 0x10 appears in command & parameter, add 0x10 just after 0x10 as escape of <DLE>
DLE = bytearray([0x10])
STX = bytearray([0x02])
ETX = bytearray([0x03])

# HEART BEAT timer (default : 5 min. period)
HB_TIME_PERIOD = 300  # should be 300


#
# AI BOX Serial Communication Class to BT-01/11
#
class BtComm(object):
    def __init__(self, tty, baudratevalue=1200, timeoutvalue=30.0):
        # port open flag
        self.isPortOpen = False
        # Rx
        self.recvData = bytearray()
        self.recvCommand = bytearray()
        self.recvChecksumByte = bytearray()
        self.afterEscapeSequence = bytearray()
        self.recvdataforescapesequence = bytearray()
        # Tx
        self.sendbytesnoescape = bytearray()
        self.sendbytesescape = bytearray()
        # Generate event
        self.event = threading.Event()

        # Open Serial Port. wait til success
        self.trycount = 0
        while True:
            print("try to open serial port 10 times.")
            try:
                self.trycount += 1
                self.comm = serial.Serial(
                    port=tty,
                    baudrate=baudratevalue,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=timeoutvalue
                    )
                self.isPortOpen = True              # opened successfully
                print("Serial port opened successfully.")
                break
            except serial.SerialException:
                self.isPortOpen = False             # failed
                print("failed to open serial port.  Retry.")
                if self.trycount == 10 :
                    print("Can't open serial port. Please reboot system.")
                    sys.exit()
                

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
            print('self.recvData = ', self.recvData)
            print('self.recvData = ', self.recvData.hex())

            #
            # here, process checksum, 0x10 escape process, & discriminating the command
            #
            # received command
            self.recvCommand = self.recvData[2]
            # extract data for checksum
            # recvdataforchecksum = self.recvData[2:-3]
            # extract payload for 0x10 escape sequence
            self.recvdataforescapesequence = self.recvData[2:-3]
            # received data checksum
            self.recvChecksumByte = self.recvData[-3]
            # extract escape sequence 0x10
            self.afterEscapeSequence = bytearray()
            self.afterEscapeSequence.clear()
            pnum = 0  # non 0x10
            for num in self.recvdataforescapesequence:
                if pnum == 0x10 & num == 0x10:
                    pnum = 0
                    continue
                else:
                    pnum = num
                    self.afterEscapeSequence.append(num)

            print("self.afterEscapeSequence = ", self.afterEscapeSequence)

            # check checksum
            num_sum = 0
            for num in self.afterEscapeSequence:
                num_sum += num
            checksumbyte = num_sum & 0xFF

            print("checksumbyte = ", hex(checksumbyte))
            print("self.recvChecksumByte = ", hex(self.recvChecksumByte))

            if checksumbyte == self.recvChecksumByte:
                print("received data check sum is correct")
            else:
                print("received data check sum is not correct")
            # send CMD_UNKNOWN_RES
            # but not need now

        return rx_result, self.recvData

    # Send Data
    def send(self, data):
        # check sum
        self.sendbytesnoescape.clear()
        num_sum = 0
        for i in data:
            num_sum = num_sum + i
            self.sendbytesnoescape.append(i)
        csum = num_sum & 0xFF       # extract only lowest byte
        self.sendbytesnoescape.append(csum)

        # 0x10 escape
        self.sendbytesescape.clear()
        for i in self.sendbytesnoescape:
            self.sendbytesescape.append(i)
            if i == 0x10:
                self.sendbytesescape.append(i)
        senddata = DLE + STX + self.sendbytesescape + DLE + ETX

        # print("debug: senddata = " + str(senddata))

        try:
            self.comm.write(senddata)
            self.isPortOpen = True
            # DEBUG
            print('senddata = ', senddata)
            print('senddata = ', senddata.hex())

        except serial.SerialException:
            self.isPortOpen = False
            print("Can't send data through serial port.")

        return self.isPortOpen, senddata

    # Stop Serial Comm
    def stop(self):
        self.event.set()

    # Close Serial Port
    def close(self):
        self.stop()
        self.comm.close()
        
