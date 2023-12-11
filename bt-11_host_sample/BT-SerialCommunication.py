# -*- coding: utf-8 -*-

import time
import threading
import os
import shutil

import logging
import subprocess
import datetime

import schedule
import serial

# version description
# described at logging.info at the beginning
VERSIONDESCRIPTION = 'version 2023/11/16 : no STATE_BT_DEAD, heartbeat = every 5min.'

# State
STATE_POWERON = 0       # Power on
STATE_WAIT4BT11 = 1     # Wait for BT-11 is alive
STATE_HEARTBEAT = 2     # Normal State

# Commands
# A2B : AIBOX to BT-11
# B2A : BT-11 to AIBOX
# format : <DLE><STX>[command1byte][parameter0～128byte][checksum1byte]<DLE><ETX>
# checksum : sum (lowest 8 bit) of command & parameter
# if 0x10 appears in command & parameter, add 0x10 just after 0x10 as escape of <DLE>
DLE = bytearray([0x10])
STX = bytearray([0x02])
ETX = bytearray([0x03])

CMD_ALIVE_REQ = bytearray([0x55])           # A2B   : Notice AI BOX is alive
CMD_ALIVE_RES = bytearray([0xAA])           # B2A   : Response to alive_req
CMD_STATUS_REQ = bytearray([0x01])          # A2B   : Status request to BT-11
CMD_STATUS_RES = bytearray([0x81])          # B2A   : Status response (Contents TBD)
CMD_TIME_SYNC_REQ = bytearray([0x02])       # A2B   : Sync Data & Time
CMD_TIME_SYNC_RES = bytearray([0x82])       # B2A   : Response to Sync req (return Data & Time)
CMD_LOG_REQ = bytearray([0x03])             # A2B   : LOG request
CMD_LOG_RES = bytearray([0x83])             # B2A   : Response to LOG req (LOG format TBD)
CMD_REBOOT_REQ = bytearray([0x04])          # A2B   : Cold reboot request
CMD_REBOOT_RES = bytearray([0x84])          # B2A   : Response to reboot req
CMD_POWEROFF_TIME_REQ = bytearray([0x05])       # A2B   : bt-11 Only : Power Off time setting request
CMD_POWEROFF_TIME_RES = bytearray([0x85])       # B2A   : bt-11 Only : Response to Power Off time setting request
CMD_HEARTBEAT_PERIOD_REQ = bytearray([0x06])    # A2B   : bt-11 Only : heartbeat period setting request
CMD_HEARTBEAT_PERIOD_RES = bytearray([0x86])    # B2A   : bt-11 Only : Response to heartbeat period setting request
CMD_POWER_BUTTON_REQ = bytearray([0x07])        # A2B   : bt-11 Only : press power button
CMD_POWER_BUTTON_RES = bytearray([0x87])        # B2A   : bt-11 Only : Response to press power button
CMD_RESET_BUTTON_REQ = bytearray([0x08])        # A2B   : bt-11 Only : press reset button
CMD_RESET_BUTTON_RES = bytearray([0x88])        # B2A   : bt-11 Only : Response to press reset button
CMD_TEMPERATURE_REQ = bytearray([0x09])         # A2B   : bt-11 Only : read temperature
CMD_TEMPERATURE_RES = bytearray([0x89])         # B2A   : bt-11 Only : Response to read temperature
CMD_NOP = bytearray([0x00])                 # A2B   : Just test Tx
CMD_NOP_RES = bytearray([0x80])             # B2A   : Received NOP (test Rx)
CMD_UNKNOWN_RES = bytearray([0xFF])         # B2A/A2B   : Received unknown command

#
# Serial communication parameters
#
# set /dev/tty & baud rate
DEVTTYNAME = "/dev/ttyTHS0"     # Serial Port tty : Orin NX/nano UART1
BAUDRATE = 1200                 # Serial Port Baud Rate : 1200 because of keeping signal quality

#
# Logging
#
# logs append to /home/nvidia/bt-11
loggingFileName = '/home/nvidia/bt-11/BT-log'
formatter = '%(asctime)s : %(levelname)s : %(message)s'

