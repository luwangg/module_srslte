import logging
import socket
import subprocess
import threading
import select
import os 
import glob
import time
from threading import Thread
import sys
import signal
import subprocess
import serial
from array import array
import json
import queue
import subprocess
import psutil
import sys
from enum import Enum

import wishful_upis as upis
import wishful_framework as wishful_module

__author__ = "Justin Tallon"
__copyright__ = "Copyright (c) 2017, Software Radio Systems Ltd."
__version__ = "0.0.1"
__email__ = "Justin Tallon"


which_metric_dict = {'CFO' : 0 ,'SNR' : 1, 'RSRP' : 2, 'RSRQ' : 3, 'NOISE' : 4, 'CSI' : 5, 'NUM_RX': 6, 'PDSCH_MISS':7, 'PDCCH_MISS':8, 'MOD':9, 'TBS':10, 'RSSI':11,'CQI':12,'ENB_ID':13}
which_metric_dict_rev = {0 :'CFO'  ,1 :'SNR' , 2 :'RSRP' , 3 : 'RSRQ', 4 :'NOISE', 5 : 'CSI', 6 : 'N_FRAMES',7:'PDSCH_MISS', 8:'PDCCH_MISS', 9:'MOD',10:'TBS',11:'RSSI',12:'CQI',13:'ENB_ID'}

which_metric_dict_enb = {'NUM_TX':0}
which_metric_dict_enb = {0:'NUM_TX'}

which_parameter_dict = {'MCS':0, 'PRBS':1, 'FREQ':2, 'GAIN':3}
which_parameter_dict_rev = {0:'MCS', 1: 'PRBS',2:'FREQ',3:'GAIN'}

sss_algorithm_dict = {'SSS_DIFF':0, 'SSS_FULL': 1, 'SSS_PARTIAL_3' :2}

class RadioProgramState(Enum):
    IDLE = 1
    RUNNING = 2

