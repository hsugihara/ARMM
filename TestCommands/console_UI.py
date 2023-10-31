# -*- coding: utf-8 -*-

import datetime
import sys
import time

import tkinter as tk
from tkinter.font import Font

# from bt_SerialCommunication import BtComm
# from commands_parameters import *
from btSerial import BtComm

# import test_console_process
# from test_console_process import TCProcess

# Commands
# A2B : AIBOX to BT-01
# B2A : BT-01 to AIBOX
# format : <DLE><STX>[command1byte][parameter0～128byte][checksum1byte]<DLE><ETX>
# checksum : sum (lowest 8 bit) of command & parameter
# if 0x10 appears in command & parameter, add 0x10 just after 0x10 as escape of <DLE>
# DLE = bytearray([0x10])
# STX = bytearray([0x02])
# ETX = bytearray([0x03])

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
CMD_POWEROFF_TIME_REQ = bytearray([0x05])   # A2B   : Power Off time setting request
CMD_POWEROFF_TIME_RES = bytearray([0x85])   # B2A   : Response to Power Off time setting request
CMD_HEARTBEAT_PERIOD_REQ = bytearray([0x06])    # A2B   : Heartbeat period setting request
CMD_HEARTBEAT_PERIOD_RES = bytearray([0x86])    # B2A   : Response to Heartbeat period setting request
CMD_POWER_BUTTON_REQ = bytearray([0x07])    # A2B   : Power button depressing request
CMD_POWER_BUTTON_RES = bytearray([0x87])    # B2A   : Response to Power button depressing request
CMD_RESET_BUTTON_REQ = bytearray([0x08])    # A2B   : RESET button depressing request
CMD_RESET_BUTTON_RES = bytearray([0x88])    # B2A   : Response to RESET button depressing request
CMD_TEMPERATURE_REQ = bytearray([0x09])     # A2B   : Temperature reading request
CMD_TEMPERATURE_RES = bytearray([0x89])     # B2A   : Response to Temperature reading request
CMD_NOP = bytearray([0x00])             # A2B   : Just test Tx
CMD_NOP_RES = bytearray([0x80])         # B2A   : Received NOP (test Rx)
CMD_UNKNOWN_RES = bytearray([0xFF])     # B2A/A2B   : Received unknown command