#
# HEART BEAT parameters (set to 5 min. period)
#
# Heartbeat Period for this program (host side)
HEARTBEAT_TIME_PERIOD = 300            # 5 min. = 5x60 sec.
# Heartbeat Period for ARMM
# Set the period to double of host period + 2 min. = 12 min.
#    double is for recovering a case of one communication error happened
#    2 min. is for recovering time error (margin) between host and ARMM
#
HEARTBEAT_PERIOD = 11       # 12 min.

# Power Off time (30 sec.)
POWEROFF_TIME = 0               # for poweroff time command : 0 = 30 sec.

# ping time out = 5 min. x 4 times
PING_TIME_OUT = 300             # should be 300
PING_TIME_OUT_COUNT = 4         # if continuous ping failed 4 times, reset LTE
hosts = ["8.8.8.8", "www.google.com"]   # set 2 hosts for ping


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


# write log(print) to BT log file
def writelog(strlog):
    f = open(loggingFileName, 'a')
    strbytes = 'BT11 DEBUG: ' + str(datetime.datetime.now()) + strlog + '\n'
    # print(strbytes)
    f.write(strbytes)
    f.close()
    return


#
# Convert hex int (one byte) to BCD format (one byte)
#
def convert2bcd(num):
    num_bcd = int((0x10 * int(num / 10))) + int(num % 10)
    return num_bcd


#
# shift every day log files for 1-7 management
#
def shiftlogfile():
    logging.info("start to shift log files")
    for i in range(7, 0, -1):
        filename = loggingFileName + '.' + str(i)
        # print('BT log file name = ', filename)
        if os.path.exists(filename):
            if i == 7:
                os.remove(filename)     # remove loggingFileName.7
            else:
                os.rename(loggingFileName + '.' + str(i), loggingFileName + '.' + str(i + 1))
    if os.path.exists(loggingFileName):
        shutil.copy2(loggingFileName, loggingFileName + '.1')

        with open(loggingFileName, "r+") as f:
            # print(f.read())
            f.truncate(0)   # clear file contents
    return


