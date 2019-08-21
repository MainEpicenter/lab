# -*- coding: utf-8 -*-
#!/usr/bin/python3
# performs a simple device inquiry, followed by a remote name request of each
# discovered device
import os
import sys
import struct
import bluetooth._bluetooth as bluez
import bluetooth
import socket
import time
#import pexpect -> 이 module은 현재 쓸 계획 X
import subprocess
import glob

time.sleep(2) #처음에 실행하기전에 그 전 코드가 종료될 때까지 기다려주는 작업을 위해서 작성
reset_point=0 #많은 에러 발생시 오류 처리, 10번이 넘으면 에러로 다시 시작, restart함수


def printpacket(pkt):
    for c in pkt:
        sys.stdout.write("%02x " % struct.unpack("B",c)[0])
    print()


def read_inquiry_mode(sock):
    """returns the current mode, or -1 on failure"""
    # save current filter
    old_filter = sock.getsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, 14)

    # Setup socket filter to receive only events related to the
    # read_inquiry_mode command
    flt = bluez.hci_filter_new()
    opcode = bluez.cmd_opcode_pack(bluez.OGF_HOST_CTL,
            bluez.OCF_READ_INQUIRY_MODE)
    bluez.hci_filter_set_ptype(flt, bluez.HCI_EVENT_PKT)
    bluez.hci_filter_set_event(flt, bluez.EVT_CMD_COMPLETE);
    bluez.hci_filter_set_opcode(flt, opcode)
    sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, flt )

    # first read the current inquiry mode.
    bluez.hci_send_cmd(sock, bluez.OGF_HOST_CTL,
            bluez.OCF_READ_INQUIRY_MODE )

    pkt = sock.recv(255)

    status,mode = struct.unpack("xxxxxxBB", pkt)
    if status != 0: mode = -1

    # restore old filter
    sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, old_filter )
    return mode

def write_inquiry_mode(sock, mode):
    """returns 0 on success, -1 on failure"""
    # save current filter
    old_filter = sock.getsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, 14)

    # Setup socket filter to receive only events related to the
    # write_inquiry_mode command
    flt = bluez.hci_filter_new()
    opcode = bluez.cmd_opcode_pack(bluez.OGF_HOST_CTL,
            bluez.OCF_WRITE_INQUIRY_MODE)
    bluez.hci_filter_set_ptype(flt, bluez.HCI_EVENT_PKT)
    bluez.hci_filter_set_event(flt, bluez.EVT_CMD_COMPLETE);
    bluez.hci_filter_set_opcode(flt, opcode)
    sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, flt )

    # send the command!
    bluez.hci_send_cmd(sock, bluez.OGF_HOST_CTL,
            bluez.OCF_WRITE_INQUIRY_MODE, struct.pack("B", mode) )

    pkt = sock.recv(255)

    status = struct.unpack("xxxxxxB", pkt)[0]

    # restore old filter
    sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, old_filter )
    if status != 0: return -1
    return 0

def device_inquiry_with_with_rssi(sock,settime,node_name):
    # save current filter
    old_filter = sock.getsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, 14)

    # perform a device inquiry on bluetooth device #0
    # The inquiry should last 8 * 1.28 = 10.24 seconds
    # before the inquiry is performed, bluez should flush its cache of
    # previously discovered devices
    flt = bluez.hci_filter_new()
    bluez.hci_filter_all_events(flt)
    bluez.hci_filter_set_ptype(flt, bluez.HCI_EVENT_PKT)
    sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, flt )

    duration = 4
    max_responses = 255
    cmd_pkt = struct.pack("BBBBB", 0x33, 0x8b, 0x9e, duration, max_responses)
    bluez.hci_send_cmd(sock, bluez.OGF_LINK_CTL, bluez.OCF_INQUIRY, cmd_pkt)

    results = []

    done = False

    while not done:
        pkt = sock.recv(255)
        ptype, event, plen = struct.unpack("BBB", pkt[:3])
        if event == bluez.EVT_INQUIRY_RESULT_WITH_RSSI:
            pkt = pkt[3:]
            nrsp = bluetooth.get_byte(pkt[0])
            for i in range(nrsp):
                addr = bluez.ba2str( pkt[1+6*i:1+6*i+6] )
                rssi = bluetooth.byte_to_signed_int(
                        bluetooth.get_byte(pkt[1+13*nrsp+i]))
                results.append( ( addr, rssi ) )
                #print("[%s] RSSI: [%d]" % (addr, rssi))
                now_time=time.time() #timestamp를 만드는 시간기준
                timestamp=now_time-settime
                num=timestamp%1200
                if num>600:
                    os.system("sudo hciconfig hci0 piscan")

                if rssi>-70:
                    raspi=addr_confirm(addr)#어떤 라즈베리파이인지 알려준다.
                    data1="time: "+str(timestamp)+" "+str(raspi)+" RSSI: "+str(rssi)
                    data2=str(raspi)+" RSSI: "+str(rssi)

                    mat_data=str(raspi)+" "+str(rssi) #매트랩에 작성하기 위한 파일
                    send_data=str(node_name)+'%'+str(raspi)
                    if raspi is not False:
                        #text.write(mat_data+'\r\n')
                        time.sleep(0.2)
                        print(send_data)
                        #이렇게 해야 바로 전송하고 접속을 끊어서 다음 데이터가 잘 들어갈 수 있다.
                        sock_data=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                        if sock_data.connect_ex(('166.104.75.39',8585)) != 0:
                            global reset_point
                            reset_point=11#바로 종료하기 위한 코드 삽입
                            restart()
                        sock_data.send(send_data.encode())
                        sock_data.close()
        elif event == bluez.EVT_INQUIRY_COMPLETE:
            done = True
        elif event == bluez.EVT_CMD_STATUS:
            status, ncmd, opcode = struct.unpack("BBH", pkt[3:7])
            if status != 0:
                print("uh oh...")
                printpacket(pkt[3:7])
                done = True
        elif event == bluez.EVT_INQUIRY_RESULT:
            pkt = pkt[3:]
            nrsp = bluetooth.get_byte(pkt[0])
            for i in range(nrsp):
                addr = bluez.ba2str( pkt[1+6*i:1+6*i+6] )
                results.append( ( addr, -1 ) )
                print("[%s] (no RRSI)" % addr)
        else:
            print("unrecognized packet type 0x%02x" % ptype)
            restart()

        #print("event ", event) (event를 출력하는 것을 일단 없애기로)


    # restore old filter
    sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, old_filter )

    return results

