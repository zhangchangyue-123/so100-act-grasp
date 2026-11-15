import cv2
import numpy as np
import os

# 蓝色积木块的HSV颜色范围（可根据实际情况调整）
BLUE_LOWER = np.array([100, 50, 50])
BLUE_UPPER = np.array([130, 255, 255])

# 最小检测面积（过滤噪声）
MIN_AREA = 200

# 参考积木块实际尺寸（cm）
REFERENCE_SIZE_CM = 3.0

# 全局变量
roi = None
selecting_roi = False
start_point = None
current_point = None
pixels_per_cm = None

def mouse_callback(event, x, y, flags, param):
    global roi, selecting_roi, start_point, current_point
    
    if event == cv2.EVENT_LBUTTONDOWN:
        selecting_roi = True
        start_point = (x, y)
        roi = None
    elif event == cv2.EVENT_MOUSEMOVE:
        if selecting_roi:
            current_point = (x, y)
    elif event == cv2.EVENT_LBUTTONUP:
        if selecting_roi and start_point is not None:
            end_point = (x, y)
            x1 = min(start_point[0], end_point[0])
            y1 = min(start_point[1], end_point[1])
            x2 = max(start_point[0], end_point[0])
            y2 = max(start_point[1], end_point[1])
            
            if x2 - x1 > 10 and y2 - y1 > 10:
                roi = (x1, y1, x2, y2)
                print(f"已框选区域: ({x1}, {y1}) 到 ({x2}, {y2}), 宽={x2-x1}px, 高={y2-y1}px")
            selecting_roi = False
            start_point = None
            current_point = None

def calibrate_pixels_per_cm(ref_image_path):
    global pixels_per_cm, roi, selecting_roi, start_point, current_point
    
    ref_img = cv2.imdecode(np.fromfile(ref_image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if ref_img is None:
        print(f"无法读取参考图片: {ref_image_path}")
        return False
    
    print("请在参考图片中框选 3cm×3cm 的积木块区域")
    print("框选完成后，按 'c' 键确认，或按 'q' 键取消")
    
    cv2.namedWindow('Select Reference Block')
    cv2.setMouseCallback('Select Reference Block', mouse_callback)
    
    while True:
        display = ref_img.copy()
        
        if roi is not None:
            x1, y1, x2, y2 = roi
            cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
            width_px = x2 - x1
            height_px = y2 - y1
            cv2.putText(display, f"Selected: {width_px}x{height_px}px", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(display, "Press 'c' to confirm", (x1, y2 + 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        if selecting_roi and start_point is not None and current_point is not None:
            cv2.rectangle(display, start_point, current_point, (0, 255, 0), 2)
        
        cv2.imshow('Select Reference Block', display)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            cv2.destroyAllWindows()
            return False
        elif key == ord('c') and roi is not None:
            x1, y1, x2, y2 = roi
            width_px = x2 - x1
            height_px = y2 - y1
            pixels_per_cm = (width_px + height_px) / (2 * REFERENCE_SIZE_CM)
            print(f"校准完成: {pixels_per_cm:.2f} 像素/cm")
            cv2.destroyAllWindows()
            return True

def detect_blue_blocks(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, BLUE_LOWER, BLUE_UPPER)
    
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel)
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours, mask

def main():
    global pixels_per_cm
    
    ref_image_path = os.environ.get("REF_BLOCK_IMAGE", "blue_block_capture.jpg")
    
    if os.path.exists(ref_image_path):
        print("找到参考图片，开始校准...")
        if not calibrate_pixels_per_cm(ref_image_path):
            print("校准取消，使用默认值")
            pixels_per_cm = 20.0
    else:
        print(f"未找到参考图片: {ref_image_path}")
        print("请输入参考积木块在图片中的像素宽度（或按回车使用默认值20像素/cm）:")
        try:
            user_input = input("像素宽度: ").strip()
            if user_input:
                pixels_per_cm = float(user_input) / REFERENCE_SIZE_CM
            else:
                pixels_per_cm = 20.0
        except ValueError:
            pixels_per_cm = 20.0
        print(f"使用比例: {pixels_per_cm:.2f} 像素/cm")
    
    cap = cv2.VideoCapture(int(os.environ.get("CAMERA_INDEX", "1")))
    
    if not cap.isOpened():
        print("无法打开摄像头")
        exit()
    
    print("\n使用说明：")
    print("- 按 'q' 键或ESC键退出程序")
    print("- 按 's' 键保存当前帧")
    print("- 按 'r' 键重新校准")
    
    while True:
        ret, frame = cap.read()
        
        if not ret:
            print("无法接收画面（可能摄像头已断开）")
            break
        
        contours, mask = detect_blue_blocks(frame)
        display_frame = frame.copy()
        
        detected_count = 0
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < MIN_AREA:
                continue
            
            cv2.drawContours(display_frame, [contour], -1, (0, 255, 0), 2)
            
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
            
            cx = x + w // 2
            cy = y + h // 2
            cv2.circle(display_frame, (cx, cy), 5, (0, 0, 255), -1)
            
            width_cm = w / pixels_per_cm
            height_cm = h / pixels_per_cm
            
            cv2.putText(display_frame, f"W: {width_cm:.1f}cm", (x, y - 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(display_frame, f"H: {height_cm:.1f}cm", (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(display_frame, f"({cx}, {cy})", (x, y + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
            
            detected_count += 1
        
        cv2.putText(display_frame, f"Blue blocks: {detected_count}  |  Scale: {pixels_per_cm:.1f} px/cm", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        cv2.imshow('Blue Block Detection', display_frame)
        cv2.imshow('Mask', mask)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break
        elif key == ord('s'):
            save_path = 'blue_block_result.jpg'
            cv2.imwrite(save_path, display_frame)
            print(f"已保存当前帧到 {save_path}")
        elif key == ord('r'):
            if os.path.exists(ref_image_path):
                pixels_per_cm = None
                if calibrate_pixels_per_cm(ref_image_path):
                    print("重新校准完成")
                else:
                    print("重新校准取消")
    
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()