FROM nginx:latest

RUN apt-get update && apt-get install -y vim

ADD conf.d /etc/nginx/conf.d
ADD nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
