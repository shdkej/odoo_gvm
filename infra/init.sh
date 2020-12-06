#/bin/bash
DOMAIN=shdkej.com
EMAIL=shdkej@gmail.com

sudo apt-get update
sudo apt-get install -y vim openssh-server docker.io git curl letsencrypt
sudo usermod -aG docker $USER

sudo curl -L https://github.com/docker/compose/releases/download/1.24.0/docker-compose-`uname -s`-`uname -m` -o /usr/bin/docker-compose
sudo chmod 755 /usr/bin/docker-compose
sudo chmod +x /usr/bin/docker-compose

sudo letsencrypt certonly --standalone -d $DOMAIN -m $EMAIL -n --agree-tos

git clone https://github.com/shdkej/odoo_gvm
cd odoo_gvm
docker-compose up -d

sudo crontab infra/cron
