import cv2
import numpy as np
import pyautogui

def pick_color_fixed():
    # 截取游戏区域
    screenshot = pyautogui.screenshot(region=(150, 330, 600, 880))
    img = np.array(screenshot)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    
    # 转为HSV
    hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # 创建窗口和滑块
    cv2.namedWindow('Color Picker')
    
    # 存储采样点
    sample_points = []
    
    # 定义鼠标回调函数
    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            # 获取点击位置的HSV值
            hsv_value = hsv_img[y, x]
            sample_points.append(hsv_value)
            print(f"添加采样点 #{len(sample_points)}: HSV = {hsv_value}")
            
            # 在图像上显示采样点
            cv2.circle(img, (x, y), 3, (0, 255, 0), -1)
            cv2.imshow('Color Picker', img)
            
            # 如果有足够多的采样点，计算更精确的范围
            if len(sample_points) >= 1:
                calculate_range()
    
    def calculate_range():
        """安全计算HSV范围，避免溢出"""
        if not sample_points:
            return
            
        # 转换为numpy数组
        points_array = np.array(sample_points)
        
        # 提取各通道的值并安全计算范围
        h_values = points_array[:, 0].astype(np.int32)  # 转为int32避免溢出
        s_values = points_array[:, 1].astype(np.int32)
        v_values = points_array[:, 2].astype(np.int32)
        
        # 检查H值是否跨越边界
        h_range = np.max(h_values) - np.min(h_values)
        h_crosses_boundary = h_range > 90 and len(h_values) > 2
        
        # 计算安全范围值
        if h_crosses_boundary:
            print("检测到H值可能跨越红色边界(0/180)!")
            # 特殊处理跨越边界的H值
            # 方法1: 简单方式 - 使用宽范围
            h_min = 0
            h_max = 179
            print(f"使用全H范围: [{h_min}, {h_max}]")
        else:
            # 正常计算H范围
            h_min = max(0, np.min(h_values) - 5)
            h_max = min(179, np.max(h_values) + 5)
        
        # 安全计算S和V范围
        s_min = max(0, np.min(s_values) - 15)
        s_max = min(255, np.max(s_values) + 15)
        v_min = max(0, np.min(v_values) - 15)
        v_max = min(255, np.max(v_values) + 15)
        
        print("\n推荐的HSV范围:")
        print(f"\"hsv_lower\": [{h_min}, {s_min}, {v_min}],")
        print(f"\"hsv_upper\": [{h_max}, {s_max}, {v_max}],")
        
        # 显示掩码预览
        show_mask_preview(h_min, h_max, s_min, s_max, v_min, v_max)
    
    def show_mask_preview(h_min, h_max, s_min, s_max, v_min, v_max):
        """显示掩码预览，标记检测到的区域"""
        
        # 创建掩码
        if h_min <= h_max:
            # 标准范围
            mask = cv2.inRange(hsv_img, 
                             np.array([h_min, s_min, v_min]), 
                             np.array([h_max, s_max, v_max]))
        else:
            # 处理H值跨越边界情况
            mask1 = cv2.inRange(hsv_img, 
                              np.array([h_min, s_min, v_min]), 
                              np.array([179, s_max, v_max]))
            mask2 = cv2.inRange(hsv_img, 
                              np.array([0, s_min, v_min]), 
                              np.array([h_max, s_max, v_max]))
            mask = cv2.bitwise_or(mask1, mask2)
        
        # 形态学操作 - 闭运算连接临近区域
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        
        # 找到连通区域
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
        
        # 创建结果图像
        result_img = img.copy()
        detected_count = 0
        
        # 处理每个连通区域
        for i in range(1, num_labels):  # 跳过背景(0)
            area = stats[i, cv2.CC_STAT_AREA]
            # 面积筛选 
            if 3000 <= area <= 100000:
                detected_count += 1
                x = stats[i, cv2.CC_STAT_LEFT]
                y = stats[i, cv2.CC_STAT_TOP]
                w = stats[i, cv2.CC_STAT_WIDTH]
                h = stats[i, cv2.CC_STAT_HEIGHT]
                
                # 绘制区域边框
                cv2.rectangle(result_img, (x, y), (x+w, y+h), (0, 255, 0), 2)
                # 显示区域ID
                cv2.putText(result_img, f"#{i}", (x+5, y+20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        # 显示结果
        cv2.imshow('Mask Preview', result_img)
        print(f"检测到 {detected_count} 个合适大小的区域")
    
    # 设置鼠标回调
    cv2.setMouseCallback('Color Picker', mouse_callback)
    
    # 显示操作说明
    print("使用说明:")
    print("1. 点击气泡上的多个位置进行采样")
    print("2. 程序会自动计算合适的HSV范围")
    print("3. 绿色方框表示检测到的区域")
    print("4. 按ESC键退出")
    print("\n【特别提示】如果气泡混合了红色和紫色，可能需要创建两个配置以处理H通道的边界问题")
    
    # 显示图像
    cv2.imshow('Color Picker', img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    pick_color_fixed()