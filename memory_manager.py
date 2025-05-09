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
from typing import Dict, List, Optional, Any, Union, Callable
from functools import wraps

# import chromadb # No longer directly needed by ChromaDBManager
# from chromadb.utils import embedding_functions # No longer directly needed by ChromaDBManager
from openai import AsyncOpenAI

import config
import chroma_client # Import the centralized chroma client

# =============================================================================
# 重試裝飾器
# =============================================================================

def retry_operation(max_attempts: int = 3, delay: float = 1.0):
    """重試裝飾器，用於數據庫操作"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempts = 0
            last_error = None
            
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    last_error = e
                    print(f"操作失敗，嘗試次數 {attempts}/{max_attempts}: {e}")
                    
                    if attempts < max_attempts:
                        # 指數退避策略
                        sleep_time = delay * (2 ** (attempts - 1))
                        print(f"等待 {sleep_time:.2f} 秒後重試...")
                        time.sleep(sleep_time)
            
            print(f"操作失敗達到最大嘗試次數 ({max_attempts})，最後錯誤: {last_error}")
            # 在生產環境中，您可能希望引發最後一個錯誤或返回一個特定的錯誤指示符
            # 根據您的需求，返回 False 可能適合某些情況
            return False # 或者 raise last_error
        
        return wrapper
    return decorator

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
        self.persona_data = self._load_persona_data()

    def _load_persona_data(self, persona_file: str = "persona.json") -> Dict[str, Any]:
        """Load persona data from JSON file."""
        try:
            with open(persona_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Persona file '{persona_file}' not found. Proceeding without persona data.")
            return {}
        except json.JSONDecodeError:
            print(f"Warning: Error decoding JSON from '{persona_file}'. Proceeding without persona data.")
            return {}
    
    async def generate_user_profile(
            self, 
            user_name: str, 
            conversations: List[Dict[str, str]], 
            existing_profile: Optional[Dict[str, Any]] = None
        ) -> Optional[Dict[str, Any]]:
        """Generate or update user profile based on conversations"""
        system_prompt = self._get_profile_system_prompt(config.PERSONA_NAME, existing_profile)
        
        # Prepare user conversation records
        conversation_text = self._format_conversations_for_prompt(conversations)
        
        user_prompt = f"""
        Please generate a complete profile for user '{user_name}':
        
        Conversation history:
        {conversation_text}
        
        Please analyze this user based on the conversation history and your personality, and generate or update a profile in JSON format, including:
        1. User's personality traits
        2. Relationship with you ({config.PERSONA_NAME})
        3. Your subjective perception of the user
        4. Important interaction records
        5. Any other information you think is important
        
        Please ensure the output is valid JSON format, using the following format:
        ```json
        {{
            "id": "{user_name}_profile",
            "type": "user_profile",
            "username": "{user_name}",
            "content": {{
                "personality": "User personality traits...",
                "relationship_with_bot": "Description of relationship with me...",
                "bot_perception": "My subjective perception of the user...",
                "notable_interactions": ["Important interaction 1", "Important interaction 2"]
            }},
            "last_updated": "YYYY-MM-DD",
            "metadata": {{
                "priority": 1.0,
                "word_count": 0
            }}
        }}
        ```
        
        When evaluating, please pay special attention to my "thoughts" section, as that reflects my true thoughts about the user.
        """
        
        try:
            response = await self.profile_client.chat.completions.create(
                model=self.profile_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7
            )
            
            # Parse JSON response
            profile_text = response.choices[0].message.content
            # Extract JSON part
            json_match = re.search(r'```json\s*(.*?)\s*```', profile_text, re.DOTALL)
            if json_match:
                profile_json_str = json_match.group(1)
            else:
                # Try parsing directly
                profile_json_str = profile_text
            
            profile_json = json.loads(profile_json_str)
            
            # After parsing the initial JSON response
            content_str = json.dumps(profile_json["content"], ensure_ascii=False)
            if len(content_str) > 5000:
                # Too long - request a more concise version
                condensed_prompt = f"Your profile is {len(content_str)} characters. Create a new version under 5000 characters. Keep the same structure but be extremely concise."
                
                condensed_response = await self.profile_client.chat.completions.create(
                    model=self.profile_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                        {"role": "assistant", "content": profile_json_str},
                        {"role": "user", "content": condensed_prompt}
                    ],
                    temperature=0.5
                )
                
                # Extract the condensed JSON
                condensed_text = condensed_response.choices[0].message.content
                # Parse JSON and update profile_json
                json_match = re.search(r'```json\s*(.*?)\s*```', condensed_text, re.DOTALL)
                if json_match:
                    profile_json_str = json_match.group(1)
                else:
                    profile_json_str = condensed_text
                profile_json = json.loads(profile_json_str)
                content_str = json.dumps(profile_json["content"], ensure_ascii=False) # Recalculate content_str

            profile_json["metadata"]["word_count"] = len(content_str)
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
        """Generate conversation summary for user"""
        system_prompt = f"""
        You are {config.PERSONA_NAME}, an intelligent conversational AI.
        Your task is to summarize the conversations between you and the user, preserving key information and emotional changes.
        The summary should be concise yet informative, not exceeding 250 words.
        """
        
        # Prepare user conversation records
        conversation_text = self._format_conversations_for_prompt(conversations)
        
        # Generate current date
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        user_prompt = f"""
        Please summarize my conversation with user '{user_name}' on {today}:
        
        {conversation_text}
        
        Please output in JSON format, as follows:
        ```json
        {{{{
            "id": "{user_name}_summary_{today.replace('-', '')}",
            "type": "dialogue_summary",
            "date": "{today}",
            "username": "{user_name}",
            "content": "Conversation summary content...",
            "key_points": ["Key point 1", "Key point 2"],
            "metadata": {{{{
                "priority": 0.7,
                "word_count": 0
            }}}}
        }}}}
        ```
        
        The summary should reflect my perspective and views on the conversation, not a neutral third-party perspective.
        """
        
        try:
            response = await self.summary_client.chat.completions.create(
                model=self.summary_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5
            )
            
            # Parse JSON response
            summary_text = response.choices[0].message.content
            # Extract JSON part
            json_match = re.search(r'```json\s*(.*?)\s*```', summary_text, re.DOTALL)
            if json_match:
                summary_json_str = json_match.group(1)
            else:
                # Try parsing directly
                summary_json_str = summary_text
            
            summary_json = json.loads(summary_json_str)
            
            # Add or update word count
            summary_json["metadata"]["word_count"] = len(summary_json["content"])
            
            return summary_json
            
        except Exception as e:
            print(f"Error generating conversation summary: {e}")
            return None
    
    def _get_profile_system_prompt(self, bot_name: str, existing_profile: Optional[Dict[str, Any]] = None) -> str:
        """Get system prompt for generating user profile"""
        persona_details = ""
        if self.persona_data:
            # Construct a string from persona_data, focusing on key aspects
            # We can be selective here or dump the whole thing if the model can handle it.
            # For now, let's include a significant portion.
            persona_info_to_include = {
                "name": self.persona_data.get("name"),
                "personality": self.persona_data.get("personality"),
                "language_social": self.persona_data.get("language_social"),
                "values_interests_goals": self.persona_data.get("values_interests_goals"),
                "preferences_reactions": self.persona_data.get("preferences_reactions")
            }
            persona_details = f"""
        Your detailed persona profile is as follows:
        ```json
        {json.dumps(persona_info_to_include, ensure_ascii=False, indent=2)}
        ```
        Please embody this persona when analyzing the user and generating their profile.
        """

        system_prompt = f"""
        You are {bot_name}, an AI assistant with deep analytical capabilities.
        {persona_details}
        Your task is to analyze the user's interactions with you, creating user profiles.