#
# AI BOX Serial Communication Class to BT-11
#
class BtComm(object):
    def __init__(self, tty, baudratevalue=1200, timeoutvalue=10.0):
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

        # Open Serial Port. wait for success until success
        while True:
            try:
                self.comm = serial.Serial(
                    port=tty, 
                    baudrate=baudratevalue, 
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=timeoutvalue
                    )
                self.isPortOpen = True              # opened successfully
                break
            except serial.SerialException:
                self.isPortOpen = False             # failed
                # not break until success
                # break

        return

    # Receiving Data with time out setting[sec]
    def recv(self, timeout=300.0):
        # for time out
        time_start = time.time()
        # Clear event to wait thread
        self.event.clear()
        # Clear Rx Buffer
        self.recvData.clear()
        # Rx result : True (success) False (fault: time out)
        result = False

        # Wait for Rx
        while not self.event.is_set():
            # Check time out
            time_end = time.time()
            if time_end - time_start > timeout:
                # time out process
                result = False
                self.stop()
                # for DEBUG
                print("Rx timeout:{0}sec".format(timeout))
                # write recvData as log
                strlog = "Rx timeout:{0}sec".format(timeout)
                writelog(strlog)
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
                    result = True
                    self.stop()
                    break

        # Return Result
        if result:
            # DEBUG
            print('self.recvData = ', self.recvData)
            print('self.recvData = ', self.recvData.hex())

            # write recvData as log
            strlog = 'self.recvData = ' + str(self.recvData)
            writelog(strlog)
            strlog = 'self.recvData = ' + str(self.recvData.hex())
            writelog(strlog)

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
                logging.debug("received data check sum is correct")
                print("received data check sum is correct")
            else:
                logging.debug("received data check sum is not correct")
                print("received data check sum is not correct")
            # send CMD_UNKNOWN_RES
            # but not need now

        return result, self.recvData, self.recvCommand, self.afterEscapeSequence

    # Send Data
    def send(self, data):
        # here, argument data = command +  parameter bytearray
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

        try:
            self.comm.write(senddata)
            self.isPortOpen = True
            # DEBUG
            print('senddata = ', senddata)
            print('senddata = ', senddata.hex())

            strlog = 'self.senddata = ' + str(senddata)
            writelog(strlog)
            strlog = 'self.senddata = ' + str(senddata.hex())
            writelog(strlog)
            
        except serial.SerialException:
            self.isPortOpen = False
            logging.error("Can't send data through serial port.")

        return self.isPortOpen

    # Stop Serial Comm
    def stop(self):
        self.event.set()

    # Close Serial Port
    def close(self):
        self.stop()
        if self.isPortOpen:
            self.comm.close()
        self.isPortOpen = False

    # read BT-11 status -> need to define status(parameters)
    def readstatus(self):
        # send status_req
        logging.debug("send status request")
        result = self.send(CMD_STATUS_REQ)
        if not result:
            return result
        else:
            result, rxdata, rxcommand, rxparameter = self.recv(30.0)
            # here, analysis the status if required
        return result

    # sync RTC
    def syncrtc(self):
        logging.debug("send RTC sync request")
        print("send RTC sync request")
        # generate RTC sync parameters
        #   <YY><MM><DD><hh><mm><ss>
        #     <1 byte> x 6
        dt_now = datetime.datetime.now()
        rtc_data = bytearray()
        rtc_data.append(0x02)
        rtc_data.append(convert2bcd(dt_now.year % 100))
        rtc_data.append(convert2bcd(dt_now.month))
        rtc_data.append(convert2bcd(dt_now.day))
        rtc_data.append(convert2bcd(dt_now.hour))
        rtc_data.append(convert2bcd(dt_now.minute))
        rtc_data.append(convert2bcd(dt_now.second))

        # DEBUG
        for i in rtc_data:
            hex_n = '{:02x}'.format(i)
            print('0x' + hex_n)

        result = self.send(rtc_data)
        print("rtc_data = ", rtc_data)
        if not result:
            return
        else:
            result, rxdata, rxcommand, rxparameter = self.recv(30)
            if result:
                logging.debug("received BT-11 RTC response")
                print("RxParameter (RTC) = ", rxparameter)
            else:
                logging.debug("not received RTC sync response")
        return

    # @print_info
    # @print_more
    def readlogs(self):
        logging.debug("send BT11 log request")
        print(str(datetime.datetime.now()) + " Read Logs starts")
        while True:
            result = self.send(CMD_LOG_REQ)
            if not result:
                logging.debug("log request failed")
                break
            else:
                result, rxdata, rxcommand, rxparameter = self.recv(30.0)
                if result:
                    logging.debug("received BT-11 log")
                    print("RxParameter (log) = ", rxparameter)

                    f = open(loggingFileName, 'a')
                    strbytes = 'BT11 LOG: ' + str(rxparameter) + '\n'
                    print(strbytes)
                    f.write(strbytes)
                    f.close()

                    # check log end
                    if (rxparameter.find(b'NO LOG')) >= 0:
                        break
                    else:
                        time.sleep(1)

                else:
                    logging.debug("not received BT-11 log")
                    print("not received BT-11 log")
        return result

    # cold boot request
    def coldboot(self):
        logging.debug("send cold reboot request")
        result = self.send(CMD_REBOOT_REQ)
        if not result:
            return
        else:
            result, rxdata, rxcommand, rxparameter = self.recv(30.0)
            if result:
                logging.debug("received coldBoot response")
                print("received coldBoot response")
            else:
                logging.debug("not received coldBoot response")
                print("not received coldBoot response")
        return

    def heartbeat_period(self):
        logging.debug("send heartbeat period request")

        hb_period = bytearray()
        hb_period.append(0x06)
        hb_period.append(HEARTBEAT_PERIOD)
        result = self.send(hb_period)
        if not result:
                 return
        else:
            result, rxdata, rxcommand, rxparameter = self.recv(30.0)
            if result:
                logging.debug("received heartbeat period response")
                print("received heartbeat period response")
            else:
                logging.debug("not received heartbeat period response")
                print("not received heartbeat period response")
        return

    def poweroff_time(self):
        logging.debug("send power off time request")

        powerofftime = bytearray()
        powerofftime.append(0x05)
        powerofftime.append(POWEROFF_TIME)
        result = self.send(powerofftime)
        if not result:
            return
        else:
            result, rxdata, rxcommand, rxparameter = self.recv(30.0)
            if result:
                logging.debug("received power off time response")
                print("received power off time response")
            else:
                logging.debug("not received power off time response")
                print("not received power off time response")
        return


