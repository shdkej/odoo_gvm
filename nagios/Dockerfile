FROM jasonrivers/nagios:latest

RUN apt-get update && apt-get -y upgrade
RUN apt-get install -y -qq python3 vim git
RUN wget https://bootstrap.pypa.io/ez_setup.py -O - | python
RUN easy_install pip
RUN pip install twx.botapi
RUN ln -sf /usr/share/zoneinfo/Asia/Seoul /etc/localtime
RUN wget -O /usr/local/bin/nagios_telegram.py https://raw.githubusercontent.com/pommi/telegram_nagios/master/telegram_nagios.py
RUN chmod 755 /usr/local/bin/nagios_telegram.py

RUN wget -O /usr/local/bin/check_docker https://raw.githubusercontent.com/timdaman/check_docker/master/check_docker/check_docker.py

#RUN wget -O /usr/local/bin/check_swarm https://raw.githubusercontent.com/timdaman/check_docker/master/check_swarm
#RUN wget -O /usr/local/bin/check_nginx.pl https://raw.githubusercontent.com/regilero/check_nginx_status/master/check_nginx_status.pl
RUN chmod a+rx /usr/local/bin/check_docker

COPY ./check_postgres /opt/nagios/libexec/check_postgres
RUN mv /usr/local/bin//check_docker/ /opt/nagios/libexec/check_docker
#COPY ./check_docker/check_docker/check_docker.py /opt/nagios/libexec/check_docker
#COPY ./check_docker/check_docker/check_swarm.py /opt/nagios/libexec/check_swarm

WORKDIR /opt/nagios/libexec
WORKDIR /opt/nagios/libexec/check_postgres
RUN apt-get install -y libxml-xpath-perl
#RUN perl Makefile.PL
#RUN make
#RUN env -i make test
#RUN make install
RUN apt-get update && apt-get install -y postgresql
ENV PERL5LIB=$PERL5LIB:/usr/lib/nagios/plugins

VOLUME /opt/nagios/etc/
EXPOSE 80
WORKDIR /opt/nagios/