dev_id = 0
try:
    sock = bluez.hci_open_dev(dev_id)
except:
    print("error accessing bluetooth device...")
    sys.exit(1)

try:
    mode = read_inquiry_mode(sock)
except Exception as e:
    print("error reading inquiry mode.  ")
    print("Are you sure this a bluetooth 1.2 device?")
    print(e)
    sys.exit(1)
print("current inquiry mode is %d" % mode)

if mode != 1:
    print("writing inquiry mode...")
    try:
        result = write_inquiry_mode(sock, 1)
    except Exception as e:
        print("error writing inquiry mode.  Are you sure you're root?")
        print(e)
        sys.exit(1)
    if result != 0:
        print("error while setting inquiry mode")
    print("result: %d" % result)


def addr_confirm(addr):
    addr_set=['B8:27:EB:48:DE:38', 'B8:27:EB:AA:2A:FD', 'B8:27:EB:A5:11:B8', 'B8:27:EB:96:5F:48', 'B8:27:EB:17:D9:C0', 'B8:27:EB:52:1B:57', 'B8:27:EB:32:AC:9D', 'B8:27:EB:61:96:25','B8:27:EB:B9:87:55','B8:27:EB:DB:FE:06','B8:27:EB:ED:D2:9A','B8:27:EB:99:54:56','B8:27:EB:B0:05:DD']
    #raspi_set=["0","1","2","3","4","5","6","7","8","9","10","11","12","13"]
    set_num=len(addr_set)
    run=False

    for i in range(0,set_num):
        if(addr_set[i]==str(addr)):
            result=str(i)
            run=True
    if run is False:
        result=False

    return result

def comfirm_hostname():
    myhost = os.uname()[1]
    host_order=int(myhost[1:])#노드의 숫자 1,2,3,4, 이런 숫자
    #host_list=['A0','A1','A2','A3','N1','N2','N3','N4'] #20개의 라즈베리파이에 Mac Address를 추가해라
    #그리고 arr[0][0]이 맨 처음 값이므로 노드 번호를 0번째부터 시작해야 맞는 것이다.
    #배열도 arr[0]가 먼저 시작이다.

    if myhost[0] == 'A':
        return host_order
    else:
        return host_order+3


def restart(): #에러가 반복되는 경우에 종료하고 다시 실행시킨다.
    global reset_point
    reset_point+=1
    if reset_point > 6:
        file_list=glob.glob("*.py")
        #subprocess.call(["python3",file_list[0]])
        os.system("sudo /usr/bin/python3 /home/pi/lab/hop_client.py")
        sys.exit(1)

if __name__ == "__main__":
    os.system("sudo hciconfig hci0 piscan")
    #name=input()
    #name=name+".txt"
    node_name=comfirm_hostname()
    #text=open(name,"w+")
    settime=time.time()


    while 1:
        device_inquiry_with_with_rssi(sock,settime,node_name)
        #check_time=time.time()
        #if check_time-settime>100:
            #reset_point=11
            #restart()
