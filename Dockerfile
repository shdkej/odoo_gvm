#FROM odoo:10.0
FROM shdkej/odoo_container:latest

#RUN apt-get update

WORKDIR /usr/lib/python2.7/dist-packages/odoo/
COPY requirements.txt ./
COPY ./addons/ ./addons/

EXPOSE 8069
