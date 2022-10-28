"""A Registry Instance Provisioning Pulumi Program"""
import os
import pathlib
import typing
import requests

import pulumi
import pulumi_openstack as openstack
import pulumi_command as command

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from jinja2 import Environment
from jinja2 import FileSystemLoader
from jinja2 import Template


def create_template(tmpl_file: str) -> Template:
    """render jinja2 template"""
    env = Environment(loader=FileSystemLoader("templates/"))
    tmpl = env.get_template(tmpl_file)
    return tmpl

homedir = pathlib.Path.home()
config = pulumi.Config()

cluster_name = config.get("cluster_name")
dns_zone_name = config.get("dns_zone_name")
registry_fqdn = f"{cluster_name}.{dns_zone_name}"

realm = f"{homedir}/.bkos/{cluster_name}"
os.makedirs(name=realm, mode=0o700, exist_ok=True)

private_file = f"{realm}/id_rsa"
public_file = f"{private_file}" + ".pub"
if not (os.path.isfile(private_file) and os.path.isfile(public_file)):
    key = rsa.generate_private_key(
        backend=default_backend(), public_exponent=65537, key_size=2048
    )
    private_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    public_key = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
        )
        .decode("utf-8")
    )
    with open(file=private_file, mode="w", encoding="ascii") as f:
        f.write(private_key)
        os.chmod(path=private_file, mode=0o600)
    with open(file=public_file, mode="w", encoding="ascii") as f:
        f.write(public_key)
        os.chmod(path=public_file, mode=0o644)
else:
    with open(file=private_file, mode="r", encoding="ascii") as f:
        private_key = f.read()
    with open(file=public_file, mode="r", encoding="ascii") as f:
        public_key = f.read()

# create a key pair
keypair = openstack.compute.keypair.Keypair(
    "keypair",
    name=f"{cluster_name}_key",
    public_key=public_key,
)

# create an image
o_img = config.require_object("image")
IMAGE_URL = f"{o_img['url']}"
IMAGE_FILE = f"{o_img['file']}"
IMAGE_NAME = f"{o_img['name']}"
IMAGE_OS_VERSION = f"{o_img['os_version']}"
image_url = f"{IMAGE_URL}/{IMAGE_FILE}"
if not os.path.isfile(IMAGE_FILE):
    response = requests.get(image_url)
    with open(f"{IMAGE_FILE}", "wb") as buffered_stream:
        binary_io: typing.BinaryIO = buffered_stream
        binary_io.write(response.content)
image = openstack.images.Image(
    "image",
    name=IMAGE_NAME,
    container_format="bare",
    disk_format="qcow2",
    local_file_path=IMAGE_FILE,
    properties={
        "hw_disk_bus": "scsi",
        "hw_scsi_model": "virtio-scsi",
        "os_type": "linux",
        "os_distro": "debian",
        "os_admin_user": "debian",
        "os_version": f"{IMAGE_OS_VERSION}",
    },
)

# create a flavor
o_flavor = config.require_object("flavor")
flavor = openstack.compute.Flavor(
    "flavor",
    name=f"{cluster_name}-flavor",
    vcpus=o_flavor.get("vcpus"),
    ram=o_flavor.get("ram") * 1024,
    disk=o_flavor.get("disk"),
    is_public=True,
)

