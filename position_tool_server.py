#!/usr/bin/env python3
"""
Position Tool MCP Server - 文件鎖通訊版本
提供職位移除功能的MCP工具，透過文件系統與主程式通訊
"""

from mcp.server.fastmcp import FastMCP
import asyncio
import json
import logging
import sys
import time
import os
from pathlib import Path

# 設置日誌到stderr（MCP Server不能使用stdout）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger('position-tool-server')

# 初始化FastMCP server
mcp = FastMCP("position-tool")

# 文件通訊路徑
COMMAND_FILE = "position_command.json" 
RESULT_FILE = "position_result.json"
HEARTBEAT_FILE = "main_heartbeat.json"

def is_main_alive():
    """檢查main.py是否存活"""
    try:
        if not os.path.exists(HEARTBEAT_FILE):
            logger.warning("Heartbeat file not found")
            return False
        
        with open(HEARTBEAT_FILE, 'r', encoding='utf-8') as f:
            heartbeat = json.load(f)
        
        # 檢查心跳是否在30秒內
        current_time = time.time()
        heartbeat_time = heartbeat.get("timestamp", 0)
        is_alive = (current_time - heartbeat_time) < 30
        
        if not is_alive:
            logger.warning(f"Main program heartbeat expired. Current: {current_time}, Heartbeat: {heartbeat_time}")
        
        return is_alive
    except Exception as e:
        logger.error(f"Error checking main program status: {e}")
        return False

def can_write_command_file():
    """檢查是否可以寫入命令文件"""
    try:
        # 測試寫入權限
        test_data = {"test": True, "timestamp": time.time()}
        with open("test_write.json", 'w', encoding='utf-8') as f:
            json.dump(test_data, f)
        os.remove("test_write.json")
        return True
    except Exception as e:
        logger.error(f"Cannot write command file: {e}")
        return False

def error_response(message, suggestion="請檢查主程式是否正常運行，或重新啟動系統"):
    """生成統一的錯誤回應"""
    return json.dumps({
        "status": "error",
        "message": message,
        "suggestion": suggestion,
        "execution_time": time.strftime("%Y-%m-%d %H:%M:%S")
    }, ensure_ascii=False)

async def wait_for_result_file(request_id, timeout=10):
    """等待結果文件出現"""
    start_time = time.time()
    logger.info(f"Waiting for result file for request {request_id}, timeout: {timeout}s")
    
    while time.time() - start_time < timeout:
        if os.path.exists(RESULT_FILE):
            try:
                with open(RESULT_FILE, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                
                # 檢查是否是我們的請求的結果
                if result.get("request_id") == request_id:
                    # 清理結果文件
                    try:
                        os.remove(RESULT_FILE)
                        logger.info(f"Result received and file cleaned for request {request_id}")
                    except:
                        logger.warning("Could not remove result file")
                    
                    return result
                else:
                    logger.warning(f"Result file contains different request_id: {result.get('request_id')}")
            except Exception as e:
                logger.error(f"Error reading result file: {e}")
        
        await asyncio.sleep(0.1)
    
    logger.warning(f"Timeout waiting for result file for request {request_id}")
    return {
        "status": "error",
        "message": "操作超時，可能是UI識別失敗或系統忙碌",
        "request_id": request_id,
        "execution_time": time.strftime("%Y-%m-%d %H:%M:%S")
    }

async def execute_with_retry(attempt, request_id):
    """執行命令並重試機制"""
    logger.info(f"Executing position removal, attempt {attempt + 1}, request {request_id}")
    
    # 寫入命令文件
    command = {
        "action": "remove_position_with_feedback",
        "timestamp": time.time(),
        "request_id": request_id,
        "attempt": attempt + 1
    }
    
    try:
        with open(COMMAND_FILE, 'w', encoding='utf-8') as f:
            json.dump(command, f, ensure_ascii=False)
        logger.info(f"Command file written for request {request_id}")
        
        # 等待結果文件出現
        result = await wait_for_result_file(request_id, timeout=12)
        return result
        
    except Exception as e:
        logger.error(f"Error in execute_with_retry: {e}")
        raise

@mcp.tool()
async def remove_user_position() -> str:
    """
    啟動職位移除操作開關（無需參數）
    
    Returns:
        執行結果的JSON字串
    """
    request_id = int(time.time() * 1000)
    logger.info(f"Received remove_user_position request {request_id}")
    
    # 1. 檢查main程式存活
    if not is_main_alive():
        logger.error("Main program is not alive")
        return error_response("主程式未運行或無回應")
    
    # 2. 檢查命令文件權限
    if not can_write_command_file():
        logger.error("Cannot write command file")
        return error_response("無法寫入命令文件，請檢查文件權限")
    
    # 3. 多次重試機制
    for attempt in range(3):
        try:
            result = await execute_with_retry(attempt, request_id)
            
            if result.get("status") != "error":
                logger.info(f"Position removal successful on attempt {attempt + 1}")
                return json.dumps(result, ensure_ascii=False)
            elif attempt < 2:  # 不是最後一次嘗試
                logger.warning(f"Attempt {attempt + 1} failed, retrying: {result.get('message')}")
                await asyncio.sleep(1)  # 等待後重試
            
        except Exception as e:
            logger.error(f"Exception in attempt {attempt + 1}: {e}")
            if attempt == 2:  # 最後一次嘗試
                return error_response(f"重試失敗: {str(e)}")
            await asyncio.sleep(1)
    
    # 如果所有重試都失敗
    logger.error("All retry attempts failed")
    return error_response("多次重試後仍然失敗，請檢查系統狀態")

@mcp.tool()
async def check_position_tool_status() -> str:
    """
    Check position tool and main program status
    
    Returns:
        Simple status confirmation as JSON string
    """
    # Simplified status check - just confirm system is running
    is_system_alive = is_main_alive()
    
    status_info = {
        "system_status": "online" if is_system_alive else "offline",
        "check_time": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    logger.info(f"Status check: System {'online' if is_system_alive else 'offline'}")
    return json.dumps(status_info, ensure_ascii=False)

if __name__ == "__main__":
    logger.info("Starting Position Tool MCP Server with file-lock communication...")
    logger.info("Server will communicate with main program via file system")
    logger.info(f"Command file: {COMMAND_FILE}")
    logger.info(f"Result file: {RESULT_FILE}")
    logger.info(f"Heartbeat file: {HEARTBEAT_FILE}")
    
    try:
        # 運行MCP服務器
        mcp.run(transport='stdio')
    except KeyboardInterrupt:
        logger.info("Server shutdown requested via keyboard interrupt")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise