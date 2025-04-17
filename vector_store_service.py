from docx import Document
from langchain_core.documents import Document as LangchainDocument 
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma 
from langchain_experimental.text_splitter import SemanticChunker
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import settings


def create_vectorstore(file_path: str, api_key: str):
    """Полный пайплайн с явным API ключом"""
    # 1. Чтение файла
    doc = Document(file_path)
    text = "\n".join([p.text for p in doc.paragraphs if p.text])
    
    # 2. Чанкинг
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_text(text)
    
    # 3. Создание эмбеддингов с явным ключом
    embeddings = OpenAIEmbeddings(
        openai_api_key=api_key,
        model="text-embedding-3-small"
    )
    
    # 4. Сохранение в ChromaDB
    vector_store = Chroma.from_texts(
        texts=chunks,
        embedding=embeddings,
        persist_directory="./docx_vector_db"
    )
    return vector_store


if __name__ == "__main__":

    # Явная передача ключа (на практике лучше брать из .env)
    api_key = settings.OPENAI_API_KEY
    
    # Запуск обработки
    store = create_vectorstore("anxiety.docx", api_key)
    print(f"Storage created at: {store._persist_directory}")