# chroma_client.py
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions # New import
import os
import json
import config
import time

# Global client variables
_client = None
_collections = {}

# Global embedding function variable
_embedding_function = None

def get_embedding_function():
    """Gets or creates the embedding function based on config"""
    global _embedding_function
    if _embedding_function is None:
        # Default to paraphrase-multilingual-mpnet-base-v2 if not specified or on error
        model_name = getattr(config, 'EMBEDDING_MODEL_NAME', "sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
        try:
            _embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
            print(f"Successfully initialized embedding function with model: {model_name}")
        except Exception as e:
            print(f"Failed to initialize embedding function with model '{model_name}': {e}")
            # Fallback to default if specified model fails and it's not already the default
            if model_name != "sentence-transformers/paraphrase-multilingual-mpnet-base-v2":
                print("Falling back to default embedding model: sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
                try:
                    _embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
                    print(f"Successfully initialized embedding function with default model.")
                except Exception as e_default:
                    print(f"Failed to initialize default embedding function: {e_default}")
                    _embedding_function = None # Ensure it's None if all attempts fail
            else:
                _embedding_function = None # Ensure it's None if default model also fails
    return _embedding_function

def initialize_chroma_client():
    """Initializes and connects to ChromaDB"""
    global _client
    try:
        # Ensure Chroma directory exists
        os.makedirs(config.CHROMA_DATA_DIR, exist_ok=True)

        # New method (for v1.0.6+)
        _client = chromadb.PersistentClient(path=config.CHROMA_DATA_DIR)
        print(f"Successfully connected to ChromaDB ({config.CHROMA_DATA_DIR})")
        return True
    except Exception as e:
        print(f"Failed to connect to ChromaDB: {e}")
        return False

def get_collection(collection_name):
    """Gets or creates a collection"""
    global _client, _collections
    if not _client:
        if not initialize_chroma_client():
            return None

    if collection_name not in _collections:
        try:
            emb_func = get_embedding_function()
            if emb_func is None:
                print(f"Failed to get or create collection '{collection_name}' due to embedding function initialization failure.")
                return None

            _collections[collection_name] = _client.get_or_create_collection(
                name=collection_name,
                embedding_function=emb_func
            )
            print(f"Successfully got or created collection '{collection_name}' using configured embedding function.")
        except Exception as e:
            print(f"Failed to get collection '{collection_name}' with configured embedding function: {e}")
            # Attempt to create collection with default embedding function as a fallback
            print(f"Attempting to create collection '{collection_name}' with default embedding function...")
            try:
                # Ensure we try the absolute default if the configured one (even if it was the default) failed
                default_emb_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
                _collections[collection_name] = _client.get_or_create_collection(
                    name=collection_name,
                    embedding_function=default_emb_func
                )
                print(f"Successfully got or created collection '{collection_name}' with default embedding function after initial failure.")
            except Exception as e_default:
                print(f"Failed to get collection '{collection_name}' even with default embedding function: {e_default}")
                return None

    return _collections[collection_name]

def get_entity_profile(entity_name, collection_name=None):
    """
    Retrieves entity data (e.g., user profile) from the specified collection

    Args:
        entity_name: The name of the entity to retrieve (e.g., username)
        collection_name: The name of the collection; if None, uses BOT_MEMORY_COLLECTION from config (Correction: Use bot memory collection)
    """
    if not collection_name:
        # Correction: Default to using BOT_MEMORY_COLLECTION to store user data
        collection_name = config.BOT_MEMORY_COLLECTION

    profile_collection = get_collection(collection_name)
    if not profile_collection:
        return None

    try:
        # Restore: Use query method for similarity search instead of exact ID matching
        query_text = f"{entity_name} profile"
        start_time = time.time()
        results = profile_collection.query(
            query_texts=[query_text],
            n_results=1 # Only get the most relevant result
        )
        duration = time.time() - start_time

        # Restore: Check the return result of the query method
        if results and results.get('documents') and results['documents'][0]:
            # query returns a list of lists, so [0][0] is needed
            print(f"Successfully retrieved data for '{entity_name}' (Query: '{query_text}') (Time taken: {duration:.3f}s)")
            return results['documents'][0][0]
        else:
            print(f"Could not find data for '{entity_name}' (Query: '{query_text}')")
            return None
    except Exception as e:
        print(f"Error querying entity data (Query: '{query_text}'): {e}")
        return None

def get_related_memories(entity_name, topic=None, limit=3, collection_name=None):
    """
    Retrieves memories related to an entity

    Args:
        entity_name: The name of the entity (e.g., username)
        topic: Optional topic keyword
        limit: Maximum number of memories to return
        collection_name: The name of the collection; if None, uses CONVERSATIONS_COLLECTION from config
    """
    if not collection_name:
        collection_name = config.CONVERSATIONS_COLLECTION

    memory_collection = get_collection(collection_name)
    if not memory_collection:
        return []

    query = f"{entity_name}"
    if topic:
        query += f" {topic}"

    try:
        start_time = time.time()
        results = memory_collection.query(
            query_texts=[query],
            n_results=limit
        )
        duration = time.time() - start_time

        if results and results['documents'] and results['documents'][0]:
            memory_count = len(results['documents'][0])
            print(f"Successfully retrieved {memory_count} related memories for '{entity_name}' (Time taken: {duration:.3f}s)")
            return results['documents'][0]

        print(f"Could not find related memories for '{entity_name}'")
        return []
    except Exception as e:
        print(f"Error querying related memories: {e}")
        return []

def get_bot_knowledge(concept, limit=3, collection_name=None):
    """
    Retrieves the bot's knowledge about a specific concept

    Args:
        concept: The concept to query
        limit: Maximum number of knowledge entries to return
        collection_name: The name of the collection; if None, uses BOT_MEMORY_COLLECTION from config
    """
    if not collection_name:
        collection_name = config.BOT_MEMORY_COLLECTION

    knowledge_collection = get_collection(collection_name)
    if not knowledge_collection:
        return []

    try:
        start_time = time.time()
        results = knowledge_collection.query(
            query_texts=[concept],
            n_results=limit
        )
        duration = time.time() - start_time

        if results and results['documents'] and results['documents'][0]:
            knowledge_count = len(results['documents'][0])
            print(f"Successfully retrieved {knowledge_count} bot knowledge entries about '{concept}' (Time taken: {duration:.3f}s)")
            return results['documents'][0]

        print(f"Could not find bot knowledge about '{concept}'")
        return []
    except Exception as e:
        print(f"Error querying bot knowledge: {e}")
        return []
