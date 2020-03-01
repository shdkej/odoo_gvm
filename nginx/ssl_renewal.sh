#!/bin/sh
mv /home/gvm/docker/nginx/conf.d/default.conf /home/gvm/docker/nginx/conf.d/default.conf.backup
mv /home/gvm/docker/nginx/conf.d/default.conf2 /home/gvm/docker/nginx/conf.d/default.conf
docker restart docker_nginx_1
docker stop docker_nginx_1
sudo letsencrypt renew --quiet
mv /home/gvm/docker/nginx/conf.d/default.conf /home/gvm/docker/nginx/conf.d/default.conf2
mv /home/gvm/docker/nginx/conf.d/default.conf.backup /home/gvm/docker/nginx/conf.d/default.conf
docker restart docker_nginx_1
echo "RENEWAL COMPLETE"
