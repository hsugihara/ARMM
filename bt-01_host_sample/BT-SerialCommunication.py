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

# State
STATE_POWERON = 0       # Power on
STATE_WAIT4BT01 = 1     # Wait for BT-01 is alive
STATE_HEARTBEAT = 2     # Normal State
STATE_BT_DEAD = 3       # BT-01 no response

# Commands
# A2B : AIBOX to BT-01
# B2A : BT-01 to AIBOX
# format : <DLE><STX>[command1byte][parameter0～128byte][checksum1byte]<DLE><ETX>
# checksum : sum (lowest 8 bit) of command & parameter
# if 0x10 appears in command & parameter, add 0x10 just after 0x10 as escape of <DLE>
DLE = bytearray([0x10])
STX = bytearray([0x02])
ETX = bytearray([0x03])

CMD_ALIVE_REQ = bytearray([0x55])       # A2B   : Notice AI BOX is alive
CMD_ALIVE_RES = bytearray([0xAA])       # B2A   : Response to alive_req
CMD_STATUS_REQ = bytearray([0x01])      # A2B   : Status request to BT-01
CMD_STATUS_RES = bytearray([0x81])      # B2A   : Status response (Contents TBD)
CMD_TIME_SYNC_REQ = bytearray([0x02])   # A2B   : Sync Data & Time
CMD_TIME_SYNC_RES = bytearray([0x82])   # B2A   : Response to Sync req (return Data & Time)
CMD_LOG_REQ = bytearray([0x03])         # A2B   : LOG request
CMD_LOG_RES = bytearray([0x83])         # B2A   : Response to LOG req (LOG format TBD)
CMD_REBOOT_REQ = bytearray([0x04])      # A2B   : Cold reboot request
CMD_REBOOT_RES = bytearray([0x84])      # B2A   : Response to reboot req
CMD_NOP = bytearray([0x00])             # A2B   : Just test Tx
CMD_NOP_RES = bytearray([0x80])         # B2A   : Received NOP (test Rx)
CMD_UNKNOWN_RES = bytearray([0xFF])     # B2A/A2B   : Received unknown command

#
# Serial communication parameters
#
# FIXME: set /dev/tty
DEVTTYNAME = '/dev/ttyACM0'   # Serial Port tty
BAUDRATE = '115200'           # Serial Port Baud Rate

#
# Logging
#
# FIXME: log should be append to /ver/log/syslog
loggingFileName = '/home/nvidia/bt-01/BT-log'
formatter = '%(asctime)s : %(levelname)s : %(message)s'

# HEART BEAT timer (5 min. period)
HB_TIME_PERIOD = 300        # should be 300

# ping time out = 5 min. x 4 times, ping hosts : google
PING_TIME_OUT = 300         # should be 300
PING_TIME_OUT_COUNT = 4
hosts = ["8.8.8.8", "www.google.com"]


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
    strbytes = 'BT01 DEBUG: ' + str(datetime.datetime.now()) + strlog + '\n'
    # print(strbytes)
    f.write(strbytes)
    f.close()
    return


#
# Convert number to BCD
#
def convert2bcd(num):
    num_bcd = int((0x10 * int(num / 10))) + int(num % 10)
    return num_bcd


