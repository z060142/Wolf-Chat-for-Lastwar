#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wolf Chat 記憶管理模組

處理聊天記錄解析、記憶生成和ChromaDB寫入的一體化模組
"""

import os
import re
import json
import time
import asyncio
import datetime
import schedule
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

import chromadb
from chromadb.utils import embedding_functions
from openai import AsyncOpenAI

import config

# =============================================================================
# 日誌解析部分
# =============================================================================

def parse_log_file(log_path: str) -> List[Dict[str, str]]:
    """解析日誌文件，提取對話內容"""
    conversations = []
    
    with open(log_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # 使用分隔符分割對話
    dialogue_blocks = content.split('---')
    
    for block in dialogue_blocks:
        if not block.strip():
            continue
            
        # 解析對話塊
        timestamp_pattern = r'\[([\d-]+ [\d:]+)\]'
        user_pattern = r'User \(([^)]+)\): (.+?)(?=\[|$)'
        bot_thoughts_pattern = r'Bot \(([^)]+)\) Thoughts: (.+?)(?=\[|$)'
        bot_dialogue_pattern = r'Bot \(([^)]+)\) Dialogue: (.+?)(?=\[|$)'
        
        # 提取時間戳記
        timestamp_match = re.search(timestamp_pattern, block)
        user_match = re.search(user_pattern, block, re.DOTALL)
        bot_thoughts_match = re.search(bot_thoughts_pattern, block, re.DOTALL)
        bot_dialogue_match = re.search(bot_dialogue_pattern, block, re.DOTALL)
        
        if timestamp_match and user_match and bot_dialogue_match:
            timestamp = timestamp_match.group(1)
            user_name = user_match.group(1)
            user_message = user_match.group(2).strip()
            bot_name = bot_dialogue_match.group(1)
            bot_message = bot_dialogue_match.group(2).strip()
            bot_thoughts = bot_thoughts_match.group(2).strip() if bot_thoughts_match else ""
            
            # 創建對話記錄
            conversation = {
                "timestamp": timestamp,
                "user_name": user_name,
                "user_message": user_message,
                "bot_name": bot_name,
                "bot_message": bot_message,
                "bot_thoughts": bot_thoughts
            }
            
            conversations.append(conversation)
    
    return conversations

def get_logs_for_date(date: datetime.date, log_dir: str = "chat_logs") -> List[Dict[str, str]]:
    """獲取指定日期的所有日誌文件"""
    date_str = date.strftime("%Y-%m-%d")
    log_path = os.path.join(log_dir, f"{date_str}.log")
    
    if os.path.exists(log_path):
        return parse_log_file(log_path)
    return []

def group_conversations_by_user(conversations: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    """按用戶分組對話"""
    user_conversations = {}
    
    for conv in conversations:
        user_name = conv["user_name"]
        if user_name not in user_conversations:
            user_conversations[user_name] = []
        user_conversations[user_name].append(conv)
    
    return user_conversations

# =============================================================================
# 記憶生成器部分
# =============================================================================

class MemoryGenerator:
    def __init__(self, profile_model: Optional[str] = None, summary_model: Optional[str] = None):
        self.profile_client = AsyncOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_API_BASE_URL if config.OPENAI_API_BASE_URL else None,
        )
        self.summary_client = AsyncOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_API_BASE_URL if config.OPENAI_API_BASE_URL else None,
        )
        self.profile_model = profile_model or getattr(config, 'MEMORY_PROFILE_MODEL', config.LLM_MODEL)
        self.summary_model = summary_model or getattr(config, 'MEMORY_SUMMARY_MODEL', "mistral-7b-instruct")

    async def generate_user_profile(
            self,
            user_name: str,
            conversations: List[Dict[str, str]],
            existing_profile: Optional[Dict[str, Any]] = None
        ) -> Optional[Dict[str, Any]]:
        """Generates or updates a user profile based on conversations."""
        system_prompt = self._get_profile_system_prompt(config.PERSONA_NAME, existing_profile)

        # Prepare user conversation history
        conversation_text = self._format_conversations_for_prompt(conversations)

        user_prompt = f"""
        Please generate a comprehensive profile for the user '{user_name}'.

        Conversation History:
        {conversation_text}

        Based on the conversation history and your persona, analyze this user and generate or update their profile in JSON format. The profile should include:
        1. User's personality traits
        2. Relationship with you ({config.PERSONA_NAME})
        3. Your subjective perception of the user
        4. Notable interactions
        5. Any other information you deem important

        Ensure the output is a valid JSON object, using the following format:
        ```json
        {{
            "id": "{user_name}_profile",
            "type": "user_profile",
            "username": "{user_name}",
            "content": {{
                "personality": "User's personality traits...",
                "relationship_with_bot": "Description of the relationship with me...",
                "bot_perception": "My subjective perception of the user...",
                "notable_interactions": ["Notable interaction 1", "Notable interaction 2"]
            }},
            "last_updated": "YYYY-MM-DD",
            "metadata": {{
                "priority": 1.0,
                "word_count": 0
            }}
        }}
        ```

        During your assessment, pay special attention to my "My thoughts" section in the conversation history, as it reflects my genuine impressions of the user.
        """

        try:
            response = await self.profile_client.chat.completions.create(
                model=self.profile_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                # Consider adding response_format for reliable JSON output if your model/API supports it
                # response_format={"type": "json_object"}
            )

            # Parse JSON response
            profile_text = response.choices[0].message.content
            # Extract JSON part
            json_match = re.search(r'```json\s*(.*?)\s*```', profile_text, re.DOTALL)
            if json_match:
                profile_json_str = json_match.group(1)
            else:
                # Try to parse directly if no markdown fence is found
                profile_json_str = profile_text

            profile_json = json.loads(profile_json_str)

            # Add or update word count
            # Note: len(json.dumps(...)) counts characters, not words.
            # For a true word count, you might need a different approach.
            content_str = json.dumps(profile_json.get("content", {}), ensure_ascii=False)
            profile_json.setdefault("metadata", {})["word_count"] = len(content_str.split()) # Rough word count
            profile_json["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d")

            return profile_json

        except Exception as e:
            print(f"Error generating user profile: {e}")
            return None

    async def generate_conversation_summary(
            self,
            user_name: str,
            conversations: List[Dict[str, str]]
        ) -> Optional[Dict[str, Any]]:
        """Generates a summary of user conversations."""
        system_prompt = f"""
        You are {config.PERSONA_NAME}, an intelligent conversational bot.
        Your task is to summarize the conversation between you and the user, preserving key information and emotional shifts.
        The summary should be concise yet informative, not exceeding 250 words.
        """

        # Prepare user conversation history
        conversation_text = self._format_conversations_for_prompt(conversations)

        # Generate current date
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        user_prompt = f"""
        Please summarize my conversation with user '{user_name}' on {today}:

        {conversation_text}

        Output the summary in JSON format, structured as follows:
        ```json
        {{
            "id": "{user_name}_summary_{today.replace('-', '')}",
            "type": "dialogue_summary",
            "date": "{today}",
            "username": "{user_name}",
            "content": "Conversation summary content...",
            "key_points": ["Key point 1", "Key point 2"],
            "metadata": {{
                "priority": 0.7,
                "word_count": 0
            }}
        }}
        ```

        The summary should reflect my perspective and views on the conversation, not a neutral third-party viewpoint.
        """

        try:
            response = await self.summary_client.chat.completions.create(
                model=self.summary_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5,
                # response_format={"type": "json_object"} # if supported
            )

            # Parse JSON response
            summary_text = response.choices[0].message.content
            # Extract JSON part
            json_match = re.search(r'```json\s*(.*?)\s*```', summary_text, re.DOTALL)
            if json_match:
                summary_json_str = json_match.group(1)
            else:
                # Try to parse directly
                summary_json_str = summary_text

            summary_json = json.loads(summary_json_str)

            # Add or update word count
            # Using split() for a rough word count of the summary content.
            summary_json.setdefault("metadata", {})["word_count"] = len(summary_json.get("content", "").split())

            return summary_json

        except Exception as e:
            print(f"Error generating conversation summary: {e}")
            return None

    def _get_profile_system_prompt(self, bot_name: str, existing_profile: Optional[Dict[str, Any]] = None) -> str:
        """Gets the system prompt for generating a user profile."""
        system_prompt = f"""
        You are {bot_name}, an AI assistant with deep analytical capabilities.

        Your personality traits:
        - Intelligent, calm, with a strong desire for control and strategic thinking.
        - Outwardly aloof but inwardly caring.
        - Meticulous planner, insightful about human nature, strong leadership skills.
        - Overconfident, fears losing control, finds it difficult to express care directly.

        Your task is to analyze user interactions with you and create a detailed user profile. The profile must:
        1. Be entirely from your role's perspective, including your subjective judgments and feelings.
        2. Analyze the user's personality traits and behavioral patterns.
        3. Assess the user's relationship with you.
        4. Record important interaction history.

        The output must be in valid JSON format, adhering to the provided template.
        """

        if existing_profile:
            system_prompt += f"""

            You have an existing profile for this user. Please update it based on the new information provided in the conversation history:
            ```json
            {json.dumps(existing_profile, ensure_ascii=False, indent=2)}
            ```

            Retain valid information, integrate new observations, and resolve any contradictions or outdated information from the existing profile when incorporating the new interactions.
            """

        return system_prompt

    def _format_conversations_for_prompt(self, conversations: List[Dict[str, str]]) -> str:
        """Formats conversation history for the prompt."""
        conversation_text = ""

        for i, conv in enumerate(conversations):
            conversation_text += f"Conversation {i+1}:\n"
            conversation_text += f"Time: {conv.get('timestamp', 'N/A')}\n" # Added .get for safety
            conversation_text += f"User ({conv.get('user_name', 'User')}): {conv.get('user_message', '')}\n"
            if conv.get('bot_thoughts'): # Check if bot_thoughts exists
                conversation_text += f"My thoughts: {conv['bot_thoughts']}\n"
            conversation_text += f"My response: {conv.get('bot_message', '')}\n\n"

        return conversation_text.strip()

# =============================================================================
# ChromaDB操作部分
# =============================================================================

class ChromaDBManager:
    def __init__(self, collection_name: Optional[str] = None):
        self.client = chromadb.PersistentClient(path=config.CHROMA_DATA_DIR)
        self.collection_name = collection_name or config.BOT_MEMORY_COLLECTION
        self.embedding_function = embedding_functions.DefaultEmbeddingFunction()
        self._ensure_collection()
    
    def _ensure_collection(self) -> None:
        """確保集合存在"""
        try:
            self.collection = self.client.get_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function
            )
            print(f"Connected to existing collection: {self.collection_name}")
        except Exception:
            self.collection = self.client.create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function
            )
            print(f"Created new collection: {self.collection_name}")
    
    def upsert_user_profile(self, profile_data: Dict[str, Any]) -> bool:
        """寫入或更新用戶檔案"""
        if not profile_data or not isinstance(profile_data, dict):
            print("無效的檔案數據")
            return False
        
        try:
            user_id = profile_data.get("id")
            if not user_id:
                print("檔案缺少ID字段")
                return False
            
            # 先檢查是否已存在
            results = self.collection.get(
                ids=[user_id], # Query by a list of IDs
                # where={"id": user_id}, # 'where' is for metadata filtering
                limit=1
            )
            
            # 準備元數據
            metadata = {
                "id": user_id,
                "type": "user_profile",
                "username": profile_data.get("username", ""),
                "priority": 1.0  # 高優先級
            }
            
            # 添加其他元數據
            if "metadata" in profile_data and isinstance(profile_data["metadata"], dict):
                for k, v in profile_data["metadata"].items():
                    if k not in ["id", "type", "username", "priority"]: # Avoid overwriting key fields
                        metadata[k] = v
            
            # 序列化內容
            content_doc = json.dumps(profile_data.get("content", {}), ensure_ascii=False)
            
            # 寫入或更新
            # ChromaDB's add/upsert handles both cases.
            # If an ID exists, it's an update; otherwise, it's an add.
            self.collection.upsert(
                ids=[user_id],
                documents=[content_doc],
                metadatas=[metadata]
            )
            print(f"Upserted user profile: {user_id}")
            
            return True
        
        except Exception as e:
            print(f"寫入用戶檔案時出錯: {e}")
            return False
    
    def upsert_conversation_summary(self, summary_data: Dict[str, Any]) -> bool:
        """寫入對話總結"""
        if not summary_data or not isinstance(summary_data, dict):
            print("無效的總結數據")
            return False
        
        try:
            summary_id = summary_data.get("id")
            if not summary_id:
                print("總結缺少ID字段")
                return False
            
            # 準備元數據
            metadata = {
                "id": summary_id,
                "type": "dialogue_summary",
                "username": summary_data.get("username", ""),
                "date": summary_data.get("date", ""),
                "priority": 0.7  # 低優先級
            }
            
            # 添加其他元數據
            if "metadata" in summary_data and isinstance(summary_data["metadata"], dict):
                for k, v in summary_data["metadata"].items():
                    if k not in ["id", "type", "username", "date", "priority"]:
                        metadata[k] = v
            
            # 獲取內容
            content_doc = summary_data.get("content", "")
            if "key_points" in summary_data and summary_data["key_points"]:
                key_points_str = "\n".join([f"- {point}" for point in summary_data["key_points"]])
                content_doc += f"\n\n關鍵點:\n{key_points_str}"
            
            # 寫入數據 (ChromaDB's add implies upsert if ID exists, but upsert is more explicit)
            self.collection.upsert(
                ids=[summary_id],
                documents=[content_doc],
                metadatas=[metadata]
            )
            print(f"Upserted conversation summary: {summary_id}")
            
            return True
        
        except Exception as e:
            print(f"寫入對話總結時出錯: {e}")
            return False
    
    def get_existing_profile(self, username: str) -> Optional[Dict[str, Any]]:
        """獲取現有的用戶檔案"""
        try:
            profile_id = f"{username}_profile"
            results = self.collection.get(
                ids=[profile_id], # Query by a list of IDs
                limit=1
            )
            
            if results and results["ids"] and results["documents"]:
                idx = 0
                # Ensure document is not None before trying to load
                doc_content = results["documents"][idx]
                if doc_content is None:
                    print(f"Warning: Document for profile {profile_id} is None.")
                    return None

                profile_data = {
                    "id": profile_id,
                    "type": "user_profile",
                    "username": username,
                    "content": json.loads(doc_content),
                    "last_updated": "", # Will be populated from metadata if exists
                    "metadata": {}
                }
                
                # 獲取元數據
                if results["metadatas"] and results["metadatas"][idx]:
                    metadata_db = results["metadatas"][idx]
                    for k, v in metadata_db.items():
                        if k == "last_updated":
                             profile_data["last_updated"] = str(v) # Ensure it's a string
                        elif k not in ["id", "type", "username"]:
                            profile_data["metadata"][k] = v
                
                return profile_data
            
            return None
        
        except json.JSONDecodeError as je:
            print(f"Error decoding JSON for profile {username}: {je}")
            return None
        except Exception as e:
            print(f"獲取用戶檔案時出錯 for {username}: {e}")
            return None

# =============================================================================
# 記憶管理器
# =============================================================================

class MemoryManager:
    def __init__(self):
        self.memory_generator = MemoryGenerator(
            profile_model=getattr(config, 'MEMORY_PROFILE_MODEL', config.LLM_MODEL),
            summary_model=getattr(config, 'MEMORY_SUMMARY_MODEL', "mistral-7b-instruct")
        )
        self.db_manager = ChromaDBManager(collection_name=config.BOT_MEMORY_COLLECTION)
        # Ensure LOG_DIR is correctly referenced from config
        self.log_dir = getattr(config, 'LOG_DIR', "chat_logs") 
    
    async def process_daily_logs(self, date: Optional[datetime.date] = None) -> None:
        """處理指定日期的日誌（預設為昨天）"""
        # 如果未指定日期，使用昨天
        if date is None:
            date = datetime.datetime.now().date() - datetime.timedelta(days=1)
        
        date_str = date.strftime("%Y-%m-%d")
        log_path = os.path.join(self.log_dir, f"{date_str}.log")
        
        if not os.path.exists(log_path):
            print(f"找不到日誌文件: {log_path}")
            return
        
        print(f"開始處理日誌文件: {log_path}")
        
        # 解析日誌
        conversations = parse_log_file(log_path)
        if not conversations:
            print(f"日誌文件 {log_path} 為空或未解析到對話。")
            return
        print(f"解析到 {len(conversations)} 條對話記錄")
        
        # 按用戶分組
        user_conversations = group_conversations_by_user(conversations)
        print(f"共有 {len(user_conversations)} 個用戶有對話")
        
        # 為每個用戶生成/更新檔案和對話總結
        for username, convs in user_conversations.items():
            print(f"處理用戶 '{username}' 的 {len(convs)} 條對話")
            
            # 獲取現有檔案
            existing_profile = self.db_manager.get_existing_profile(username)
            
            # 生成或更新用戶檔案
            profile_data = await self.memory_generator.generate_user_profile(
                username, convs, existing_profile
            )
            
            if profile_data:
                self.db_manager.upsert_user_profile(profile_data)
            
            # 生成對話總結
            summary_data = await self.memory_generator.generate_conversation_summary(
                username, convs
            )
            
            if summary_data:
                self.db_manager.upsert_conversation_summary(summary_data)
        print(f"日誌處理完成: {log_path}")

# =============================================================================
# 定時調度器
# =============================================================================

class MemoryScheduler:
    def __init__(self):
        self.memory_manager = MemoryManager()
        self.scheduled = False # To track if a job is already scheduled
    
    def schedule_daily_backup(self, hour: Optional[int] = None, minute: Optional[int] = None) -> None:
        """設置每日備份時間"""
        # Clear any existing jobs to prevent duplicates if called multiple times
        schedule.clear()

        backup_hour = hour if hour is not None else getattr(config, 'MEMORY_BACKUP_HOUR', 0)
        backup_minute = minute if minute is not None else getattr(config, 'MEMORY_BACKUP_MINUTE', 0)
        
        time_str = f"{backup_hour:02d}:{backup_minute:02d}"

        # 設置定時任務
        schedule.every().day.at(time_str).do(self._run_daily_backup_job)
        self.scheduled = True
        print(f"已設置每日備份時間: {time_str}")
    
    def _run_daily_backup_job(self) -> None:
        """Helper to run the async job for scheduler."""
        print(f"開始執行每日記憶備份 - {datetime.datetime.now()}")
        try:
            # Create a new event loop for the thread if not running in main thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.memory_manager.process_daily_logs())
            loop.close()
            print(f"每日記憶備份完成 - {datetime.datetime.now()}")
        except Exception as e:
            print(f"執行每日備份時出錯: {e}")
        # schedule.every().day.at...do() expects the job function to return schedule.CancelJob
        # if it should not be rescheduled. Otherwise, it's rescheduled.
        # For a daily job, we want it to reschedule, so we don't return CancelJob.

    def start(self) -> None:
        """啟動調度器"""
        if not self.scheduled:
            self.schedule_daily_backup() # Schedule with default/config times if not already
        
        print("調度器已啟動，按Ctrl+C停止")
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)  # Check every second
        except KeyboardInterrupt:
            print("調度器已停止")
        except Exception as e:
            print(f"調度器運行時發生錯誤: {e}")
        finally:
            print("調度器正在關閉...")


# =============================================================================
# 直接運行入口
# =============================================================================

def run_memory_backup_manual(date_str: Optional[str] = None) -> None:
    """手動執行記憶備份 for a specific date string or yesterday."""
    target_date = None
    if date_str:
        try:
            target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            print(f"無效的日期格式: {date_str}。將使用昨天的日期。")
            target_date = datetime.datetime.now().date() - datetime.timedelta(days=1)
    else:
        target_date = datetime.datetime.now().date() - datetime.timedelta(days=1)
        print(f"未指定日期，將處理昨天的日誌: {target_date.strftime('%Y-%m-%d')}")

    memory_manager = MemoryManager()
    
    # Setup asyncio event loop for the manual run
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    try:
        loop.run_until_complete(memory_manager.process_daily_logs(target_date))
    except Exception as e:
        print(f"手動執行記憶備份時出錯: {e}")
    finally:
        # If we created a new loop, we might want to close it.
        # However, if get_event_loop() returned an existing running loop,
        # we should not close it here.
        # For simplicity in a script, this might be okay, but in complex apps, be careful.
        # loop.close() # Be cautious with this line.
        pass
    print("記憶備份完成")


# 如果直接運行此腳本
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Wolf Chat 記憶管理模組')
    parser.add_argument('--backup', action='store_true', help='執行一次性備份 (預設為昨天，除非指定 --date)')
    parser.add_argument('--date', type=str, help='處理指定日期的日誌 (YYYY-MM-DD格式) for --backup')
    parser.add_argument('--schedule', action='store_true', help='啟動定時調度器')
    parser.add_argument('--hour', type=int, help='備份時間（小時，0-23）for --schedule')
    parser.add_argument('--minute', type=int, help='備份時間（分鐘，0-59）for --schedule')
    
    args = parser.parse_args()
    
    if args.backup:
        run_memory_backup_manual(args.date)
    elif args.schedule:
        scheduler = MemoryScheduler()
        # Pass hour/minute only if they are provided, otherwise defaults in schedule_daily_backup will be used
        scheduler.schedule_daily_backup(
            hour=args.hour if args.hour is not None else getattr(config, 'MEMORY_BACKUP_HOUR', 0),
            minute=args.minute if args.minute is not None else getattr(config, 'MEMORY_BACKUP_MINUTE', 0)
        )
        scheduler.start()
    else:
        print("請指定操作: --backup 或 --schedule")
        parser.print_help()
