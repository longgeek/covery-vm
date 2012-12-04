#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os,re
import MySQLdb

#判断计算节点是否宕机,compute_down_list是宕机的计算节点列表
print '\n正在扫描宕机的计算节点,请等待...'
def select_compute_down_host():
    nova_service_list = os.popen("nova-manage service list 2> /dev/null").read().strip().split("\n")
    compute_down_list = []
    for compute_num in range(len(nova_service_list)):
        if len(re.findall(r"[(nova-compute),(nova-network)].*?(enabled).*?(XXX)",nova_service_list[compute_num])) == 0:
            continue
        else:
            compute_down_list.append(nova_service_list[compute_num].split()[1])
    #如果没有扫描到宕机的计算节点，退出程序
    if len(compute_down_list) == 0:
        print "\n没有宕机的计算节点,程序自动退出！\n"
        exit(0)
    else:
        compute_down_list = list(set(compute_down_list))
    return compute_down_list

def select_compute_down_host_instances(host='172.16.0.21', user='nova', passwd='nova', db='nova'):
    #连接数据库
    connection_mysql = MySQLdb.connect(host=host, user=user, passwd=passwd, db=db)#, charset='utf8')
    cursor = connection_mysql.cursor()
    instances_dict = {}	
    down_instances = []
    #查询宕机的计算节点上的实例
    print '\n扫描到宕机的计算节点,并扫描上面所运行的虚拟机\n'
    for hosts in select_compute_down_host():
        #sql_select = 'select hostname from instances where host=\''+hosts+'\' and vm_state=\'active\''
        sql_select = 'select id from instances where host=\''+hosts+'\' and vm_state=\'active\''
        cursor.execute(sql_select)
        instances_name = cursor.fetchall()
        if instances_name == ():
            pass
        else:
            instances_dict[hosts] = instances_name
            down_instances.append(instances_dict[hosts])
    if down_instances == []:
        print '\n宕机的计算节点上没有运行虚拟机\n'
        exit()
