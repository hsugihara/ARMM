#!/bin/bash

# setup Edge AI Box to run a host sample program
# Execute at home directory

# install pip
sudo apt install -y python3-pip
python3 -m pip install --upgrade pip

#install schedule & pyserial
python3 -m pip install schedule pyserial

# add nvidia to dialout group
sudo gpasswd -a nvidia dialout
reboot
