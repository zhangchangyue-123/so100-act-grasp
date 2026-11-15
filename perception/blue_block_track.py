import os

import cv2
import numpy as np
from collections import deque

# 蓝色积木块的HSV颜色范围
BLUE_LOWER = np.array([104, 106, 24])
BLUE_UPPER = np.array([124, 255, 255])

# 轨迹最大长度
MAX_TRAJECTORY = 100

# 最小检测面积（过滤噪声）
MIN_AREA = 200

# 轨迹点队列
trajectory = deque(maxlen=MAX_TRAJECTORY)

# 打开摄像头
cap = cv2.VideoCapture(int(os.environ.get("CAMERA_INDEX", "1")))

if not cap.isOpened():
    print("无法打开摄像头")
    exit()

print("使用说明：")
print("- 按 'q' 键或ESC键退出程序")
print("- 按 'c' 键清除轨迹")
print("- 按 's' 键保存当前帧")

while True:
    ret, frame = cap.read()
    
    if not ret:
        print("无法接收画面（可能摄像头已断开）")
        break
    
    # 转换到HSV颜色空间
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # 创建蓝色掩码
    mask = cv2.inRange(hsv, BLUE_LOWER, BLUE_UPPER)
    
    # 形态学操作：去除噪声
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel)
    
    # 查找轮廓
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    display_frame = frame.copy()
    
    # 找到最大的蓝色区域（假设是目标积木块）
    if contours:
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)
        
        if area >= MIN_AREA:
            # 计算中心点
            M = cv2.moments(largest_contour)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                
                # 添加到轨迹
                trajectory.append((cx, cy))
                
                # 绘制轮廓
                cv2.drawContours(display_frame, [largest_contour], -1, (0, 255, 0), 2)
                
                # 绘制中心点
                cv2.circle(display_frame, (cx, cy), 8, (0, 0, 255), -1)
                
                # 显示坐标
                cv2.putText(display_frame, f"({cx}, {cy})", (cx + 10, cy - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    
    # 绘制轨迹
    for i in range(1, len(trajectory)):
        thickness = int(np.sqrt(i) * 1.5)
        color = (255, 0, 0)
        cv2.line(display_frame, trajectory[i-1], trajectory[i], color, thickness)
    
    # 显示轨迹起点和终点
    if len(trajectory) > 0:
        cv2.circle(display_frame, trajectory[0], 5, (0, 255, 0), -1)
        cv2.putText(display_frame, "Start", (trajectory[0][0] + 10, trajectory[0][1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    
    if len(trajectory) > 1:
        cv2.circle(display_frame, trajectory[-1], 5, (0, 0, 255), -1)
        cv2.putText(display_frame, "End", (trajectory[-1][0] + 10, trajectory[-1][1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    
    # 显示轨迹长度
    cv2.putText(display_frame, f"Trajectory: {len(trajectory)} points", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    # 显示原图和掩码
    cv2.imshow('Blue Block Tracking', display_frame)
    cv2.imshow('Mask', mask)
    
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27:
        break
    elif key == ord('c'):
        trajectory.clear()
        print("轨迹已清除")
    elif key == ord('s'):
        cv2.imwrite('blue_block_track_result.jpg', display_frame)
        print("已保存当前帧到 blue_block_track_result.jpg")

cap.release()
cv2.destroyAllWindows()