class srslte_iface:
    def __init__(self,
                 ip='127.0.0.1',
                 ue_port_server = 4321,
                 ue_port_client = 2222,
                 eNb_port_server = 4321,
                 eNb_port_client = 2222,
                 directory = "/opt/srsLTE"
                 ):
        self.ip = ip
        self.ue_port_server = ue_port_server
        self.ue_port_client = ue_port_client
        self.eNb_port_server = eNb_port_server
        self.eNb_port_client = eNb_port_client
        self.threads = []
        self.killpill = threading.Event()
        self.metric_buffer = queue.Queue()
        self.config_buffer = queue.Queue()
        self.directory = directory
        self.is_ue = False

        self.srsradio_state = RadioProgramState.IDLE

        self.ue_filename = './build/lib/examples/pdsch_ue_wishful'
        self.ue_is_running = False
        self.ue_pid = -1

        self.eNb_filename = './build/lib/examples/pdsch_enodeb_wishful'
        self.eNb_is_running = False
        self.eNb_pid = -1

        #input parameters for the UE
        self.ue_frequency = 806000000
        self.ue_gain = 70
        self.ue_equalizer = 'mmse'
        self.ue_nof_antennas =1
        self.ue_max_turbo_decoder_its = 4
        self.ue_noise_est_alg = 0
        self.ue_sss_algorithm = sss_algorithm_dict['SSS_DIFF']
        self.ue_snr_ema_coeff = 0.1
        self.ue_cfo_tol = 50.0
        self.ue_rnti = 0xFFFF
        #input parameters for the eNb
        self.eNb_frequency = 2491000000
        self.eNb_rf_amp = 0.8
        self.eNb_gain  = 70
        self.eNb_no_of_frames = 100000
        self.eNb_no_of_prbs = 25
        self.eNb_which_prbs = 0xFFFF
        self.eNb_MCS = 1
        self.eNb_send_pdsch_data = 1
        self.eNb_net_port = 0
        self.eNb_rnti = 0x1234
        print("srs interface object has been initialized\n")

    def throw_signal_function(self,frame, event, arg):
        raise SigFinish()

    def interrupt_thread(self,thread):
        for thread_id, frame in sys._current_frames().items():
            if thread_id == thread.ident:  # Note: Python 2.6 onwards
                self.set_trace_for_frame_and_parents(frame, self.throw_signal_function)

    def set_trace_for_frame_and_parents(self, frame, trace_func):
        # Note: this only really works if there's a tracing function set in this
        # thread (i.e.: sys.settrace or threading.settrace must have set the
        # function before)
        while frame:
            if frame.f_trace is None:
                frame.f_trace = trace_func
            frame = frame.f_back
        del frame

    def do_nothing_trace_function(frame, event, arg):
        return None

    def set_ue_frequency(self,frequency):
        self.ue_frequency = frequency
        if self.ue_is_running:
            return self.send_command(True, self.ue_frequency, -4, 0, 1, which_parameter_dict['FREQ'])
        else:
            return self.ue_frequency

    def set_ue_gain(self, gain):
        self.ue_gain = gain
        if self.ue_is_running:
            return self.send_command(True, self.ue_gain, -4, 0, 1, which_parameter_dict['GAIN'])
        else:
            return self.ue_gain

    def set_ue_nof_antennas(self,nof_antennas):
        self.ue_nof_antennas = nof_antennas
        return self.ue_nof_antennas

    def set_ue_equalizer(self,equalizer_mode):
        self.ue_equalizer = equalizer_mode
        return self.ue_equalizer

    def set_ue_max_turbo_decoder_its(self,max_turbo_decoder_its):
        self.ue_max_turbo_decoder_its = max_turbo_decoder_its
        return self.ue_max_turbo_decoder_its

    def set_ue_noise_est_alg(self,noise_est_algorithm):
        self.ue_noise_est_alg = noise_est_algorithm
        return self.ue_noise_est_alg

    def set_ue_sss_algorithm(self,sss_algorithm):
        self.ue_sss_algorithm = sss_algorithm
        return self.ue_sss_algorithm

    def set_ue_snr_ema_coeff(self,snr_ema_coeff):
        self.ue_snr_ema_coeff = snr_ema_coeff
        return self.ue_snr_ema_coeff

    def set_ue_cfo_tol(self,cfo_tol):
        self.ue_cfo_tol = cfo_tol
        return self.ue_cfo_tol

    def set_ue_rnti(self,rnti):
        self.ue_rnti = rnti
        return self.ue_rnti

    def print_parameter_values(self):
        print ("UE frequency :", self.ue_frequency)
        print ("UE equalizer :", self.ue_equalizer)
        print ("max turbodecoder its :", self.ue_max_turbo_decoder_its)
        print ("noise estimation algorithm :", self.ue_noise_est_alg)
        print ("ue sss algorithm : ", self.ue_sss_algorithm)
        print ("SNR moving average coefficient ", self.ue_snr_ema_coeff)
        print ("CFO tolerence :", self.ue_cfo_tol)

    def get_ue_cfo(self):
        cfo = self.send_command(True,0,which_metric_dict['CFO'],1,0,0)
        return cfo

    def get_ue_snr(self):
        snr = self.send_command(True, 0, which_metric_dict['SNR'], 1, 0, 0)
        return snr

    def get_ue_rsrp(self):
        rsrp = self.send_command(True, 0, which_metric_dict['RSRP'], 1, 0, 0)
        return rsrp

    def get_ue_rsrq(self):
        rsrq = self.send_command(True, 0, which_metric_dict['RSRQ'], 1, 0, 0)
        return rsrq

    def get_ue_noise(self):
        noise = self.send_command(True, 0, which_metric_dict['NOISE'], 1, 0, 0)
        return noise

    def get_ue_pdsch_miss(self):
        noise = self.send_command(True, 0, which_metric_dict['PDSCH'], 1, 0, 0)
        return noise

    def get_ue_CSI(self):
        have_CSI = self.send_command(True, 0, which_metric_dict['CSI'], 1, 0, 0)
        return have_CSI

    def get_ue_nFrames(self):
        N_FRAMES = self.send_command(True, 0, which_metric_dict['N_FRAMES'], 1, 0, 0)
        return N_FRAMES

    def get_ue_pdsch_miss(self):
        pdsch_miss = self.send_command(True, 0, which_metric_dict['PDSCH_MISS'], 1, 0, 0)
        return pdsch_miss

    def get_ue_pdcch_miss(self):
        pdcch_miss = self.send_command(True, 0, which_metric_dict['PDCCH_MISS'], 1, 0, 0)
        return pdcch_miss

    def get_ue_mod(self):
        MCS = self.send_command(True, 0, which_metric_dict['MOD'], 1, 0, 0)
        return MCS

    def get_ue_tbs(self):
        TBS = self.send_command(True, 0, which_metric_dict['TBS'], 1, 0, 0)
        return TBS

    def get_ue_rssi(self):
        RSSI = self.send_command(True, 0, which_metric_dict['RSSI'], 1, 0, 0)
        return RSSI

    def get_ue_cqi(self):
        CQI = self.send_command(True, 0, which_metric_dict['CQI'], 1, 0, 0)
        return CQI

    def get_ue_enb_id(self):
        ENB_ID = self.send_command(True, 0, which_metric_dict['ENB_ID'], 1, 0, 0)
        return ENB_ID

    def start_ue(self):
        self.is_ue = True
        self.launch_response_reception_thread(True)
        time.sleep(5)
        os.chdir(self.directory)
        self.ue_filename = self.ue_filename + ' -f ' + str(self.ue_frequency)  + ' -y ' + str(self.ue_cfo_tol) + ' -E ' + str(self.ue_snr_ema_coeff)  + ' -X ' + str(self.ue_sss_algorithm)  + ' -N ' + str(self.ue_noise_est_alg)  + ' -T ' + str(self.ue_max_turbo_decoder_its)   + ' -e ' + self.ue_equalizer +  ' -r ' + str(self.ue_rnti)
        f_duece = self.ue_filename.split()
        process = subprocess.Popen(f_duece)
        pid1 = process.pid
        self.ue_is_running = True
        self.ue_pid = pid1
        self.ue_filename = './build/lib/examples/pdsch_ue_wishful'
        print("[agent] UE up and running\n")
        return pid1

    def stop_ue(self):
        os.kill(self.ue_pid, signal.SIGINT)
        print("killing srslte UE process/n")
        time.sleep(3)
        self.ue_is_running = False
        for t in self.threads:
            t.join
        print("[agent] UE successfully stopped")


    def get_enb_num_tx(self):
        NUM_TX = self.send_command(False, 0, which_metric_dict['NUM_TX'], 1, 0, 0)
        return NUM_TX

    def set_enb_frequency(self,frequency):
        self.eNb_frequency = frequency
        if self.eNb_is_running:
            return self.send_command(False, self.eNb_frequency, -4, 0, 1, which_parameter_dict['FREQ'])
        else:
            return self.eNb_frequency

    def set_enb_rf_amp(self,rf_amp):
        self.eNb_rf_amp = rf_amp
        return self.eNb_rf_amp

    def set_enb_net_port(self,net_port):
        self.eNb_net_port = net_port
        return net_port


    def set_enb_gain(self,gain):
        self.eNb_gain = gain
        if self.eNb_is_running:
            return self.send_command(False, self.eNb_gain, -4, 0, 1, which_parameter_dict['GAIN'])
        else:
            return self.eNb_gain

    def set_enb_no_of_frames(self,no_of_frames):
        self.eNb_no_of_frames = no_of_frames
        self.eNb_filename = self.eNb_filename + ' -n ' + str(self.eNb_no_of_frames) 
        return no_of_frames

 
    def set_enb_no_of_prbs(self,no_of_prbs):
        self.eNb_no_of_prbs = no_of_prbs
        return self.eNb_no_of_prbs

    def set_enb_which_prbs(self,which_prbs):
        self.eNb_which_prbs = which_prbs
        if self.eNb_is_running:
            return self.send_command(False, self.eNb_which_prbs , -4, 0, 1, which_parameter_dict['PRBS'])
        else:
            return self.eNb_which_prbs

    def set_enb_select_MCS(self,mcs):
        self.eNb_MCS = mcs
        if self.eNb_is_running:
            return self.send_command(False,self.eNb_MCS , -4, 0, 1, which_parameter_dict['MCS'])
        else:
            return self.eNb_MCS

    def set_enb_send_pdsch_data(self,send_pdsch_data):
        self.eNb_send_pdsch_data = send_pdsch_data
        return send_pdsch_data

    def set_enb_rnti(self,rnti):
        self.eNb_rnti = rnti
        return rnti

    
    def start_enb(self):
        self.is_ue = False
        self.launch_response_reception_thread(False)
        time.sleep(5)
        os.chdir(self.directory)
        self.eNb_filename = self.eNb_filename + ' -f ' + str(self.eNb_frequency) + ' -p ' + str(self.eNb_no_of_prbs)  + ' -w ' + str(self.eNb_which_prbs) + '-g ' + str(self.eNb_gain)  + ' -l ' + str(self.eNb_rf_amp) + ' -m ' + str(self.eNb_MCS) + ' -u ' + str(self.eNb_net_port) + ' -P  '   + str(self.eNb_send_pdsch_data) + ' -R ' +str(self.eNb_rnti)
        f_duece = self.eNb_filename.split()
        process = subprocess.Popen(f_duece)
        pid1 = process.pid
        self.eNb_pid = pid1
        self.eNb_filename = './build/lib/examples/pdsch_enodeb_wishful'
        self.eNb_is_running = True
        print("[agent] eNodeB is up and running\n")
        return pid1

    def stop_enb(self):
        os.kill(self.eNb_pid, signal.SIGINT)
        print("[agent] killing srslte eNodeB process with ctrl C/n")
        time.sleep(3)
        self.eNb_is_running = False
        for t in self.threads:
            t.join
        print("[agent] eNb successfully stopped")

    def send_command(self, is_ue, config_value, which_metric, wants_metric, make_config, which_config):
        try:
            if is_ue and self.ue_is_running == False:
                raise ValueError("the UE is not running")

            if not is_ue and not self.eNb_is_running:
                raise ValueError("the eNodeB is not running")
            send_stream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if is_ue:
                server = self.ue_port_server
            else:
                server = self.eNb_port_server
            send_stream.connect((self.ip, server))
            if wants_metric:
                print('[agent] : getting ', which_metric_dict_rev[which_metric] , '......')
            else:
                print('[agent] : setting ', which_parameter_dict_rev[which_config], '.....')
            j = json.dumps({'config_value':config_value, 'which_metric':which_metric,'wants_metric': wants_metric, 'make_config':make_config,'which_config':which_config})
            MESSAGE = j

            send_stream.send(MESSAGE.encode())
            send_stream.close()
            if wants_metric:
                metric = self.metric_buffer.get()
                print  (which_metric_dict_rev[which_metric] ,' is : ', metric)
                return metric
            else:
                reconfig = self.config_buffer.get()
                print("[agent] parameter : ", which_parameter_dict_rev[which_config], "has been reconfigured to ", reconfig)
                return reconfig

            time.sleep(10)

        except ValueError as msg:
            print (msg)

    def start_server(self, is_ue ,stop_event, timeout):

        rece_stream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print ('[agent] Starting  Server ... \n')

        if is_ue:
            client_port = self.ue_port_client
            print('[agent] UE server\n')
        else:
            client_port = self.eNb_port_client
            print('[agent] enb server\n')
        rece_stream.bind((self.ip, client_port))
        rece_stream.listen(1)

        conn, addr = rece_stream.accept()
        try:
            while 1:
                data = conn.recv(150)
                if not data:
                    conn.close()
                    print('[agent] Restarting server ...\n')
                    break
                else:
                    data = data.decode('utf-8')
                    if data == 'hello':
                        print("TEST of receive connection complete")
                    else:
                        res = json.loads(data)
                        if not res['is_reconfig']:
                            self.metric_buffer.put(res['metric_value'])
                        else:
                            self.config_buffer.put(res['reconfig_value'])

        except KeyboardInterrupt:
            print('closing python server\n')

    def launch_response_reception_thread(self, is_ue):

        rece_thread = threading.Thread(target=self.start_server,args=(is_ue,self.killpill,0))
        rece_thread.start()
        self.threads.append(rece_thread)