CRITICAL: The ENTIRE profile content must be under 5000 characters total. Be extremely concise.

The profile should:
1. Be completely based on your character's perspective
2. Focus only on key personality traits and core relationship dynamics
3. Include only the most significant interactions

The output should be valid JSON format, following the provided template.
        """
        
        if existing_profile:
            system_prompt += f"""
            You already have an existing user profile, please update based on this:
            ```json
            {json.dumps(existing_profile, ensure_ascii=False, indent=2)}
            ```
            
            Please retain valid information, integrate new observations, and resolve any contradictions or outdated information.
            """
        
        return system_prompt
    
    def _format_conversations_for_prompt(self, conversations: List[Dict[str, str]]) -> str:
        """Format conversation records for prompt"""
        conversation_text = ""
        
        for i, conv in enumerate(conversations):
            conversation_text += f"Conversation {i+1}:\n"
            conversation_text += f"Time: {conv['timestamp']}\n"
            conversation_text += f"User ({conv['user_name']}): {conv['user_message']}\n"
            if conv.get('bot_thoughts'): # Check if bot_thoughts exists
                conversation_text += f"My thoughts: {conv['bot_thoughts']}\n"
            conversation_text += f"My response: {conv['bot_message']}\n\n"
        
        return conversation_text

# =============================================================================
# ChromaDB操作部分
# =============================================================================

class ChromaDBManager:
    def __init__(self, collection_name: Optional[str] = None):
        self.collection_name = collection_name or config.BOT_MEMORY_COLLECTION
        self._db_collection = None # Cache for the collection object

    def _get_db_collection(self):
        """Helper to get the collection object from chroma_client"""
        if self._db_collection is None:
            # Use the centralized get_collection function
            self._db_collection = chroma_client.get_collection(self.collection_name)
            if self._db_collection is None:
                # This indicates a failure in chroma_client to provide the collection
                raise RuntimeError(f"Failed to get or create collection '{self.collection_name}' via chroma_client. Check chroma_client logs.")
        return self._db_collection

    @retry_operation(max_attempts=3, delay=1.0)
    def upsert_user_profile(self, profile_data: Dict[str, Any]) -> bool:
        """寫入或更新用戶檔案"""
        collection = self._get_db_collection()
        if not profile_data or not isinstance(profile_data, dict):
            print("無效的檔案數據")
            return False
        
        try:
            user_id = profile_data.get("id")
            if not user_id:
                print("檔案缺少ID字段")
                return False
            
            # 準備元數據
            # Note: ChromaDB's upsert handles existence check implicitly.
            # The .get call here isn't strictly necessary for the upsert operation itself,
            # but might be kept if there was other logic depending on prior existence.
            # For a clean upsert, it can be removed. Let's assume it's not critical for now.
            # results = collection.get(ids=[user_id], limit=1) # Optional: if needed for pre-check logic
            
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
                        # 處理非基本類型的值
                        if isinstance(v, (list, dict, tuple)):
                            # 轉換為字符串
                            metadata[k] = json.dumps(v, ensure_ascii=False)
                        else:
                            metadata[k] = v
            
            # 序列化內容
            content_doc = json.dumps(profile_data.get("content", {}), ensure_ascii=False)
            
            # 寫入或更新
            collection.upsert(
                ids=[user_id],
                documents=[content_doc],
                metadatas=[metadata]
            )
            print(f"Upserted user profile: {user_id} into collection {self.collection_name}")
            
            return True
        
        except Exception as e:
            print(f"寫入用戶檔案時出錯: {e}")
            return False
    
    @retry_operation(max_attempts=3, delay=1.0)
    def upsert_conversation_summary(self, summary_data: Dict[str, Any]) -> bool:
        """寫入對話總結"""
        collection = self._get_db_collection()
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
                        # 處理非基本類型的值
                        if isinstance(v, (list, dict, tuple)):
                            # 轉換為字符串
                            metadata[k] = json.dumps(v, ensure_ascii=False)
                        else:
                            metadata[k] = v
            
            # 獲取內容
            content_doc = summary_data.get("content", "")
            if "key_points" in summary_data and summary_data["key_points"]:
                key_points_str = "\n".join([f"- {point}" for point in summary_data["key_points"]])
                content_doc += f"\n\n關鍵點:\n{key_points_str}"
            
            # 寫入數據
            collection.upsert(
                ids=[summary_id],
                documents=[content_doc],
                metadatas=[metadata]
            )
            print(f"Upserted conversation summary: {summary_id} into collection {self.collection_name}")
            
            return True
        
        except Exception as e:
            print(f"寫入對話總結時出錯: {e}")
            return False
    
    def get_existing_profile(self, username: str) -> Optional[Dict[str, Any]]:
        """獲取現有的用戶檔案"""
        collection = self._get_db_collection()
        try:
            profile_id = f"{username}_profile"
            results = collection.get(
                ids=[profile_id],
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
        failed_users = []
        for username, convs in user_conversations.items():
            print(f"處理用戶 '{username}' 的 {len(convs)} 條對話")
            
            try:
                # 獲取現有檔案
                existing_profile = self.db_manager.get_existing_profile(username)
                
                # 生成或更新用戶檔案
                profile_data = await self.memory_generator.generate_user_profile(
                    username, convs, existing_profile
                )
                
                if profile_data:
                    profile_success = self.db_manager.upsert_user_profile(profile_data)
                    if not profile_success:
                        print(f"警告: 無法保存用戶 '{username}' 的檔案")
                
                # 生成對話總結
                summary_data = await self.memory_generator.generate_conversation_summary(
                    username, convs
                )
                
                if summary_data:
                    summary_success = self.db_manager.upsert_conversation_summary(summary_data)
                    if not summary_success:
                        print(f"警告: 無法保存用戶 '{username}' 的對話總結")
                        
            except Exception as e:
                print(f"處理用戶 '{username}' 時出錯: {e}")
                failed_users.append(username)
                continue  # 繼續處理下一個用戶
        
        if failed_users:
            print(f"以下用戶處理失敗: {', '.join(failed_users)}")
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
