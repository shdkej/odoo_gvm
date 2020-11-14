#/bin/bash
sudo apt-get update
sudo apt-get install -y vim openssh-server docker.io git curl
sudo usermod -aG docker $USER

sudo curl -L https://github.com/docker/compose/releases/download/1.24.0/docker-compose-`uname -s`-`uname -m` -o /usr/bin/docker-compose
sudo chmod 755 /usr/bin/docker-compose
sudo chmod +x /usr/bin/docker-compose

git clone https://github.com/shdkej/odoo_gvm
cd odoo_gvm
docker-compose up -d

sudo crontab infra/cron