def main():
    logging.basicConfig(filename=loggingFileName, format=formatter, level=logging.DEBUG)
    # logging.basicConfig(filename=loggingFileName, encoding='utf-8', format=formatter, level=logging.DEBUG)
    # logging.basicConfig(encoding='utf-8', format=formatter, level=logging.DEBUG)
    # logging.basicConfig(level=logging.DEBUG)
    # logger = logging.getLogger(__name__)
    # h = logging.FileHandler(loggingFileName)
    # logger.addHandler(h)
    #
    logging.info('=============================================')
    logging.info('AIBOX Program (re-)started : start log output')
    logging.info(VERSIONDESCRIPTION)
    ''' 
    logging message examples
    logging.critical('CRITICAL MESSAGE')
    logging.error('ERROR MESSAGE')
    logging.warning('WARNING MESSAGE')
    logging.info('INFO MESSAGE')
    logging.debug('DEBUG MESSAGE')
    '''

    # -- STATE = 00 "Power On" -- #
    state = STATE_POWERON
    pstate = STATE_POWERON

    # Continue til port opened
    logging.debug('start to open serial port & wait for "opened" successfully forever')
    print("Start to open serial port")

    btcom = BtComm(DEVTTYNAME, BAUDRATE)

    logging.debug('opened serial port !')
    print("Opened serial port")
    hb_time_start = time.time()
    ping_time_start = time.time()
    logging.info('state = STATE_POWERON')

    #
    # just wait for system up and running
    #
    logging.info('program started.  wait for 15 seconds for system up')
    time.sleep(15)

    #
    # start main loop of state machine
    #
    while True:
        if state == STATE_POWERON:
            # since serial port is already opened, shift to WAIT4BT11

            # DEBUG
            print('Start Shift from POWERON to WAIT4BT11')

            # Shift to STATE:01 "wait for alive_res" from bt-11
            state = STATE_WAIT4BT11     # next STATE: 01
            logging.info('shift state = STATE_WAIT4BT11, pstate = STATE_POWERON')
            pstate = STATE_POWERON      # Previous STATE: 00

        elif state == STATE_WAIT4BT11:
            # STATE:01 処理
            strlog = "state = STATE_WAIT4BT11"
            writelog(strlog)
            # Start to send "alive_req" & wait for alive_res
            #   write log "start to send 'alive_req'"
            #       try with 1 min interval
            #           if receiving, shift to STATE:02
            #           if not, continue
            while True:
                # send 'alive_req' and wait for 'alive_res' w/ interval 1 min.
                #  send alive_req command
                btcom.send(CMD_ALIVE_REQ)
                #  wait for alive_res w/ 1 min. time out
                result, rxdata, rxccmmand, rxparameter = btcom.recv(60)
                # data received ?
                if result:
                    # alive_res ?
                    if rxdata == b'\x10\x02\xaa\xaa\x10\x03':
                        # yes
                        print('Received alive_res, BT11 is alive.')
                        logging.info("Received alive_res, BT11 is alive.")
                        break

                # just sleep 60 sec.
                time.sleep(60)

            # shift to next state
            state = STATE_HEARTBEAT
            logging.info('shift state = STATE_HEARTBEAT, pstate = STATE_WAIT4BT11')
            pstate = STATE_WAIT4BT11

        else:       # state == STATE_HEARTBEAT:
            # first time to come ? (Entering Process ?)
            if pstate == STATE_WAIT4BT11:
                pstate = STATE_HEARTBEAT
                # DEBUG
                print('Start Shift Process from WAIT4BT11 to HEARTBEAT')
                strlog = "Start Shift Process from WAIT4BT11 to HEARTBEAT"
                writelog(strlog)

                # set heartbeat period to 5 min.
                btcom.heartbeat_period()

                # set power off time to 30 sec.
                btcom.poweroff_time()

                # read BT-11 status
                logging.debug("send status request")
                result = btcom.send(CMD_STATUS_REQ)
                if result:
                    result, rxdata, rxcommand, rxparameter = btcom.recv(10.0)
                    # here, analysis the status if required
                    # not implemented, now

                # sync RTC
                strlog = "Sync RTC"
                writelog(strlog)
                btcom.syncrtc()

                # read all logs
                strlog = "Read all logs from BT11"
                writelog(strlog)
                result = btcom.readlogs()

                # Set to read LOG every day at 2:00 am
                schedule.every().days.at("02:00").do(btcom.readlogs)
                # Set to shift log files every day at 2:15am
                schedule.every().days.at("02:15").do(shiftlogfile)

                # initiate ping
                ping_time_start = time.time()
                # ping_time_end = ping_time_start
                ping_counter = 0

                # heart beat timer
                hb_time_start = time.time()
                # hb_time_end = hb_time_start

            else:
                # STATE:02 処理
                # just put sleep, could be 10 sec.
                time.sleep(10)

                # HEART BEAT timing ?
                # DEBUG
                # print("start heart beat timing check")
                hb_time_end = time.time()
                if hb_time_end - hb_time_start > HEARTBEAT_TIME_PERIOD:
                    # HEART BEAT process
                    # DEBUG
                    print('Send HEARTBEAT')
                    strlog = "Send HEARTBEAT"
                    writelog(strlog)

                    # send 'alive_req' and wait for 'alive_res'
                    #  send alive_req command
                    result = btcom.send(CMD_ALIVE_REQ)
                    if not result:
                        # move to POWERON state
                        state = STATE_POWERON
                        logging.info('Due to serial communication error to send, shift to state = SATE_POWERON')
                        continue

                    #  wait for alive_res w/ 15 sec. time out
                    result, rxdata, rxcommand, rxparameter = btcom.recv(15)
                    # data received ?
                    if result:
                        # alive_res ?
                        if rxdata == b'\x10\x02\xaa\xaa\x10\x03':
                            # yes
                            hb_time_start = time.time()
                            # hb_time_end = hb_time_start
                            # DEBUG
                            logging.info('Received HEARTBEAT Response')

                        else:
                            # if not alive_res, just ignore it
                            # just in case of communication error
                            hb_time_start = time.time()
                            # hb_time_end = hb_time_start
                            # DEBUG
                            logging.info('Not received HEARTBEAT response but something else')
                            continue

                    else:
                        # Nothing received in 15 sec.
                        logging.info('Nothing received from BT-11 after HEARTBEAT Req')
                        # pstate = STATE_HEARTBEAT
                        # DEBUG
                        print('Nothing received from BT-11 after HEARTBEAT Req')
                        # just do nothing, and re-try heartbeat

                #
                # if LTE is not working, send reboot_req & wait for reboot_res
                #   After receiving reboot_res, start shutdown
                #
                ping_time_end = time.time()
                if ping_time_end - ping_time_start > PING_TIME_OUT:
                    # execute ping
                    # DEBUG
                    print("Start ping")
                    strlog = "Start ping"
                    writelog(strlog)

                    for host in hosts:
                        res = subprocess.run(["ping", host, "-c", "2", "-W", "300"], stdout=subprocess.PIPE)
                        if res.returncode == 0:
                            # DEBUG
                            logging.debug('ping OK')
                            ping_time_start = time.time()
                            # ping_time_end = ping_time_start
                            ping_counter = 0
                        else:
                            # not received ping
                            logging.debug("ping failed")
                            ping_counter += 1
                            if ping_counter >= PING_TIME_OUT_COUNT:
                                # WAN network is not working
                                # no connection to internet, cold reboot AI BOX
                                # cold reboot request
                                # DEBUG
                                logging.info('ping does not reach !!  Send Cold Boot Req and Shutdown')
                                btcom.coldboot()
                                # check received res
                                # if received, execute shutdown
                                # if not resend cold boot request
                                # but ANYWAY shutdown
                                os.system('shutdown -h now')

                            else:
                                ping_time_start = time.time()
                                # ping_time_end = ping_time_start

                # execute to read LOG
                # every day 2 am
                schedule.run_pending()


if __name__ == '__main__':
    main()
