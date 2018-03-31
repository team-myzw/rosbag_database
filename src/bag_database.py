#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Sun Dec 25 13:56:00 2016

@author: robocup
"""
import rosbag
import time
from multiprocessing import Process
import sys
import signal
import rospy
import os
import pickle
import numpy as np


from rosbag_database.srv import RosbagRecord, RosbagRecordResponse 
from rosbag_database.srv import RosbagStop, RosbagStopResponse
from rosbag_database.srv import RosbagPlay, RosbagPlayResponse



MAIN_MESSAGE="rosrun rosbag record -j --split --duration={0:s} {1:s} -O {2:s}.bag __name:={3:s}"

MAX_SPLIT=100
DEF_DUR="1m"
DEF_TOP="-a"
DEF_NAME="bagfile"
NAME = "record"
NODE_NAME = "bag_record"



BAG = os.getenv("BAG_FOLDA")
if BAG== None:
    BAG = os.getcwd() + "/bag"
    os.environ["BAG_FOLDA"] = BAG
try:
    os.mkdir(BAG)
except:
    pass

print BAG    

def check_time(rbt, st, et):
    s = int(st - rbt)
    if s <= 0:
        s = 0
    bag_time = "-s {0:d}".format(s)
    e = et - st
    if e > 0:
        bag_time += " -u {0:d}".format(e)
    return bag_time

def topic_check(topics, remap_topics):
    remap= []
    for t,r in zip(topics,remap_topics):
        mes = "{0:s}:=/{1:s}".format(t,r)
        remap.append(mes)
    message = " ".join(remap)
    return message

def bag_file(name, sc, ec):
    bag_name = name + "_{0:d}.bag"
    
    names = []
    for i in range(sc, ec+1):
        names.append(bag_name.format(i))
    bag_names = names
    return bag_names

def _check_file(name):
    count = 0
    file_name = name + "_{0:d}.bag"
    while not rospy.is_shutdown():
        flag = os.path.exists(file_name.format(count))
        if not flag:
            break
        count += 1
    return count

def _bag_time_check( rbt, st, et, dur=0):
    s = int(st - rbt)
    e = int(et - rbt)
    sc = 0
    ec = 0
    if not dur == 0:
        sc = s / dur
        ec = e / dur
        if (e%dur)==0:
            ec - 1
    return sc, ec            


class RosbagRecorder(object):
    def __init__(self):
        self.rb_administrator={}
        self.rb_record = {}
        rospy.Service("rosbag_record", RosbagRecord, self._start_record)
        rospy.Service("rosbag_record_stop", RosbagStop, self._stop_record)
        rospy.Service("rosbag_play", RosbagPlay, self._read_bag)
        self.rate= rospy.Rate(10)
    def _start_record(self, data):
##      リクエストの確認　空要素にデフォルト値を挿入
        if data.split_duration_str == "":
            dur = DEF_DUR
        else:
            dur = data.split_duration_str

        if data.record_topic_list == [""]:
            topic = DEF_TOP
        else:
            topic = " ".join(data.record_topic_list)
        
        if data.save_name == "":
            name = DEF_NAME
        else:
            name = data.save_name

        if data.node_name == "":
            node_name = NODE_NAME
        else:
            node_name = data.node_name


        name = BAG + "/" + name
        command = MAIN_MESSAGE.format(dur, topic, name, node_name)
        res = RosbagRecordResponse()
        rb = Process(target=os.system, args=[command])
        remind_data = [dur, topic, name, node_name]
        rb.start()
        
        res.record_time = rospy.Time.now()
        res.record_number = int(rb.pid)
        self.rb_administrator.update({int(rb.pid):remind_data})
        return res
    

    def _stop_record(self, data):
##      停止
        num = data.rosbag_number
        res = RosbagStopResponse()
        if not num in self.rb_administrator:
            rospy.logwarn("no number")
            return res            
        ps = Process(target=os.system, args=["rosnode kill /{0:s}".format(self.rb_administrator[num][-1])])
        ps.start()
##      残ったものの処理
        rospy.sleep(5)
        name = self.rb_administrator[num][-2]
        number = _check_file(name)
#        active_name =name + "_{0:d}.bag.active".format(number)
        self.rb_record.update({num:self.rb_administrator.pop(num).append(number)})
        res.count_number = number
        res.bag_name = name
        return res
        
    def _read_bag(self,data):
        start = data.start_time.secs
        count = data.count_number
        end = data.end_time.secs
        bag_time = data.rosbag_time.secs
        folda_path = data.folda_path        
        name = data.name
        topics = data.topics
        dur = data.duration
        res= RosbagPlayResponse()

        if folda_path == "":
            folda_path = BAG

        if name == "" or name =="/":
            rospy.logwarn("no name")
            return res

        if start == 0.0 and end == 0.0:
            start_count = 0
            end_count = count
        else:
            start_count, end_count = _bag_time_check(bag_time, start, end, dur)



        bag_name = folda_path + "/"+name
        bag_names = bag_file(bag_name, start_count, end_count)
        print bag_names
        topic_box = []
        
        t = topics
        
        for n in bag_names:
            print n
            bag = rosbag.Bag(n)
            if n == bag_names[0]:
                mes = bag.read_messages(t, start_time=rospy.Time(start))
            elif n == bag_names[-1]:
                mes = bag.read_messages(t, end_time=rospy.Time(end))
            else:
                mes = bag.read_messages(t)
            while not rospy.is_shutdown():
                try:
                    topic_box.append(mes.next()[1])
                except:
                    break
        self.old = topic_box
        if topic_box ==[]:
            rospy.logwarn("no data")
            return res
            
        module_code = topic_box[0].__module__
        module = sys.modules[module_code]
        module_path = module.__file__
        p_str = pickle.dumps(topic_box)
        res.pickle_message = p_str
        res.success = True
        res.module_code = module_code
        res.module_path = module_path

        return  res

        



    def run(self):
        while not rospy.is_shutdown():
            self.rate.sleep()            


if __name__ =="__main__":
    rospy.init_node("test")
    rb = RosbagRecorder()
    rb.run()