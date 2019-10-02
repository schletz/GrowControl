---
title: Raspberry Pi und Arch Linux ARM
author: Michael Schletz
date: 17. Juli 2019
---

![Arch Linux ARM](https://upload.wikimedia.org/wikipedia/commons/thumb/e/eb/Arch_Linux_ARM_logo.svg/1280px-Arch_Linux_ARM_logo.svg.png)

# Vorbereitung der Hardware und der SD Karte
Damit die SD Karte für Arch Linux ARM vorbereitet werden kann, wird am PC ein Arch Livesystem
gebootet. Damit kann dann in Virtual Box die SD Karte beschrieben werden. Dafür wird von
[Arch Linux Downloads](https://www.archlinux.org/download/) die ISO Datei des aktuellen Release
geladen. Für das Anlegen der VM gibt es ein eigenes Profil mit dem Namen *Arch Linux (64bit)*. Eine
Festplatte muss nicht angelegt werden, da das System nur mit einer Ramdisk arbeitet. Bei der
Netzwerkeinstellung kann man Netzwerkbrücke wählen, damit das System so wie ein eigener Rechner im 
Heimnetzwerk erscheint.

Nach dem Starten stellen wir das System auf eine deutsche Tastatur um und erweitern das Dateisystem,
da 1 GB schon recht knapp ist.

```bash
loadkeys de-latin1
mount -o remount,size=1G /run/archiso/cowspace
```

## Arbeit in der VM
Mit `systemctl start sshd.service` wird der SSH Server gestartet. Zum Verbinden muss mit `passwd` noch
ein root Passwort gesetzt werden. Mit `ifconfig` kann die IP Adresse nachgesehen und sich mit PuTTY 
verbunden werden.

Auf der [Downloadseite von ARM Linux](https://archlinuxarm.org/about/downloads) wird der 
Downloadlink der entsprechendne Plattform kopiert. Für einen Raspberry Pi 3 gibt es eine ARMv8 
Version, der Raspberry Zero funktioniert mit der ARMv6 Version. In der VM (also über PuTTY) kann mit 
wget der Link geladen werden. In PuTTY fügt man mit der rechten Maustaste aus der Zwischenablage 
ein.

Nun wird die SHD Karte eingesteckt. Zu Beginn liest Windows die Karte ein. Im Menü der Virtual Box
VM kann unter *Geräte* - *USB* der Kartenleser zugewiesen werden. Es erscheint dann die Meldung in
Linux, dass das Gerät unter *sdb* (Nachkontrollieren!) zur Verfügung steht.

Die nachfolgenden Befehle sind von https://archlinuxarm.org/platforms/armv6/raspberry-pi als Skript
zusammengefasst. Der Dateiname bei bsdtar ist durch das heruntergeladene Archiv zu ersetzen.

```bash
cd
cat << EOF | fdisk /dev/sdb --wipe-partitions=always
  o
  n
  p
  1
   
  +100M
  t
  c
  n
  p
  2
   
   
  a
  1
  w
  q
EOF
fdisk /dev/sdb -l
mkfs.vfat /dev/sdb1
mkdir boot
mount /dev/sdb1 boot
mkfs.ext4 /dev/sdb2
mkdir root
mount /dev/sdb2 root
bsdtar -xpf ArchLinuxARM-rpi-3-latest.tar.gz  -C root
sync
mv root/boot/* boot
```

Damit beim ersten Start auch schon SSH zur Verfügung steht, wird das WLAN und das Netzwerk vorher
konfiguriert. Dabei sind die IP Adressen und der DNS Server natürlich anzupassen. Bei 
*wpa_passphrase* muss SSID und der WPA Key unter Anführungszeichen stehen.

```bash
cd
rm -f root/etc/systemd/network/*.network
cat << EOF >> root/etc/systemd/network/wlan0.network
[Match]
Name=wlan0

[Network]
Address=192.168.15.60/24
Gateway=192.168.15.1
RouteMetric=10
EOF
cat << EOF >> root/etc/systemd/network/eth0.network
[Match]
Name=eth0

[Network]
Address=192.168.15.61/24
Gateway=192.168.15.1
RouteMetric=20
EOF

# Vermutlich wird DNSSEC vom Router nicht unterstützt. Deswegen deaktivieren wir es, sonst gibt
# es Probleme mit pacman.
echo "DNS=192.168.15.1" >> root/etc/systemd/resolved.conf
echo "DNSSEC=no" >> root/etc/systemd/resolved.conf

# Die " müssen bleiben!
wpa_passphrase "(SSID)" "(Passwort)" > root/etc/wpa_supplicant/wpa_supplicant-wlan0.conf

# Den WPA Service automatisch starten, sodss er die Konfiguration von 
# /etc/systemd/network/wlan0.network liest.
ln -s \
   /usr/lib/systemd/system/wpa_supplicant@.service \
   root/etc/systemd/system/multi-user.target.wants/wpa_supplicant@wlan0.service
```

Am Ende werden die Partitionen ausgehängt und die SD Karte kann entfernt werden:
```bash
cd
umount boot root
```

# Konfiguration des Systems
## Initialisierung
Der Login mit dem Benutzer *alarm* hat das Passwort *alarm*. Mit *su* kann eine Root Shell geöffnet
werden. Dies ist für die nachfolgenden Befehle notwendig. Das root Passwort ist *root*. Zuerst wird 
*pacman* (der Paketmanager) initialisiert und der Benutzer *alarm* als sudo User aktiviert:
```bash
pacman-key --init
pacman-key --populate archlinuxarm
pacman -S base-devel                 # Developerpaket zum Kompilieren
pacman -Syu                          # Systemupgrade
echo "alarm   ALL=(ALL) ALL" >> /etc/sudoers
```

Damit die Zeit immer korrekt ist, hinterlegen wir die Zeitserver von der Bundesanstalt für 
Metrologie und synchronisieren die Zeit.
```bash
echo "NTP = bevtime1.metrologie.at bevtime2.metrologie.at time.metrologie.at" >> \
    /etc/systemd/timesyncd.conf
timedatectl set-ntp true
timedatectl status
```

## Firewall
Damit nicht unbeabsichtigt Ports offen gelassen werden, installieren wir mit *ufw* (Uncomplicated 
Firewall) ein Paket für die einfache Konfiguration von *iptables*. Danach wird Port 22 (SSH) und
445 (SMB) geöffnet.
```bash
pacman -S ufw 
ufw allow 22/tcp
ufw allow 445/tcp 
ufw enable
```

## Samba
Um von Windows aus auf das Homeverzeichnis zugreifen zu können, installieren wir *samba*. Da bei
der Installation keine Musterkonfiguration in */etc/samba/smb.conf* erstellt wird, laden wir
diese aus dem Repository von Samba. Danach wird die Arbeitsgruppe ersetzt und die Homeverzeichnisse
werden der Einfachheit halber durchsuchbar gemacht. Der neue Name der Arbeitsgruppe muss natürlich
angepasst werden.

Der User *alarm* wird dann als Benutzer hinzugefügt. Er kann ein eigenes Passwort erhalten. Dieses
wird dann beim Verbinden aus Windows verwendet.
```bash
pacman -S samba
curl \
    "https://git.samba.org/samba.git/?p=samba.git;a=blob_plain;f=examples/smb.conf.default;hb=HEAD" > \
    /etc/samba/smb.conf
sed -i 's/workgroup\s*=\s*MYGROUP/workgroup = (NAME)/gi' /etc/samba/smb.conf
sed -i 's/browseable\s*=\s*no/browseable = yes/gi' /etc/samba/smb.conf
smbpasswd -a alarm
systemctl start smb.service
systemctl enable smb.service
```

Unter Windows kann in der Eingabeaufforderung (cmd) das Netzlaufwerk permanent angelegt werden.
```
net use P: \\x.x.x.x\alarm (Passwort) /user:alarm /persistent:yes
net use \\x.x.x.x\alarm /savecred
```

## Swapdatei
Da besonders beim Kompilieren mehr Speicher als physisch vorhanden ist angefordert wird,
wird eine Swapdatei eingerichtet:
```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo "/swapfile       none    swap    defaults        0       0" >> /etc/fstab
```

## I²C
Soll der I²C Bus verwendet werden, müssen in der Bootkonfiguration die Hardware aktiviert werden.
Das Modul *i2c-dev* wird zur Liste der automatisch geladenen Module hinzugefügt. Danach ist ein
Neustart nötig. Mit `i2cdetect 1` kann danach geprüft werden, ob auf den Bus zugegriffen werden 
kann.

```bash
pacman -S i2c-tools          # Für i2cdetect 1
echo "device_tree_param=i2c1=on" >> /boot/config.txt
echo "i2c-dev" > /etc/modules-load.d/i2c-dev.conf
```

# Python 3
Zuerst wird die neueste Version von Python samt Paketmanager (*pip*) und den git Tools installiert.
```bash
pacman -S python python-pip git
```

Bei der Installation des originalen RPi.GPIO Modules gibt es ein Problem, dass die Plattform nicht
erkannt wird. Folgendes Modul läuft aber:

```bash
pip install git+https://github.com/TheNextLVL/RPi.GPIO.64.git
```

## Autostart
Im folgenden Beispiel wird angenommen, dass die Datei /home/alarm/monitor.py beim Starten ausgeführt
werden soll. Dabei muss im Python Script mit *#!/usr/bin/python3* der Interpreter angegeben werden.
Mit `chmod a+x monitor.py` wird die Datei ausführbar gemacht. Beachte, dass das Skript als root in 
einem anderen Ordner ausgeführt wird.

Wenn das Skript als root (testen mit `sudo ./monitor.py`) läuft, kann eine Servicedatei für 
*systemctl* erstellt werden. Für unser Monitorskript wählen wir als Name der Servicedatei 
*monitor.service*, dieser kann aber beliebig sein.

```bash
cat << EOF > /etc/systemd/system/monitor.service
[Unit]
Description=Steuerprogramm fuer die Growbox

[Service]
WorkingDirectory=/home/alarm/growmonitor/
ExecStart=python3 main.py cronjobs.growbox.json
Restart=on-abort
StandardOutput=null
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl start monitor.service
systemctl enable monitor.service
```

Durch systemctl enable wir dien Link auf das Skript erzeugt:
*/etc/systemd/system/multi-user.target.wants/monitor.service -> /etc/systemd/system/monitor.service*

# Webcam
Nach Anschluss der Logitech C920 Webcam erscheint in der Konsole (oder nach Aufruf von dmesg 
über SSH) die Meldung 
*input: HD Pro Webcam C920 as /devices/platform/soc/3f980000.usb/usb1/1-1/1-1.1/1-1.1.2/1-1.1.2:1.0/input/input18*
Das bedeutet, dass die Kamera erkannt und der Treiber geladen wurde. Möchte man periodisch 
Snapshots aufnehmen, gibt es im Paket *xawtv* mit dem Programm *v4ctl* die Möglichkeit das zu tun.

```bash
pacman -S xawtv 
v4lctl -c /dev/video0 snap jpeg full webcam.jpg
``` 
# Backup
https://wiki.archlinux.org/index.php/Full_system_backup_with_tar