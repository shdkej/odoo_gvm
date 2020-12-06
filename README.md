---
# Odoo GVM
Odoo build with docker compose
include postgres, nginx, nagios(monitoring)

## Quick start
```
git clone https://github.com/shdkej/odoo_gvm
docker-compose up
```


## To Cloud Instance
running github action to build ansible

```
git push origin master

# run github action with ansible
# ansible does install docker, running docker
```

## To Local Virtual Machine
```
cd infra
vagrant up

# check build
vagrant ssh
docker ps
```

## To-do
- [ ] non stop build
- [ ] fail recovery
