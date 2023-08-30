# bt-11 ホスト側サンプル
Jetpack5.1.1 Python 3.8 にて試験をしています。
以下に各ファイルの説明をします。
- bt_id.txt は、本プログラム識別用ファイルであり、ユーザーが自由に内容を設定できます。
- BT-SerialCommunication.py はホスト側サンプルプログラム
- start_bt.service は自動起動用サービス起動ファイル
- start_bt.sh は自動起動用BT-SerialCommunication.py起動シェルスクリプト
- send_bt-logs.sh はlogファイル全てをmailで送るシェルスクリプト
- sendlog.py はlogファイル全てをmailで送るプログラム

## bt-11用ホスト側サンプルを実行するための設定
1. bt-11 ディレクトリーを /home/nvidia/に作成します。(user accountはnvidia）
2. 本bt-11_host_sampleのプログラムを全て /home/nvidia/bt-11 にコピーします。

### pipをインストールします
```
sudo apt install -y python3-pip
python3 -m pip install --upgrade pip 
```
### pythonライブラリ schedule と pyserial　をインストールします
```
python3 -m pip install schedule pyserial
```

### dialoutグループにnvidiaを追加します
```
id -a                           # dialoutにnvidiaが含まれていないことを確認
sudo gpasswd -a nvidia dialout  # dialoutにnvidia追加
reboot                          # 立ち上がってからdialoutにnvidiaを追加できたか確認する 
id -a　　　                      # dialoutに追加されていればOK
```

### BT-SerialCommunication.py が問題なく動作するか試験をします
```
cd /home/nvidia/bt-11
python3 BT-SerialCommunication.py
```

### 動作に問題なければ（エラー等無ければ）自動起動設定を行います
```
cd /home/nvidia/bt-11
chmod 777 ./start_bt.sh                    # 実行可にする
cp ./start_bt.service /etc/systemd/system
sudo systemctl enable start_bt.service　　　# サービスをenable
sudo systemctl start start_bt.service      # サービス開始
sudo systemctl status start_bt.service     # 動作を確認
reboot                                     # 自動起動を確認のため
sudo systemctl status start_bt.service　　　# 動作確認
```

### logファイルをgoogle mailで送出する （bt_id.txtも添付）
```
cd /home/nvidia/bt-11
chmod 777 send_bt-logs.sh
send_bt-logs.sh from_email_address from_email_app-password, to_email_address
```

### 以上
(2023/08/30)