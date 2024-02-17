#!/bin/bash

# setup host sample program as a service
# execute at bt-11 directory

# disable nvgetty.service (maybe not active but just for secure)
sudo systemctl disable nvgetty.service

# setup service
sudo cp start_bt.service /etc/systemd/system
sudo systemctl enable start_bt.service
sudo systemctl start start_bt.service

# confirm service is running
sudo systemctl status start_bt.service