#
# shift every day log file for 1-7 management
#
def shiftlogfile():
    logging.info("start to shift log files")
    for i in range(7, 0, -1):
        filename = loggingFileName + '.' + str(i)
        # print('BT log file name = ', filename)
        if os.path.exists(filename):
            if i == 7:
                os.remove(filename)
            else:
                os.rename(loggingFileName + '.' + str(i), loggingFileName + '.' + str(i + 1))
    if os.path.exists(loggingFileName):
        shutil.copy2(loggingFileName, loggingFileName + '.1')

        with open(loggingFileName, "r+") as f:
            # print(f.read())
            f.truncate(0)  # ファイル内容のクリア
    return


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

        # Open Serial Port. wait for success
        while True:
            try:
                self.comm = serial.Serial(tty, baudrate, timeout=timeoutvalue)
                self.isPortOpen = True
                break
            except serial.SerialException:
                self.isPortOpen = False

    # Receiving Data with time out setting[sec]
    def recv(self, timeout=300):
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
                # Time out process
                result = False
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
                    result = True
                    self.stop()
                    break

        # Return Result
        if result:
            # DEBUG
            print('self.recvData = ', self.recvData)

            # write recvData as log
            strlog = 'self.recvData = ' + str(self.recvData)
            writelog(strlog)

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
                logging.debug("received data check sum is correct")
            else:
                logging.debug("received data check sum is not correct")
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

        return result, self.recvData, self.recvCommand, self.afterEscapeSequence

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

        try:
            self.comm.write(senddata)
            self.isPortOpen = True
            # DEBUG
            print('senddata = ', senddata)

            strlog = 'self.senddata = ' + str(senddata)
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

    # TODO: read BT-01 status -> need to define status(parameters)
    def readstatus(self):
        # send status_req
        logging.debug("send status request")
        result = self.send(CMD_STATUS_REQ)
        if not result:
            return result
        else:
            result, rxdata, rxcommand, rxparameter = self.recv(30)
            # TODO: here, analysis the status
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
                logging.debug("received BT-01 RTC response")
                print("RxParameter (RTC) = ", rxparameter)
            else:
                logging.debug("not received RTC sync response")
        return

    # @print_info
    # @print_more
    def readlogs(self):
        logging.debug("send bt01 log request")
        print(str(datetime.datetime.now()) + " Read Logs starts")
        while True:
            result = BtComm.send(self, CMD_LOG_REQ)
            if not result:
                logging.debug("log request failed")
                break
            else:
                result, rxdata, rxcommand, rxparameter = self.recv(30)
                if result:
                    logging.debug("received BT-01 log")
                    print("RxParameter (log) = ", rxparameter)

                    f = open(loggingFileName, 'a')
                    strbytes = 'BT01 LOG: ' + str(rxparameter) + '\n'
                    print(strbytes)
                    f.write(strbytes)
                    f.close()

                    # check log end
                    if (rxparameter.find(b'NO LOG')) >= 0:
                        break
                    else:
                        time.sleep(1)

                else:
                    logging.debug("not received BT-01 log")
                    print("not received BT-01 log")
        return result

    # cold boot request
    def coldboot(self):
        logging.debug("send cold reboot request")
        result = BtComm.send(self, CMD_REBOOT_REQ)
        if not result:
            return
        else:
            result, rxdata, rxcommand, rxparameter = self.recv(30)
            if result:
                logging.debug("received coldBoot response")
                print("received coldBoot response")
            else:
                logging.debug("not received coldBoot response")
                print("not received coldBoot response")
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
    logging.debug('start to open serial port & wait for "opened" successfully')
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
    logging.info('program started.  wait for 1 minutes for system up')
    print("program started.  wait for 1 minutes for system up")
    time.sleep(60)

    #
    # start main loop of state machine
    #
    while True:
        if state == STATE_POWERON:
            # DEBUG
            print('Start Shift from POWERON to WAIT4BT01')

            # Shift to STATE:01 "BT-01確認待機"
            state = STATE_WAIT4BT01  # Current STATE: 01
            logging.info('state = STATE_WAIT4BT01')
            pstate = STATE_POWERON  # Previous STATE: 00

        elif state == STATE_WAIT4BT01:
            # STATE:01 処理
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
                        print('Received alive_res, BT01 is alive.')
                        break

                # just sleep 5 sec. (should be 60 sec.)
                time.sleep(60)

            # shift to next state
            state = STATE_HEARTBEAT
            logging.info('state = STATE_HEARTBEAT')
            pstate = STATE_WAIT4BT01

        elif state == STATE_HEARTBEAT:
            # first time to come ? (Entering Process ?)
            if pstate == STATE_WAIT4BT01:
                pstate = STATE_HEARTBEAT
                # DEBUG
                print('Start Shift Process from WAIT4BT01 to HEARTBEAT')

                # read BT-01 status
                logging.debug("send status request")
                result = btcom.send(CMD_STATUS_REQ)
                if result:
                    result, rxdata, rxcommand, rxparameter = btcom.recv(10)
                    # status is not implemented, yet in current bt-01

                # sync RTC
                btcom.syncrtc()
                # read all logs & write them to logging
                result = btcom.readlogs()

                # Set to read LOG every day at 2:00 am
                schedule.every().days.at("02:00").do(btcom.readlogs)
                # Set to shift log files every day at 2:15am
                schedule.every().days.at("02:15").do(shiftlogfile)

                # initiate ping
                ping_time_start = time.time()
                ping_time_end = ping_time_start
                ping_counter = 0

                # heart beat timer
                hb_time_start = time.time()
                hb_time_end = hb_time_start

            elif pstate == STATE_BT_DEAD:
                pstate = STATE_HEARTBEAT
                # DEBUG
                print('Start Shift Process from BT_DEAD to HEARTBEAT')

                # read BT-01 status
                logging.debug("send status request")
                result = btcom.send(CMD_STATUS_REQ)
                if result:
                    result, rxdata, rxcommand, rxparameter = btcom.recv(10)
                    # status is not implemented, yet in current bt-01

                # sync RTC
                btcom.syncrtc()
                # read all logs
                btcom.readlogs()

                # Set to read LOG every day at 2:00 am
                schedule.every().days.at("02:00").do(btcom.readlogs)
                # Set to shift log files every day at 2:15am
                schedule.every().days.at("02:15").do(shiftlogfile)

                # initiate ping
                ping_time_start = time.time()
                ping_time_end = ping_time_start
                ping_counter = 0

                # heart beat timer
                hb_time_start = time.time()
                hb_time_end = hb_time_start

            else:
                # STATE:02 処理
                # just put sleep, could be 10 sec.
                time.sleep(10)

                # HEART BEAT timing ?
                # DEBUG
                # print("start heart beat timing check")
                hb_time_end = time.time()
                if hb_time_end - hb_time_start > HB_TIME_PERIOD:
                    # HEART BEAT process
                    # DEBUG
                    print('Send HEARTBEAT')

                    # send 'alive_req' and wait for 'alive_res'
                    #  send alive_req command
                    result = btcom.send(CMD_ALIVE_REQ)
                    if not result:
                        # 送信不能：何かが異常になった
                        # move to POWERON state
                        state = STATE_POWERON
                        logging.info('Due to serial communication error, shift to state = SATE_POWERON')
                        continue

                    #  wait for alive_res w/ 10 sec. time out
                    result, rxdata, rxcommand, rxparameter = btcom.recv(10)
                    # data received ?
                    if result:
                        # alive_res ?
                        if rxdata == b'\x10\x02\xaa\xaa\x10\x03':
                            # yes
                            hb_time_start = time.time()
                            hb_time_end = hb_time_start
                            # DEBUG
                            logging.info('Received HEARTBEAT Response')
                            print("Received HEARTBEAT Response")

                        else:
                            # if not alive_res, just ignore it
                            # just in case of communication error
                            hb_time_start = time.time()
                            hb_time_end = hb_time_start
                            # DEBUG
                            logging.info('Not received HEARTBEAT response but something else')
                            print("Not received HEARTBEAT response but something else")
                            continue

                    else:
                        # Not received 'alive_res' in 10 sec.
                        state = STATE_BT_DEAD
                        logging.info('state = STATE_BT_DEAD')
                        pstate = STATE_HEARTBEAT
                        # DEBUG
                        print('NOT received BT01 HEARTBEAT Response')
                        break

                #
                # if LTE is not working, send reboot_req & wait for reboot_res
                #   After receiving reboot_res, start shutdown
                #
                ping_time_end = time.time()
                if ping_time_end - ping_time_start > PING_TIME_OUT:
                    # execute ping
                    # DEBUG
                    print("Start ping")
                    for host in hosts:
                        res = subprocess.run(["ping", host, "-c", "2", "-W", "300"], stdout=subprocess.PIPE)
                        if res.returncode == 0:
                            # DEBUG
                            logging.debug('ping OK')
                            ping_time_start = time.time()
                            ping_time_end = ping_time_start
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
                                print("ping does not reach !!  Send Cold Boot Req and Shutdown")
                                btcom.coldboot()
                                # check received res
                                # if received, execute shutdown
                                # if not, maybe can do something
                                # but ANYWAY shutdown
                                os.system('shutdown -s')

                            else:
                                ping_time_start = time.time()
                                ping_time_end = ping_time_start

                # execute to read LOG
                # every day 2 am
                schedule.run_pending()

        else:
            # STATE:03 STATE_BT_DEAD
            # every 5 min, send alive_req and wait for alive_res
            while True:
                # close & open to just to recover some errors
                btcom.close()
                # DEBUG put 5 sec for debug
                time.sleep(5)
                btcom = BtComm(DEVTTYNAME, BAUDRATE)
                # send 'alive_req' and wait for 'alive_res' w/ interval 5 min.
                #  send alive_req command
                btcom.send(CMD_ALIVE_REQ)
                #  wait for alive_res w/ 5 min. time out
                result, rxdata, rxcommand, rxparameter = btcom.recv(300)
                # data received ?
                if result:
                    # alive_res ?
                    if rxdata == b'\x10\x02UU\x10\x03':
                        # yes
                        break

            # shift to next state
            state = STATE_HEARTBEAT
            logging.info('state = STATE_HEARTBEAT')
            pstate = STATE_BT_DEAD


if __name__ == '__main__':
    main()
