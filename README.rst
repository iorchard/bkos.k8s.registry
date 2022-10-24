bkos.k8s.registry
=====================

This is a pulumi program to set up a container registry on PBOS platform.

It is used by bkos.k8s which is the pulumi program to provision
a kubernetes cluster on PBOS platform.

pre-requisites
---------------

The make package should be installed.

On RHEL OS flavor::

    $ sudo dnf -y install make

On Debian OS flavor::

    $ sudo apt -y install make

Setup pulumi
-------------

Refer to https://www.pulumi.com/docs/get-started/install/ to install and
set up pulumi in your environment.

Install python packages.::

    $ pip -r requirements.txt

Run
----

Edit Makefile until the comment "Do Not Edit Below!!!".

* STACK: set the pulumi stack name
* private_network_name: your openstack private network name
* provider_network_name: your openstack provider network name
* dns_zone_name: your openstack default dns zone name

Create a stack.::

    $ make stack
    

Configure the stack.::

    $ make config
    pulumi stack select bkos.k8s.registry.dev
    pulumi config set 'private_network_name' 'private-net'
    pulumi config set 'provider_network_name' 'public-net'
    pulumi config set 'dns_zone_name' 'pbos.local'
    pulumi config set 'openstack:authUrl' 'http://192.168.20.50:5000/v3'
    pulumi config set --secret 'openstack:password'
    value: 
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

Run pulumi.::

    $ make up


