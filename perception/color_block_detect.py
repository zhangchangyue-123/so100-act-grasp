import os

import cv2
import numpy as np

# 打开1号端口的摄像头
cap = cv2.VideoCapture(int(os.environ.get("CAMERA_INDEX", "1")))

# 检查摄像头是否成功打开
if not cap.isOpened():
    print("无法打开摄像头")
    exit()

# 定义蓝色的HSV范围
blue_lower = np.array([100, 50, 50])
blue_upper = np.array([130, 255, 255])

# 定义黄色的HSV范围
yellow_lower = np.array([20, 50, 50])
yellow_upper = np.array([30, 255, 255])

print("按 'q' 键或ESC键退出程序")

while True:
    # 读取一帧画面
    ret, frame = cap.read()
    
    if not ret:
        print("无法接收画面（可能摄像头已断开）")
        break
    
    # 转换到HSV颜色空间
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # 创建蓝色掩码
    blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)
    # 创建黄色掩码
    yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)
    
    # 使用掩码提取蓝色积木块
    blue_result = cv2.bitwise_and(frame, frame, mask=blue_mask)
    # 使用掩码提取黄色积木块
    yellow_result = cv2.bitwise_and(frame, frame, mask=yellow_mask)
    
    # 显示原图
    cv2.imshow('Original', frame)
    # 显示蓝色积木块
    cv2.imshow('Blue Block', blue_result)
    # 显示黄色积木块
    cv2.imshow('Yellow Block', yellow_result)
    
    # 等待按键
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27:  # q键或ESC键
        break

# 释放摄像头并关闭窗口
cap.release()
cv2.destroyAllWindows()