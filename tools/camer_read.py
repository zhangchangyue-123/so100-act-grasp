import os

import cv2

# 全局变量
roi = None
selecting_roi = False
start_point = None
current_point = None

# 鼠标回调函数
def mouse_callback(event, x, y, flags, param):
    global roi, selecting_roi, start_point, current_point
    
    if event == cv2.EVENT_LBUTTONDOWN:
        # 鼠标左键按下，开始选择ROI
        selecting_roi = True
        start_point = (x, y)
        roi = None
    elif event == cv2.EVENT_MOUSEMOVE:
        # 鼠标移动，更新当前点
        if selecting_roi:
            current_point = (x, y)
    elif event == cv2.EVENT_LBUTTONUP:
        # 鼠标左键释放，完成ROI选择
        if selecting_roi and start_point is not None:
            end_point = (x, y)
            # 确保ROI的坐标是正确的顺序
            x1 = min(start_point[0], end_point[0])
            y1 = min(start_point[1], end_point[1])
            x2 = max(start_point[0], end_point[0])
            y2 = max(start_point[1], end_point[1])
            
            # 确保ROI有实际大小
            if x2 - x1 > 10 and y2 - y1 > 10:
                roi = (x1, y1, x2, y2)
            selecting_roi = False
            start_point = None
            current_point = None

# 打开1号端口的摄像头
cap = cv2.VideoCapture(int(os.environ.get("CAMERA_INDEX", "1")))

# 检查摄像头是否成功打开
if not cap.isOpened():
    print("无法打开摄像头")
    exit()

# 设置鼠标回调
cv2.namedWindow('Camera')
cv2.setMouseCallback('Camera', mouse_callback)

print("使用说明：")
print("- 鼠标左键拖拽选择ROI区域")
print("- 按 'r' 键清除ROI")
print("- 按 'q' 键或ESC键退出程序")

while True:
    # 读取一帧画面
    ret, frame = cap.read()
    
    if not ret:
        print("无法接收画面（可能摄像头已断开）")
        break
    
    display_frame = frame.copy()
    
    # 如果已选择ROI，绘制ROI矩形和ROI区域
    if roi is not None:
        x1, y1, x2, y2 = roi
        # 绘制矩形框
        cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        # 提取并显示ROI区域
        roi_image = frame[y1:y2, x1:x2]
        cv2.imshow('ROI', roi_image)
    
    # 如果正在选择ROI，绘制实时预览矩形
    if selecting_roi and start_point is not None and current_point is not None:
        cv2.rectangle(display_frame, start_point, current_point, (0, 255, 0), 2)
    
    # 显示画面
    cv2.imshow('Camera', display_frame)
    
    # 等待按键
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27:  # q键或ESC键
        break
    elif key == ord('r'):  # r键清除ROI
        roi = None
        if cv2.getWindowProperty('ROI', cv2.WND_PROP_VISIBLE) >= 1:
            cv2.destroyWindow('ROI')

# 释放摄像头并关闭窗口
cap.release()
cv2.destroyAllWindows()