#select_compute_down_host_instances()
    #在DB中查询所有计算节点的service_id号
    sql = 'select service_id from compute_nodes'
    cursor.execute(sql)
    compute_hosts_id = cursor.fetchall()
    ##not_down_host_id = []
    not_down_host_id = {}
    #提取没有宕机的计算节点的id号
    print '\n正在计算需要恢复虚拟机所需要的资源空间..'
    for row in compute_hosts_id:
        for id in row:
            sql_select_hosts = 'select host from services where id='+str(id)+''
            cursor.execute(sql_select_hosts)
            a = cursor.fetchall()
            #up，下面的if是同一计算节点可能在compute_nodes中出现多次，可能services表中更新过记录或者删除计算节点并重新加入到计算集群中,而导致compute_nodes中的service_id和services中的id号不一致.
            if a == ():
                pass
            else:
                hosts = a[0][0]
            #hosts = cursor.fetchall()[0][0]
            #hosts = list(cursor.fetchall())[0][0]
                if hosts in select_compute_down_host():
                    pass
                else:
                    not_down_host_id[hosts] = int(id)
    if not_down_host_id == {}:
        print '###\n没有可用的计算节点\n###'
        exit()
    #通过compute_nodes表中的service_id号来查询计算节点剩余的资源
    hosts_resource = {}
    for host_id in not_down_host_id.values():
        sql_select_host_resource = 'select vcpus-vcpus_used, free_ram_mb from compute_nodes where service_id='+str(host_id)+';'
        cursor.execute(sql_select_host_resource)
        hosts_free_source = cursor.fetchall()[0]
        hosts_resource[host_id] = hosts_free_source
    #总可用vcpu和总ram数
    total_hosts_vcpus = reduce(lambda x,y: x+y, [r for r,z in hosts_resource.values()])
    total_hosts_ram = reduce(lambda x,y: x+y, [z for r,z in hosts_resource.values()]) 
    instances_resource = {}
    instances_id = {}
    instances_id_id = {}
    for i in range(len(down_instances)):
        for j in down_instances[i]:
            #sql_select_instance_resource = 'select vcpus, memory_mb from instances where hostname=\''+str(j[0])+'\' and vm_state=\'active\';'
            sql_select_instance_resource = 'select vcpus, memory_mb from instances where id=\''+str(j[0])+'\' and vm_state=\'active\';'
            cursor.execute(sql_select_instance_resource)
            instances_used_resource = cursor.fetchall()[0]
            instances_resource[j[0]] = instances_used_resource

            sql_select_instance_id = 'select hostname from instances where id=\''+str(j[0])+'\' and vm_state=\'active\';'
            cursor.execute(sql_select_instance_id)
            instances_id_all = cursor.fetchall()[0]
            instances_id[j[0]] = instances_id_all

            sql_select_instance_id_id = 'select id from instances where id=\''+str(j[0])+'\' and vm_state=\'active\';'
            cursor.execute(sql_select_instance_id_id)
            instances_id_id_all = cursor.fetchall()[0]
            instances_id_id[j[0]] = instances_id_id_all
    total_instances_vcpus = reduce(lambda x,y: x+y, [r for r,z in instances_resource.values()])
    total_instances_ram = reduce(lambda x,y: x+y, [z for r,z in instances_resource.values()])
    
    #判断所有可用计算节点的资源是否能承载需要恢复的所有虚拟机
    if total_instances_vcpus <= total_hosts_vcpus and total_instances_ram <= total_hosts_ram:
        print '\n所有的虚拟机可以恢复\n'
    else:
        print '\n计算节点无空闲资源，请插入新的计算节点！\n'
    	#print total_instances_vcpus ,total_hosts_vcpus, total_instances_ram, total_hosts_ram
        cursor.close()
        connection_mysql.commit()
        connection_mysql.close()
        exit()
    #过滤不合适的计算节点
    os.system("> /root/instance_info_list.txt")
    print '\n正在任务调度中...\n'
    for i in instances_resource:
        for j in hosts_resource:
            if instances_resource[i][0] < hosts_resource[j][0] and instances_resource[i][1] < hosts_resource[j][1]:
                a = hosts_resource[j][0] - instances_resource[i][0], hosts_resource[j][1] - instances_resource[i][1]
                hosts_resource[j] = a
                #过滤出虚拟机的ID号恢复在合适的计算节点上！
                instances_name = 'instance-' + '0' * (8 - len(hex(int(instances_id_id[i][0]))[2:])) + hex(int(instances_id_id[i][0]))[2:]
                sql_select_instance_fixed_id = 'select id from fixed_ips where instance_id=\''+str(instances_id_id[i][0])+'\';'
                cursor.execute(sql_select_instance_fixed_id)
                fixed_id = cursor.fetchall()
                for k in not_down_host_id.keys():
                    if not_down_host_id[k] == j:
                        j = k
                if fixed_id == ():
                    floating_address = ()
                else:
                    sql_select_instance_floating_address = 'select address from floating_ips where fixed_ip_id=\''+str(fixed_id[0][0])+'\';'
                    cursor.execute(sql_select_instance_floating_address)
                    floating_address = cursor.fetchall()
                if floating_address == ():
                    os.system("echo '"+str(instances_name)+" "+str(j)+" "+str(instances_id[i][0])+"' >> /root/instance_info_list.txt")
                    print 'Add '+str(instances_name)+' in /root/instance_info_list.txt'
                    #在db中更新需要恢复的vm所在的新计算节点
                    sql_update_instance_host = 'update instances set host=\''+str(j)+'\' where id=\''+str(instances_id_id[i][0])+'\';'
                    cursor.execute(sql_update_instance_host)
                    cursor.fetchall()
                    print 'Update db '+str(instances_name)+' in '+str(j)+''
                else:
                    floating_address = floating_address[0][0]
                    os.system("echo '"+str(instances_name)+" "+str(j)+" "+str(instances_id[i][0])+" "+str(floating_address)+"' >> /root/instance_info_list.txt")
                    print 'Add '+str(instances_name)+' in /root/instance_info_list.txt'
                    #在db中更新需要恢复的vm所在的新计算节点
                    sql_update_instance_host = 'update instances set host=\''+str(j)+'\' where id=\''+str(instances_id_id[i][0])+'\';'
                    cursor.execute(sql_update_instance_host)
                    sql_update_floating_host = 'update floating_ips set host=\''+str(j)+'\' where address=\''+str(floating_address)+'\' ;'
                    cursor.execute(sql_update_floating_host)
                    cursor.fetchall()

                for i in select_compute_down_host():
                    sql_select_services_host = 'select id from services where host=\''+str(i)+'\' and services.binary=\'nova-compute\';'
                    cursor.execute(sql_select_services_host)
                    id = cursor.fetchall()
                    if id == ():
                        pass
                    else:
                        sql_delete_compute_host = 'delete from compute_nodes where service_id='+str(id[0][0])+';'
                        cursor.execute(sql_delete_compute_host)
                        cursor.fetchall()
                    sql_delete_service_host = 'delete from services where host=\''+str(i)+'\';'
                    cursor.execute(sql_delete_service_host)
                    cursor.fetchall()
            	print '###已删除宕机的计算节点###'
                break
            else:
                print 'Big',i > j

    cursor.close()
    connection_mysql.commit()
    connection_mysql.close()
if __name__ == "__main__":
    select_compute_down_host_instances()
