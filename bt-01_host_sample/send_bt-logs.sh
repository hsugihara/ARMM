#!/bin/bash

# command format
# send_bt-logs.sh from_email_address from_email_app-password, to_email_address

timestamp=$(date +%Y%m%d-%H%M%S)
fileName="bt_log-${timestamp}"


echo "archiving device logs into a file..."
# cwd=$PWD
# cd /home/nvidia/bt-01

# shellcheck disable=SC2086
tar -zcvf $fileName.tar.gz BT-log BT-log.*

# cd $cwd
echo "archived into /home/nvidia/bt-01/$fileName.tar.gz"

echo "device logs collection completed!"

echo "send log file by email"

# set to_email
fr_email=$1
appPassword=$2
to_email=$3
# echo $to_email

python3 sendlog.py $fileName.tar.gz $fr_email $appPassword $to_email


echo "sent log file !"
echo "delete the log file archive (.tar.gz)"

rm $fileName.tar.gz

echo "deleted"

exit 0
