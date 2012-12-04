#!/bin/bash

instances_name=`cat /root/instance_info_list.txt | awk '{print $1}'`
instances_dir_path="/var/lib/nova/instances/"
for name in $instances_name
do
    instances_hostname=`cat /root/instance_info_list.txt | grep $name | awk '{print $3}'`
    filter_name=`cat $instances_dir_path$name/libvirt.xml | grep filter= | awk -F'"' '{print $2}'`
    fixed_ip=` cat $instances_dir_path$name/libvirt.xml | grep IP | awk -F '"' '{print $4}'`
    filter_uuid=`uuidgen $filter_name`
    instances_mac=`cat $instances_dir_path$name/libvirt.xml | grep mac | awk -F "'" '{print $2}'`
    instances_gateway=`ifconfig br100 | grep 'inet addr' | cut -d: -f2 | cut -d ' ' -f1`
    hex_adecimal=`echo '0x'\`echo $name | awk -F- {'print $2}'\``
    ten_adecimal=`echo $(($hex_adecimal))`
    instances_netmask=`ifconfig br100 | grep 'inet addr' | cut -d: -f4`
    if [ "$instances_netmask" = "255.255.255.0" ]; then
        network_bits='24'
        network=`echo $fixed_ip | cut -d. -f1-3`.0
    elif [ "$instances_netmask" = "255.255.0.0" ]; then
        network_bits='16'
        network=`echo $fixed_ip | cut -d. -f1-2`.0.0
    elif [ "$instances_netmask" = "255.0.0.0" ]; then
        network_bits='8'
        network=`echo $fixed_ip | cut -d. -f1-1`.0.0.0
    fi
	iptables -t filter -N nova-compute-inst-$ten_adecimal
	iptables -t filter -A nova-compute-inst-$ten_adecimal -m state --state INVALID -j DROP
	iptables -t filter -A nova-compute-inst-$ten_adecimal -m state --state RELATED,ESTABLISHED -j ACCEPT
	iptables -t filter -A nova-compute-inst-$ten_adecimal -j nova-compute-provider
	iptables -t filter -A nova-compute-inst-$ten_adecimal -s $instances_gateway/32 -p udp -m udp --sport 67 --dport 68 -j ACCEPT
	iptables -t filter -A nova-compute-inst-$ten_adecimal -s $network/$network_bits -j ACCEPT
	iptables -t filter -A nova-compute-inst-$ten_adecimal -p tcp -m tcp --dport 22 -j ACCEPT
	iptables -t filter -A nova-compute-inst-$ten_adecimal -p icmp -j ACCEPT
	iptables -t filter -A nova-compute-inst-$ten_adecimal -j nova-compute-sg-fallback
	iptables -t filter -A nova-compute-local -d $fixed_ip/32 -j nova-compute-inst-$ten_adecimal
    cat > /etc/libvirt/nwfilter/$filter_name.xml << _Longgeek_
<filter name='$filter_name' chain='root'>
  <uuid>$filter_uuid</uuid>
  <filterref filter='nova-base'/>
</filter>
_Longgeek_
    sed -i 's/"DHCPSERVER" value=.*$/"DHCPSERVER" value="'$instances_gateway'" \/>/g' $instances_dir_path$name/libvirt.xml
    echo -e "\n$instances_mac,$instances_hostname.novalocal,$fixed_ip" >> /var/lib/nova/networks/nova-br100.conf
    float_ip=`cat /root/instance_info_list.txt | grep $name | awk '{print $4}'`
    if [ "$float_ip" != '' ] ;then
        public_interface=`grep public_interface /etc/nova/nova.conf | awk -F= '{print $2}'`
        ip addr add $float_ip/32 dev $public_interface
        iptables -t nat -A nova-network-OUTPUT -d $float_ip/32 -j DNAT --to-destination $fixed_ip
        iptables -t nat -A nova-network-PREROUTING -d $float_ip/32 -j DNAT --to-destination $fixed_ip
        iptables -t nat -A nova-network-float-snat -s $fixed_ip/32 -j SNAT --to-source $float_ip
    fi
    /etc/init.d/libvirtd restart
    virsh define $instances_dir_path$name/libvirt.xml
    virsh start $name
done
chown nova:nova /var/lib/nova/networks/nova-br100.conf
/etc/init.d/openstack-nova-network reload
/etc/init.d/iptables save
