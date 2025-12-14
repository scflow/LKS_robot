import serial
import time
import struct

# --- 配置 (完全照搬原始 Demo) ---
MMWR_PORT = "/dev/ttyTHS1"
MMWR_BAUD_RATE = 115200

# 限制范围
MIN_DUTY = 0.0
MAX_DUTY = 0.2
MIN_POSITION = 800
MAX_POSITION = 2200

def clamp(val, lo, hi):
    return lo if val < lo else hi if val > hi else val

# 1. 原始 Demo 的数据处理逻辑
def motor_data_deal(motor_value):
    # 强制当作占空比处理 (float)
    motor_value = float(motor_value)
    # 限幅
    motor_value = clamp(motor_value, MIN_DUTY, MAX_DUTY)
    # 转换规则: 0.09 -> 9
    motor_int = int(motor_value * 100)
    return motor_int.to_bytes(2, byteorder='little')

def scs_data_deal(scs_steering):
    scs_steering = int(scs_steering)
    steering_input = clamp(scs_steering, MIN_POSITION, MAX_POSITION)
    return steering_input.to_bytes(2, byteorder='little')

# 2. 原始 Demo 的发送逻辑
def send_data(uart, motor_val, servo_val):
    protocol_header = b'\xFF'
    protocol_ender = b'\xFE'
    
    # 符号位处理
    if motor_val < 0:
        motor_val = -motor_val
        motor_data_pandn = b'\x01'
    else:
        motor_data_pandn = b'\x00'
        
    motor_input = motor_data_deal(motor_val)
    steering_input = scs_data_deal(servo_val)
    
    # 模式和灯光 (默认关闭/Ackerman)
    scs_mode = b'\x00'
    headlight = b'\x00'

    # 拼包
    data_packet = protocol_header + motor_data_pandn + motor_input + steering_input + scs_mode + headlight + protocol_ender
    
    uart.write(data_packet)

# --- 主程序 ---
def main():
    print(f"正在打开串口 {MMWR_PORT} ...")
    try:
        # 原始 Demo 使用 timeout=5
        uart = serial.Serial(MMWR_PORT, MMWR_BAUD_RATE, timeout=5)
    except Exception as e:
        print(f"串口打开失败: {e}")
        return

    print("串口已打开！")
    print("准备开始：前进了3秒 (速度 0.09)")
    time.sleep(1)

    try:
        start_time = time.time()
        while True:
            # 运行 3 秒
            if time.time() - start_time < 3:
                speed = 0.09  # 原始 Demo 的默认速度
                servo = 1500  # 回中
                print(f"\r正在发送 -> 速度: {speed}, 舵机: {servo}", end="")
            else:
                print("\n时间到，停车！")
                speed = 0.0
                servo = 1500
                send_data(uart, speed, servo)
                break
            
            # 发送数据
            send_data(uart, speed, servo)
            
            # 【关键】模拟 Demo 的接收逻辑 (清空缓冲区，防止阻塞)
            if uart.in_waiting > 0:
                uart.read(uart.in_waiting)

            # 【关键】原始 Demo 的频率控制
            time.sleep(0.002)

    except KeyboardInterrupt:
        print("\n强制停止...")
    finally:
        # 发送停止指令
        send_data(uart, 0.0, 1500)
        uart.close()
        print("串口已关闭")

if __name__ == "__main__":
    main()