# create a security group and rules
sg = openstack.networking.SecGroup(
    "sg",
    name=f"{cluster_name}-sg",
    description=f"Security Group for {cluster_name}",
)
sg_icmp = openstack.networking.SecGroupRule(
    "sg_icmp",
    direction="ingress",
    ethertype="IPv4",
    protocol="icmp",
    remote_ip_prefix="0.0.0.0/0",
    description="Allow incoming icmp",
    security_group_id=sg.id,
)
sg_tcp_ssh = openstack.networking.SecGroupRule(
    "sg_tcp_ssh",
    direction="ingress",
    ethertype="IPv4",
    protocol="tcp",
    port_range_min=22,
    port_range_max=22,
    remote_ip_prefix="0.0.0.0/0",
    description="Allow incoming ssh service",
    security_group_id=sg.id,
)
sg_tcp_registry = openstack.networking.SecGroupRule(
    "sg_tcp_registry",
    direction="ingress",
    ethertype="IPv4",
    protocol="tcp",
    port_range_min=5000,
    port_range_max=5000,
    remote_ip_prefix="0.0.0.0/0",
    description="Allow incoming registry service",
    security_group_id=sg.id,
)
sg_tcp_etcd_discovery = openstack.networking.SecGroupRule(
    "sg_tcp_etcd_discovery",
    direction="ingress",
    ethertype="IPv4",
    protocol="tcp",
    port_range_min=8087,
    port_range_max=8087,
    remote_ip_prefix="0.0.0.0/0",
    description="Allow incoming etcd discovery service",
    security_group_id=sg.id,
)
registry_fip = openstack.networking.FloatingIp(
    "registry_fip", pool=config.get("provider_network_name")
)
push_images_tmpl = command.local.Command(
    "push_images_tmpl",
    create=pulumi.Output.concat(
        "echo '",
        pulumi.Output.all(registry_fqdn=registry_fqdn,).apply(
            lambda v: create_template("push_images.sh.j2").render(
                registry_fqdn=v["registry_fqdn"],
            )
        ),
        "'",
    ),
    opts=pulumi.ResourceOptions(depends_on=[registry_fip]),
)
post_run_tmpl = command.local.Command(
    "post_run_tmpl",
    create=pulumi.Output.concat(
        "echo '",
        pulumi.Output.all(
            registry_fip_address=registry_fip.address,
            registry_fqdn=registry_fqdn,
        ).apply(
            lambda v: create_template("post_run.sh.j2").render(
                registry_fip_address=v["registry_fip_address"],
                registry_fqdn=v["registry_fqdn"],
            )
        ),
        "'",
    ),
    opts=pulumi.ResourceOptions(depends_on=[registry_fip]),
)
etchosts_tmpl = command.local.Command(
    "etchosts_tmpl",
    create=pulumi.Output.concat(
        "echo '",
        pulumi.Output.all(
            registry_fip_address=registry_fip.address,
            cluster_name=cluster_name,
            registry_fqdn=registry_fqdn,
        ).apply(
            lambda v: create_template("etchosts.j2").render(
                registry_fip_address=v["registry_fip_address"],
                cluster_name=v["cluster_name"],
                registry_fqdn=v["registry_fqdn"],
            )
        ),
        "'",
    ),
    opts=pulumi.ResourceOptions(depends_on=[registry_fip]),
)
etcd_discovery_conf_tmpl = command.local.Command(
    "etcd_discovery_conf_tmpl",
    create=pulumi.Output.concat(
        "echo '",
        pulumi.Output.all(
            cluster_name=cluster_name,
            dns_zone_name=dns_zone_name,
        ).apply(
            lambda v: create_template("etcd_discovery_conf.j2").render(
                cluster_name=v["cluster_name"],
                dns_zone_name=v["dns_zone_name"],
            )
        ),
        "'",
    ),
    opts=pulumi.ResourceOptions(depends_on=[registry_fip]),
)
userdata_tmpl = command.local.Command(
    "userdata_tmpl",
    create=pulumi.Output.concat(
        "echo '",
        pulumi.Output.all(
            public_key=public_key,
            post_run=post_run_tmpl.stdout,
            push_images=push_images_tmpl.stdout,
            etcd_discovery_conf=etcd_discovery_conf_tmpl.stdout,
            etchosts=etchosts_tmpl.stdout,
        ).apply(
            lambda v: create_template("userdata.j2").render(
                public_key=v["public_key"],
                post_run=v["post_run"],
                push_images=v["push_images"],
                etcd_discovery_conf=v["etcd_discovery_conf"],
                etchosts=v["etchosts"],
            )
        ),
        "'",
    ),
    opts=pulumi.ResourceOptions(
        depends_on=[post_run_tmpl, push_images_tmpl, etchosts_tmpl]
    ),
)
# create an instance
registry_instance = openstack.compute.Instance(
    "registry",
    name="registry",
    flavor_id=flavor.id,
    key_pair=keypair.id,
    security_groups=[sg.name],
    user_data=userdata_tmpl.stdout,
    block_devices=[
        openstack.compute.InstanceBlockDeviceArgs(
            source_type="image",
            destination_type="volume",
            delete_on_termination=True,
            volume_size=o_flavor.get("disk"),
            uuid=image.id,
        )
    ],
    networks=[
        openstack.compute.InstanceNetworkArgs(
            name=config.get("private_network_name")
        ),
    ],
    opts=pulumi.ResourceOptions(depends_on=[userdata_tmpl]),
)

registry_fip_assoc = openstack.compute.FloatingIpAssociate(
    "registry_fip_assoc",
    fixed_ip=registry_instance.networks[0].fixed_ip_v4,
    floating_ip=registry_fip.address,
    instance_id=registry_instance.id,
)
# create registry recordset
zone = openstack.dns.get_dns_zone(name=f"{dns_zone_name}.")
rs = openstack.dns.RecordSet(
    "registry_dns_record",
    name=f"{cluster_name}.{dns_zone_name}.",
    records=[registry_fip.address],
    ttl=3600,
    type="A",
    zone_id=zone.id,
    opts=pulumi.ResourceOptions(depends_on=[registry_fip_assoc]),
)
# wait until registry ssh port is open
wait_sleep = command.local.Command(
    "wait_sleep",
    create=f"""while true;do
        echo 2>/dev/null > /dev/tcp/{registry_fqdn}/22 && break || sleep 5;
      done; sleep 120""",
    interpreter=["/bin/bash", "-c"],
    opts=pulumi.ResourceOptions(depends_on=[registry_fip_assoc]),
)
registry_ready = command.remote.Command(
    "registry_ready",
    connection=command.remote.ConnectionArgs(
        host=registry_fip.address,
        port=22,
        user="clex",
        private_key=private_key,
    ),
    create="while true;do [ -f $HOME/.i_am_ready ] && exit 0 || sleep 5;done",
    opts=pulumi.ResourceOptions(depends_on=[wait_sleep]),
)

pulumi.export("image_id", image.id)
pulumi.export("image_name", image.name)
pulumi.export("image_size", image.size_bytes)
pulumi.export("image_status", image.status)
pulumi.export("registry_fip_address", registry_fip.address)
