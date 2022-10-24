SHELL := /bin/bash
STACK := bkos.k8s.registry.dev
ENDPOINT_IP := 192.168.20.50

stack:
	pulumi stack select $(STACK) 2>/dev/null || pulumi stack init $(STACK)

config:
	pulumi stack select $(STACK)
	pulumi config set --secret 'openstack:password'
	pulumi config set 'private_network_name' 'private-net'
	pulumi config set 'provider_network_name' 'public-net'
	pulumi config set 'dns_zone_name' 'pbos.local'

#########################################################
# Do Not Edit Below!!!                                  #
#########################################################

	pulumi config set 'openstack:authUrl' 'http://$(ENDPOINT_IP):5000/v3'
	pulumi config set 'openstack:projectDomainName' 'default'
	pulumi config set 'openstack:userDomainName' 'default'
	pulumi config set 'openstack:userName' 'admin'
	pulumi config set 'openstack:tenantName' 'admin'

	pulumi config set 'cluster_name' 'registry'

	pulumi config set --path 'image.url' \
		'https://cloud.debian.org/images/cloud/bullseye/latest/'
	pulumi config set --path 'image.file' 'debian-11-genericcloud-amd64.qcow2'
	pulumi config set --path 'image.name' 'registry'
	pulumi config set --path 'image.os_version' '11'

	pulumi config set --path 'flavor.vcpus' 4
	pulumi config set --path 'flavor.ram' 1
	pulumi config set --path 'flavor.disk' 50

up: check
	pulumi stack select $(STACK)
	pulumi up --yes --skip-preview

down: check
	pulumi stack select $(STACK)
	pulumi down --yes

refresh:
	pulumi stack select $(STACK)
	pulumi refresh --yes --skip-preview

typehint:
	mypy *.py

lint:
	pylint *.py

tidy:
	black -l 79 *.py

check: lint typehint

.PHONY: stack typehint lint tidy check up down refresh