@wishful_module.build_module
class SrslteModule(wishful_module.AgentModule):
    def __init__(self):
        super(SrslteModule, self).__init__()
        self.srs = srslte_iface()
        self.srs.srsradio_state = RadioProgramState.IDLE

    @wishful_module.bind_function(upis.radio.set_parameters)
    def srslte_set_var(self,param_key_values_dict):
        for k, v in param_key_values_dict.items():
            if k == 'IS_UE':
                self.srs.is_ue = v
        if self.srs.is_ue:
            self.srslte_set_ue_var(param_key_values_dict)
        else:
            self.srslte_set_enb_var(param_key_values_dict)

    @wishful_module.bind_function(upis.radio.get_parameters)
    def srslte_get_var(self, param_key_list):
        if self.srs.is_ue:
            return self.srslte_get_ue_var(param_key_list)
        else:
            return self.srslte_get_enb_var(param_key_list)

    @wishful_module.bind_function(upis.radio.get_measurements)
    def srslte_get_measurements(self,measurement_key_list):
        out  = {}
        if self.srs.is_ue:
            for k in measurement_key_list:
                if k == 'CFO':
                    out = {'CFO': self.srs.get_ue_cfo()}
                elif k == 'SNR':
                    out = {'SNR': self.srs.get_ue_snr()}
                elif k == 'RSRP':
                    out = {'RSRP': self.srs.get_ue_rsrp()}
                elif k == 'RSRQ':
                    out = {'RSRQ': self.srs.get_ue_rsrq()}
                elif k == 'NOISE':
                    out = {'NOISE': self.srs.get_ue_noise()}
                elif k == 'CSI':
                    out = {'CSI': self.srs.get_ue_CSI()}
                elif k == 'N_FRAMES':
                    out = {'N_FRAMES': self.srs.get_ue_nFrames()}
                elif k == 'PDSCH_MISS':
                    out = {'PDSCH_MISS': self.srs.get_ue_pdsch_miss()}
                elif k == 'PDCCH_MISS':
                    out = {'PDCCH_MISS': self.srs.get_ue_pdcch_miss()}
                elif k == 'MOD':
                    out = {'MOD': self.srs.get_ue_mod()}
                elif k == 'TBS':
                    out = {'TBS': self.srs.get_ue_tbs()}
                elif k == 'RSSI':
                    out = {'RSSI': self.srs.get_ue_rssi()}
                elif k == 'CQI':
                    out = {'CQI': self.srs.get_ue_cqi()}
                elif k == 'ENB_ID':
                    out = {'ENB_ID': self.srs.get_ue_enb_id()}
                else:
                    print("invalid metric\n")
        else:
            for k in measurement_key_list:
                if k == 'NUM_TX':
                    out = {'NUM_TX': self.srs.get_enb_num_tx()}
                else:
                    print("invalid metric\n")

        return out

    @wishful_module.bind_function(upis.radio.activate_radio_program)
    def srslte_start_radio(self,name):
        if name == 'UE':
            self.srs.is_ue = True
            self.srs.start_ue()
        elif name == 'ENB':
            self.srs.is_ue = False
            self.srs.start_enb()
        else:
            print("invalid radio mode, choose either UE or ENB")

    @wishful_module.bind_function(upis.radio.get_running_radio_program)
    def srslte_is_running(self):
        if self.srs.eNb_is_running or self.srs.ue_is_running:
            return True
        else:
            return False


    @wishful_module.bind_function(upis.radio.deactivate_radio_program)
    def srslte_stop_radio(self,name):
        if self.srs.is_ue == True:
            self.srs.stop_ue()
        else:
            self.srs.stop_enb()



    def srslte_set_ue_var(self, param_key_values_dict):
        for k, v in param_key_values_dict.items():
            if k  == 'LTE_UE_DL_FREQ':
                self.srs.set_ue_frequency(v)
            elif k == 'LTE_UE_EQUALIZER_MODE':
                self.srs.set_ue_equalizer(v)
            elif k == 'LTE_UE_MAX_TURBO_ITS':
                self.srs.set_ue_max_turbo_decoder_its(v)
            elif k == 'LTE_NOISE_EST_ALG':
                self.srs.set_ue_noise_est_alg(v)
            elif k == 'LTE_UE_SSS_ALGORITHM':
                self.srs.set_ue_sss_algorithm(v)
            elif k == 'LTE_UE_SNR_EMA_COEFF':
                self.srs.set_ue_snr_ema_coeff(v)
            elif k == 'LTE_UE_CFO_TOL':
                self.srs.set_ue_cfo_tol(v)
            elif k == 'LTE_UE_RX_GAIN':
                self.srs.set_ue_gain(v)
            elif k == 'LTE_UE_N_RX_ANT':
                self.srs.set_ue_nof_antennas(v)
            elif k == 'LTE_RX_RNTI':
                self.srs.set_ue_rnti(v)
            else :
                print("invalid parameter\n")

    def srslte_set_enb_var(self, param_key_values_dict):
        print("param_key_values_dict",param_key_values_dict)
        for k, v in param_key_values_dict.items():
            if k == 'LTE_ENB_DL_FREQ':
                self.srs.set_enb_frequency(v)
            elif k == 'LTE_ENB_RF_AMP':
                self.srs.set_enb_rf_amp(v)
            elif k == 'LTE_ENB_TX_GAIN':
                self.srs.set_enb_gain(v)
            elif k == 'LTE_ENB_NO_OF_FRAMES':
                self.srs.set_enb_no_of_frames(v)
            elif k == 'LTE_ENB_DL_BW':
                if v == 20000000:
                    return_value = 100
                elif v == 15000000:
                    return_value = 75
                elif v == 10000000:
                    return_value = 50
                elif v == 5000000:
                    return_value = 25
                elif v == 2000000:
                    return_value = 6
                else:
                    print("invalid bandwidth\n")
                self.srs.set_enb_no_of_prbs(return_value)
            elif k == 'LTE_ENB_WHICH_PRBS':
                self.srs.set_enb_which_prbs(v)
            elif k == 'LTE_ENB_MCS':
                self.srs.set_enb_select_MCS(v)
            elif k == 'LTE_ENB_RNTI':
                self.srs.set_enb_rnti(v)
            else:
                print("invalid parameter\n")

    def srslte_get_ue_var(self, param_key_list):
        ret = {}
        for k in param_key_list:
            if k == 'LTE_UE_DL_FREQ':
                ret.update({'LTE_UE_DL_FREQ': self.srs.ue_frequency})
            elif k == 'LTE_UE_EQUALIZER_MODE':
                ret.update({'LTE_UE_EQUALIZER_MODE':self.srs.ue_equalizer})
            elif k == 'LTE_UE_MAX_TURBO_ITS':
                ret.update({'LTE_UE_MAX_TURBO_ITS':self.srs.ue_max_turbo_decoder_its})
            elif k == 'LTE_UE_NOISE_EST_ALG':
                ret.update({'LTE_UE_NOISE_EST_ALG':self.srs.ue_noise_est_alg})
            elif k == 'LTE_UE_SSS_ALGORITHM':
                ret.update({'LTE_UE_SSS_ALGORITHM':self.srs.ue_sss_algorithm})
            elif k == 'LTE_UE_SNR_EMA_COEFF':
                ret.update({'LTE_UE_SNR_EMA_COEFF':self.srs.ue_snr_ema_coeff})
            elif k == 'LTE_UE_CFO_TOL':
                ret.update({'LTE_UE_CFO_TOL':self.srs.ue_cfo_tol})
            elif k == 'LTE_UE_RX_GAIN':
                ret.update({'LTE_UE_RX_GAIN':self.srs.ue_gain})
            elif k == 'LTE_UE_NO_OF_ANTENNAS':
                ret.update({'LTE_UE_NO_OF_ANTENNAS':self.srs.ue_nof_antennas})
            elif k == 'LTE_UE_RX_RNTI':
                ret.update({'LTE_UE_RX_RNTI':self.srs.set_ue_rnti(v)})
            else:
                print("invalid parameter\n")
        return ret

    def srslte_get_enb_var(self, param_key_list):
        ret = {}	
        for k  in param_key_list:
            if k == 'LTE_ENB_DL_FREQ':
                ret.update({'LTE_ENB_DL_FREQ': self.srs.eNb_frequency})
            elif k == 'LTE_ENB_RF_AMP':
                ret.update({'LTE_ENB_RF_AMP':self.srs.eNb_rf_amp})
            elif k == 'LTE_ENB_TX_GAIN':
                ret.update({'LTE_ENB_TX_GAIN':self.srs.eNb_gain})
            elif k == 'LTE_ENB_NO_OF_FRAMES':
                ret.update({'LTE_ENB_NO_OF_FRAMES':self.srs.eNb_no_of_frames})
            elif k == 'LTE_ENB_DL_BW':
                if self.srs.eNb_no_of_prbs == 100:
                    return_value = 20000000
                elif self.srs.eNb_no_of_prbs == 75:
                    return_value = 15000000
                elif self.srs.eNb_no_of_prbs == 50:
                    return_value = 10000000
                elif self.srs.eNb_no_of_prbs == 25:
                    return_value = 5000000
                elif self.srs.eNb_no_of_prbs == 6:
                    return_value = 2000000
                ret.update({'LTE_ENB_DL_BW':return_value})
            elif k == 'LTE_ENB_WHICH_PRBS':
                ret.update({'LTE_ENB_WHICH_PRBS':self.srs.eNb_which_prbs})
            elif k == 'LTE_ENB_MCS':
                ret.update({'LTE_ENB_MCS': self.srs.eNb_MCS})
            elif k == 'LTE_ENB_NET_PORT':
                ret.update({'LTE_ENB_NET_PORT': self.srs.eNb_net_port})
            elif k == 'LTE_ENB_PDSCH_DATA':
                ret.update({'LTE_ENB_PDSCH_DATA': self.srs.eNb_send_pdsch_data})
            elif k == 'LTE_ENB_RNTI':
                ret.update({'LTE_ENB_RNTI': self.srs.eNb_rnti})
            else:
                print("invalid parameter\n")
        return ret







