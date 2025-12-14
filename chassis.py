import serial
import time
import threading
import struct

# ==============================================================================
# 1. 常量定义
# ==============================================================================

CHASSIS_PORT = "/dev/ttyTHS1"  
MMWR_BAUD_RATE = 115200

SCS_MODE_ACKERMAN = 0
SCS_MODE_4MATIC_DIFF = 1
SCS_MODE_4MATIC_SAME = 2

HEADLIGHT_OFF = 0
HEADLIGHT_ON = 1

CENTER_POSITION = 1500
MIN_POSITION = 800
MAX_POSITION = 2200

MIN_DUTY = 0.0
MAX_DUTY = 0.2

# 修复了这里的参数名错误：hi -> high
def clamp(value, low, high):
    """Clamp value between low/high."""
    return low if value < low else high if value > high else value


# ==============================================================================
# 2. 数据处理函数
# ==============================================================================

def motor_data_deal(motor_value):
    motor_value = float(motor_value)
    motor_value = clamp(motor_value, MIN_DUTY, MAX_DUTY)
    motor_int = int(motor_value * 100)
    return motor_int.to_bytes(2, byteorder='little')


def scs_data_deal(scs_steering):
    scs_steering = int(scs_steering)
    steering_input = clamp(scs_steering, MIN_POSITION, MAX_POSITION)
    return steering_input.to_bytes(2, byteorder='little')


def send_data_import(uart, motor_value, scs_steering, scs_mode, headlight):
    protocol_header = b'\xFF'
    protocol_ender = b'\xFE'
    
    if motor_value < 0:
        motor_value = -motor_value
        motor_data_pandn = b'\x01'
    else:
        motor_data_pandn = b'\x00'
        
    motor_input = motor_data_deal(motor_value)
    steering_input = scs_data_deal(scs_steering)

    if isinstance(scs_mode, int):
        scs_mode = bytes([scs_mode])
    
    if isinstance(headlight, int):
        headlight = bytes([headlight])

    data_packet = protocol_header + motor_data_pandn + motor_input + steering_input + scs_mode + headlight + protocol_ender
    
    try:
        if uart and uart.is_open:
            uart.write(data_packet)
    except Exception:
        pass


def receive_data(uart):
    if not uart or not uart.is_open:
        return
    try:
        while uart.in_waiting > 0:
            uart.read_all()
    except Exception:
        pass


# ==============================================================================
# 3. 线程封装器
# ==============================================================================

class Chassis:
    def __init__(self):
        self.uart = None
        self.last_error = ""
        
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # 共享控制变量
        self.target_motor = 0.0
        self.target_servo = CENTER_POSITION
        self.target_mode = SCS_MODE_ACKERMAN
        self.target_light = HEADLIGHT_OFF
        

    def open(self):
        if self.uart and self.uart.is_open:
            return True
        try:
            self.uart = serial.Serial(CHASSIS_PORT, MMWR_BAUD_RATE, timeout=0.1)
            self._start_loop()
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def is_open(self):
        return self.uart is not None and self.uart.is_open

    def close(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self.uart:
            self.uart.close()
            self.uart = None

    def send(self, motor, servo, mode, light):
        with self._lock:
            self.target_motor = motor
            self.target_servo = servo
            self.target_mode = mode
            self.target_light = light

    def _start_loop(self):
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._demo_loop_worker, daemon=True)
        self._thread.start()

    def _demo_loop_worker(self):
        # print(">>> 底盘后台线程启动")
        while self._running and self.uart and self.uart.is_open:
            with self._lock:
                m = self.target_motor
                s = self.target_servo
                md = self.target_mode
                lt = self.target_light
            
            send_data_import(self.uart, m, s, md, lt)
            receive_data(self.uart)
            time.sleep(0.002)


# 全局单例
chassis = Chassis()