class TestConsole(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        # self.__frame = master

        #
        # Serial communication parameters
        #
        # set /dev/tty & baud rate (should be 1200 because of generating stable signal of bt-11)
        self.ttySerialPort = '/dev/ttyTHS0'     # Serial Port tty of Orin NX & nano UART1
        # self.ttySerialPort = '/dev/tty.usbmodem69A0933337381'     # mac tty serial port (example)
        self.serialBaudRate = "1200"
        # self.serialBaudrate = "115200"                            # mac baud rate to bt-01

        self.heartbeat_period = 4   # heartbeat period default : 5 min.
        self.heartbeat_millisecond = (self.heartbeat_period + 1) * 60 * 1000

        self.poweroff_time = 0      # 0: default 30 sec.
        #
        # GUI Setting
        #
        self.__button_alive_req_text = tk.StringVar()
        self.__button_alive_req_text.set("heartbeat on")
        self.__heartbeat_status = False
        self.__heartbeat_count = 0

        self.__button_status_req_text = tk.StringVar()
        self.__button_status_req_text.set("send")

        self.__button_time_sync_req_text = tk.StringVar()
        self.__button_time_sync_req_text.set("send")

        self.__button_log_req_text = tk.StringVar()
        self.__button_log_req_text.set("send")

        self.__button_cold_reboot_req_text = tk.StringVar()
        self.__button_cold_reboot_req_text.set("send")

        self.__button_poweroff_time_req_text = tk.StringVar()
        self.__button_poweroff_time_req_text.set("send")
        self.entry_poweroff_time = tk.StringVar()
        self.entry_poweroff_time.set("00")

        self.__button_heartbeat_period_req_text = tk.StringVar()
        self.__button_heartbeat_period_req_text.set("send")
        self.__entry_heartbeat_period = tk.StringVar()
        self.__entry_heartbeat_period.set("04")

        self.__button_power_button_req_text = tk.StringVar()
        self.__button_power_button_req_text.set("send")

        self.__button_reset_button_req_text = tk.StringVar()
        self.__button_reset_button_req_text.set("send")

        self.__button_temperature_req_text = tk.StringVar()
        self.__button_temperature_req_text.set("send")

        self.__button_nop_text = tk.StringVar()
        self.__button_nop_text.set("send")

        self.__button_quit_text = tk.StringVar()
        self.__button_quit_text.set("QUIT Test Console")

        # Tx Data frame
        __frameTx = tk.LabelFrame(master, text="Tx Data (hex)")
        __frameTx.pack(anchor="w", fill="x", expand=True, padx=10, pady=10)

        self.textBoxTx = tk.Text(__frameTx, height=7, width=80)
        self.textBoxTx.configure(font=Font(family='Arial', size=12))
        self.textBoxTx.grid(row=0, column=0, sticky=(tk.E + tk.W))

        __scrollbarTx = tk.Scrollbar(__frameTx, orient=tk.VERTICAL, command=self.textBoxTx.yview)
        __scrollbarTx.grid(row=0, column=1, sticky=(tk.N + tk.S))
        self.textBoxTx["yscrollcommand"] = __scrollbarTx.set
        self.textBoxTx.insert(tk.END, 'Tx Data is here\n')

        # self.textBoxTx.configure(state='disabled')

        # Rx Data frame
        __frameRx = tk.LabelFrame(master, text="Rx Data (hex)")
        __frameRx.pack(anchor="w", fill="x", expand=True, padx=10, pady=10)

        self.textBoxRx = tk.Text(__frameRx, height=7, width=80)
        self.textBoxRx.configure(font=Font(family='Arial', size=12))
        self.textBoxRx.grid(row=0, column=0, sticky=(tk.N + tk.W + tk.S + tk.E))

        __scrollbarRx = tk.Scrollbar(__frameRx, orient=tk.VERTICAL, command=self.textBoxRx.yview())
        self.textBoxRx["yscrollcommand"] = __scrollbarRx.set
        __scrollbarRx.grid(row=0, column=1, sticky=(tk.N + tk.S))
        self.textBoxRx.insert(tk.END, 'Rx Data is here\n')
        # self.textBoxRx.configure(state='disabled')

        # Serial Communication Commands frame
        __frameCommands = tk.LabelFrame(master, text="Serial Communication Commands")
        __frameCommands.pack(anchor="w", fill="x", expand=True, padx=10, pady=10)

        # alive request
        __label_alive_req = tk.Label(__frameCommands, text="alive_req")
        __label_alive_req.grid(row=0, column=0, sticky=tk.W)
        __button_alive_req = tk.Button(__frameCommands, textvariable=self.__button_alive_req_text,
                                       command=self.cmd_alive_req)
        __button_alive_req.grid(row=0, column=1, sticky=tk.E)
        __label_alive_req_comment = tk.Label(__frameCommands, text="  Must send alive_req first to ARMM.", foreground="#ff0000")
        __label_alive_req_comment.grid(row=0, column=3, sticky=tk.W)

        # status request
        __label_alive_req = tk.Label(__frameCommands, text="status_req")
        __label_alive_req.grid(row=1, column=0, sticky=tk.W)
        __button_alive_req = tk.Button(__frameCommands, textvariable=self.__button_status_req_text,
                                       command=self.cmd_status_req)
        __button_alive_req.grid(row=1, column=1, sticky=tk.E)

        # time sync request
        __label_alive_req = tk.Label(__frameCommands, text="time_sync_req")
        __label_alive_req.grid(row=2, column=0, sticky=tk.W)
        __button_alive_req = tk.Button(__frameCommands, textvariable=self.__button_time_sync_req_text,
                                       command=self.cmd_time_sync_req)
        __button_alive_req.grid(row=2, column=1, sticky=tk.E)
        __label_alive_req_comment = tk.Label(__frameCommands, text="  Sync ARMM time with this machine time.")
        __label_alive_req_comment.grid(row=2, column=3, sticky=tk.W)

        # log request
        __label_log_req = tk.Label(__frameCommands, text="log_req")
        __label_log_req.grid(row=3, column=0, sticky=tk.W)
        __button_log_req = tk.Button(__frameCommands, textvariable=self.__button_log_req_text, command=self.cmd_log_req)
        __button_log_req.grid(row=3, column=1, sticky=tk.E)

        # cold reboot request
        __label_cold_reboot_req = tk.Label(__frameCommands, text="cold_reboot_req")
        __label_cold_reboot_req.grid(row=4, column=0, sticky=tk.W)
        __button_cold_reboot_req = tk.Button(__frameCommands, textvariable=self.__button_cold_reboot_req_text,
                                             command=self.cmd_cold_reboot_req)
        __button_cold_reboot_req.grid(row=4, column=1, sticky=tk.E)

        # power off time request
        __label_poweroff_time_req = tk.Label(__frameCommands, text="poweroff_time_req")
        __label_poweroff_time_req.grid(row=5, column=0, sticky=tk.W)
        __button_poweroff_time_req = tk.Button(__frameCommands,
                                               textvariable=self.__button_poweroff_time_req_text,
                                               command=self.cmd_poweroff_time_req)
        __button_poweroff_time_req.grid(row=5, column=1, sticky=tk.E)
        __entry_poweroff_time = tk.Entry(__frameCommands, width=2, textvariable=self.entry_poweroff_time)
        __entry_poweroff_time.grid(row=5, column=2, sticky=tk.E, padx=1)
        __label_poweroff_time = tk.Label(__frameCommands, text="  Hex Value Input > 00:30 sec., 01-FF:1-255 min.")
        __label_poweroff_time.grid(row=5, column=3, sticky=tk.W)

        # heart beat period request
        __label_heartbeat_period_req = tk.Label(__frameCommands, text="heartbeat_period_req")
        __label_heartbeat_period_req.grid(row=6, column=0, sticky=tk.W)
        __button_heartbeat_period_req = tk.Button(__frameCommands,
                                                  textvariable=self.__button_heartbeat_period_req_text,
                                                  command=self.cmd_heartbeat_period_req)
        __button_heartbeat_period_req.grid(row=6, column=1, sticky=tk.E)
        self.entry_heartbeat_period = tk.Entry(__frameCommands, width=2, textvariable=self.__entry_heartbeat_period)
        self.entry_heartbeat_period.grid(row=6, column=2, sticky=tk.E, padx=1)
        __label_heartbeat_period = tk.Label(__frameCommands, text="  Hex Value Input > 00-FF:1 min.-256 min.")
        __label_heartbeat_period.grid(row=6, column=3, sticky=tk.W)


        # power button request
        __label_power_button_req = tk.Label(__frameCommands, text="power_button_req")
        __label_power_button_req.grid(row=7, column=0, sticky=tk.W)
        __button_power_button_req_text = tk.StringVar()
        __button_power_button_req_text.set("heartbeat off")
        __button_power_button_req = tk.Button(__frameCommands, textvariable=self.__button_power_button_req_text,
                                              command=self.cmd_power_button_req)
        __button_power_button_req.grid(row=7, column=1, sticky=tk.E)

        # reset button request
        __label_reset_button_req = tk.Label(__frameCommands, text="reset_button_req")
        __label_reset_button_req.grid(row=8, column=0, sticky=tk.W)
        __button_reset_button_req = tk.Button(__frameCommands, textvariable=self.__button_reset_button_req_text,
                                              command=self.cmd_reset_button_req)
        __button_reset_button_req.grid(row=8, column=1, sticky=tk.E)

        # temperature request
        __label_temperature_req = tk.Label(__frameCommands, text="temperature_req")
        __label_temperature_req.grid(row=9, column=0, sticky=tk.W)
        __button_temperature_req = tk.Button(__frameCommands, textvariable=self.__button_temperature_req_text,
                                             command=self.cmd_temperature_req)
        __button_temperature_req.grid(row=9, column=1, sticky=tk.E)

        # no operation
        __label_nop = tk.Label(__frameCommands, text="nop")
        __label_nop.grid(row=10, column=0, sticky=tk.W)
        __button_nop = tk.Button(__frameCommands, textvariable=self.__button_nop_text, command=self.cmd_nop)
        __button_nop.grid(row=10, column=1, sticky=tk.E)

        # Debug Messages frame
        __frameDebug = tk.LabelFrame(master, text="Debug Messages")
        __frameDebug.pack(anchor="w", fill="x", expand=True, padx=10, pady=10)

        self.textBoxDebug = tk.Text(__frameDebug, height=5, width=80)
        self.textBoxDebug.configure(font=Font(family='Arial', size=12))
        self.textBoxDebug.grid(row=0, column=0, sticky=(tk.N + tk.W + tk.S + tk.E))

        __scrollbarDebug = tk.Scrollbar(__frameDebug, orient=tk.VERTICAL, command=self.textBoxDebug.yview())
        self.textBoxDebug['yscrollcommand'] = __scrollbarDebug.set
        __scrollbarDebug.grid(row=0, column=1, sticky=(tk.N + tk.S))

        self.textBoxDebug.insert(tk.END, 'Debug Messages are here\n')
        # self.textBoxDebug.configure(state='disabled')

        # Quit this program
        __button_quit = tk.Button(master, textvariable=self.__button_quit_text, command=self.quitprogram)
        __button_quit.pack(anchor="e", fill="x", expand=True, padx=10, pady=10)

        #
        # set Serial Communication
        #  Orin NX/Nano tty serial port
        #
        # -- try to open serial port, wait til opened
        self.write_debug("Start to open serial port")
        # print("Start to open serial port")
        # __ttySerialPort = DEVTTYNAME
        # __serialBaudRate = BAUDRATE

        # open port
        self.bt_communication = BtComm(tty=self.ttySerialPort, baudratevalue=self.serialBaudRate)

        # print("Opened serial port")
        self.write_debug("Opened serial port")

    def cmd_alive_req(self):

        self.write_debug("heartbeat button pressed !")

        if self.__heartbeat_status:
            self.__heartbeat_status = False
            self.__button_alive_req_text.set("heartbeat on")
            self.heartbeat()

        else:
            self.__heartbeat_status = True
            self.__button_alive_req_text.set("heartbeat off")
            #
            # calculate period
            __heartbeat_count = 0
            self.heartbeat()

    def heartbeat(self):
        strdebug = "heartbeat !!  " + str(self.__heartbeat_count)
        self.write_debug(strdebug)

        if self.__heartbeat_status:

            txresult, txdata = self.bt_communication.send(CMD_ALIVE_REQ)

            self.__heartbeat_count += 1
            if txresult:
                # print(txdata)
                self.write_txdata(txdata.hex())
            else:
                # print("alive_req send error")
                self.write_debug("alive_req send error")

            rx_result, rxdata = self.bt_communication.recv(15)

            # print(rx_result, rxdata)
            self.write_rxdata(rxdata.hex())
            self.heartbeat_millisecond = (self.heartbeat_period + 1) * 60 * 1000
            self.write_debug("heartbeat_millisecond = " + str(self.heartbeat_millisecond))
            self.__heartbeat_id = self.master.after(self.heartbeat_millisecond, self.heartbeat)

        else:
            self.master.after_cancel(self.__heartbeat_id)


    def cmd_status_req(self):
        self.write_debug("status_req")

        txresult, txdata = self.bt_communication.send(CMD_STATUS_REQ)

        if txresult:
            self.write_txdata(txdata.hex())
            rx_result, rxdata = self.bt_communication.recv(15)
            self.write_rxdata(rxdata.hex())
        else:
            self.write_debug("status_req send error")

    def cmd_time_sync_req(self):
        #
        self.write_debug("time_sync_req")
        # generate RTC sync parameters
        #   <YY><MM><DD><hh><mm><ss>
        #     <1 byte> x 6
        dt_now = datetime.datetime.now()
        rtc_data = bytearray()
        rtc_data.append(0x02)
        rtc_data.append(self.convert2bcd(dt_now.year % 100))
        rtc_data.append(self.convert2bcd(dt_now.month))
        rtc_data.append(self.convert2bcd(dt_now.day))
        rtc_data.append(self.convert2bcd(dt_now.hour))
        rtc_data.append(self.convert2bcd(dt_now.minute))
        rtc_data.append(self.convert2bcd(dt_now.second))

        # print("rtc_data = ", rtc_data.hex())
        txresult, txdata = self.bt_communication.send(rtc_data)
        # print("txdata = ", txdata.hex())

        if txresult:
            self.write_txdata(txdata.hex())
            # print("rtc sent and wait for response")
            rx_result, rxdata = self.bt_communication.recv(15)
            # print("rtc response received")
            self.write_rxdata(rxdata.hex())
        else:
            self.write_debug("time_sync_req send error")

    def cmd_log_req(self):
        self.write_debug("log_req, logs_reading starts")

        txresult, txdata = self.bt_communication.send(CMD_LOG_REQ)

        if not txresult:
            self.write_debug("log request failed")

        else:

            self.write_txdata(txdata.hex())
            rx_result, rxdata = self.bt_communication.recv(15)

            self.write_rxdata(rxdata.hex())

    def cmd_cold_reboot_req(self):
        self.write_debug("cold_reboot_req")

        txresult, txdata = self.bt_communication.send(CMD_REBOOT_REQ)

        if txresult:
            self.write_txdata(txdata.hex())
            rx_result, rxdata = self.bt_communication.recv(15)
            self.write_rxdata(rxdata.hex())
        else:
            self.write_debug("cold_reboot_req send error")

    def cmd_poweroff_time_req(self):
        self.write_debug("poweroff_time_req")
        # generate power off time parameters
        pf_data = bytearray()
        pf_data.append(0x05)  # power off time command
        self.inputvalue = eval("0x"+ self.entry_poweroff_time.get())
        self.poweroff_time = self.inputvalue
        pf_data.append(self.poweroff_time)

        txresult, txdata = self.bt_communication.send(pf_data)

        if txresult:
            self.write_txdata(txdata.hex())
            rx_result, rxdata = self.bt_communication.recv(15)
            self.write_rxdata(rxdata.hex())

            if self.poweroff_time == 0:
                print("Power Off time is 30 sec.")
            else:
                print("Power Off time is ", self.poweroff_time, " min.")

        else:
            self.write_debug("poweroff_time_req send error")

    def cmd_heartbeat_period_req(self):
        self.write_debug("heartbeat_period_req")
        # generate heartbeat period parameters
        hb_data = bytearray()
        hb_data.append(0x06)        # heartbeat period command
        self.inputvalue = eval("0x"+self.entry_heartbeat_period.get())
        self.heartbeat_period = self.inputvalue
        hb_data.append(self.heartbeat_period)

        txresult, txdata = self.bt_communication.send(hb_data)

        if txresult:
            self.write_txdata(txdata.hex())
            rx_result, rxdata = self.bt_communication.recv(15)
            self.write_rxdata(rxdata.hex())

            print("New heartbeat period = ", self.heartbeat_period+1, " min.")
        else:
            self.write_debug("heartbeat_period_req send error")

    def cmd_power_button_req(self):
        self.write_debug("power_button_req")

        txresult, txdata = self.bt_communication.send(CMD_POWER_BUTTON_REQ)

        if txresult:
            self.write_txdata(txdata.hex())
            rx_result, rxdata = self.bt_communication.recv(15)
            self.write_rxdata(rxdata.hex())
        else:
            self.write_debug("power_button_req send error")

    def cmd_reset_button_req(self):
        self.write_debug("reset_button_req")

        txresult, txdata = self.bt_communication.send(CMD_RESET_BUTTON_REQ)

        if txresult:
            self.write_txdata(txdata.hex())
            rx_result, rxdata = self.bt_communication.recv(15)
            self.write_rxdata(rxdata.hex())
        else:
            self.write_debug("reset_button_req send error")

    def cmd_temperature_req(self):
        self.write_debug("temperature_req")

        txresult, txdata = self.bt_communication.send(CMD_TEMPERATURE_REQ)

        if txresult:
            self.write_txdata(txdata.hex())
            rx_result, rxdata = self.bt_communication.recv(15)
            self.write_rxdata(rxdata.hex())
        else:
            self.write_debug("temperature_req send error")

    def cmd_nop(self):
        # print("nop")
        self.write_debug("nop")

        txresult, txdata = self.bt_communication.send(CMD_NOP)

        if txresult:
            self.write_txdata(txdata.hex())
            # rx_result, rxdata = self.bt_communication.recv(15)
            # self.write_rxdata(rxdata.hex())
        else:
            self.write_debug("nop send error")

    def quitprogram(self):
        self.write_debug("quit this program after close serial port")

        self.bt_communication.close()
        # just sleep before exit()
        time.sleep(1)

        sys.exit()

    def write_txdata(self, tx_message):
        # self.textBoxTx.configure(state='normal')
        self.textBoxTx.insert(tk.END, str(datetime.datetime.now()) + " " + tx_message + '\n')
        self.textBoxTx.see("end")
        # self.textBoxTx.configure(state='disabled')

    def write_rxdata(self, rx_message):
        # self.textBoxRx.configure(state='normal')
        self.textBoxRx.insert(tk.END, str(datetime.datetime.now()) + " " + rx_message + '\n')
        self.textBoxRx.see("end")
        # self.textBoxRx.configure(state='disabled')

    def write_debug(self, debug_message):
        # self.textBoxDebug.configure(state='normal')
        self.textBoxDebug.insert(tk.END, str(datetime.datetime.now()) + " " + debug_message + '\n')
        self.textBoxDebug.see("end")
        # self.textBoxDebug.configure(state='disabled')

    #
    # Convert number to BCD
    #
    def convert2bcd(self, num):
        num_bcd = int((0x10 * int(num / 10))) + int(num % 10)
        return num_bcd
