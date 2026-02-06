# app/vector_store.py
import chromadb
from chromadb.utils import embedding_functions

# Initialize globals
_client = None
_collection = None

def get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path="./chroma_db")
        emb_fn = embedding_functions.DefaultEmbeddingFunction()
        _collection = _client.get_or_create_collection(name="video_transcripts", embedding_function=emb_fn)
    return _collection

def index_transcript(video_id, segments):
    """Stores segments in the vector database."""
    collection = get_collection()
    ids = [f"{video_id}_{i}" for i in range(len(segments))]
    documents = [s['text'] for s in segments]
    metadatas = [{"start": s['start'], "end": s['end'], "video_id": video_id} for s in segments]
    
    collection.add(ids=ids, documents=documents, metadatas=metadatas)

def search_video_moments(query, video_id):
    """Finds the most relevant timestamps for a natural language query."""
    collection = get_collection()
    results = collection.query(
        query_texts=[query],
        n_results=5,
        where={"video_id": video_id}
    )
    return results['metadatas'][0] # Returns list of {start, end}