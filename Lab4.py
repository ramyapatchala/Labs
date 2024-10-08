import streamlit as st
from openai import OpenAI
import os
from PyPDF2 import PdfReader
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import chromadb

# Initialize OpenAI client
if 'openai_client' not in st.session_state:
    api_key = st.secrets['key1']
    st.session_state.openai_client = OpenAI(api_key=api_key)

# Function to add PDF content to ChromaDB collection
def add_to_collection(collection, text, filename):
    openai_client = st.session_state.openai_client
    response = openai_client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    embedding = response.data[0].embedding
    collection.add(
        documents=[text],
        ids=[filename],
        embeddings=[embedding]
    )
    return collection

# Function to set up VectorDB if not already created
def setup_vectordb():
    if 'Lab4_vectorDB' not in st.session_state:
        client = chromadb.PersistentClient()
        collection = client.get_or_create_collection(
            name="Lab4Collection",
            metadata={"hnsw:space": "cosine", "hnsw:M": 32}
        )
        
        datafiles_path = os.path.join(os.getcwd(), "datafiles")
        pdf_files = [f for f in os.listdir(datafiles_path) if f.endswith('.pdf')]
        
        for pdf_file in pdf_files:
            file_path = os.path.join(datafiles_path, pdf_file)
            with open(file_path, 'rb') as file:
                pdf_reader = PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
                collection = add_to_collection(collection, text, pdf_file)
        
        st.session_state.Lab4_vectorDB = collection
        st.success(f"VectorDB setup complete with {len(pdf_files)} PDF files!")
    else:
        st.info("VectorDB already set up.")

# Function to query the VectorDB and retrieve relevant documents
def query_vectordb(query, k=3):
    if 'Lab4_vectorDB' in st.session_state:
        collection = st.session_state.Lab4_vectorDB
        openai_client = st.session_state.openai_client
        response = openai_client.embeddings.create(
            input=query,
            model="text-embedding-3-small"
        )
        query_embedding = response.data[0].embedding
        results = collection.query(
            query_embeddings=[query_embedding],
            include=['documents', 'distances', 'metadatas'],
            n_results=k
        )
        return results
    else:
        st.error("VectorDB not set up. Please set up the VectorDB first.")
        return None

# Function to get a response from OpenAI using the retrieved context
def get_ai_response(query, context):
    openai_client = st.session_state.openai_client
    messages = [
        {"role": "system", "content": "You are a helpful assistant with knowledge about the course materials. Use the provided context to answer questions."},
        {"role": "user", "content": f"Context: {context}\n\nQuestion: {query}"}
    ]
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=150
    )
    return response.choices[0].message.content

# Main Streamlit app
st.title("Course Information Chatbot")

# Set up the VectorDB if it's not already set up
setup_vectordb()

# Initialize chat history if not already in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Handle user input and respond
if prompt := st.chat_input("What would you like to know about the course?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Query VectorDB for relevant documents
    results = query_vectordb(prompt)
    
    # Set a distance threshold (adjust as needed)
    DISTANCE_THRESHOLD = 0.7
    
    if results and results['documents'][0] and results['distances'][0][0] < DISTANCE_THRESHOLD:
        # Retrieve document content from the vector DB and use it as context
        context = " ".join([doc for doc in results['documents'][0]])
        response = get_ai_response(prompt, context)

        # Indicate that the bot is using context from the RAG pipeline
        final_response = f"(Using retrieved knowledge from documents)\n\n{response}"
        st.session_state.messages.append({"role": "assistant", "content": final_response})
        with st.chat_message("assistant"):
            st.markdown(final_response)

            # Optionally display related document names
            st.write("Related documents:")
            for i, doc_id in enumerate(results['ids'][0]):
                st.write(f"{i+1}. {doc_id}")
    else:
        # If no relevant documents were found, generate response without document context
        response = get_ai_response(prompt, "")
        final_response = f"(No relevant information found in documents, answering from general knowledge)\n\n{response}"
        st.session_state.messages.append({"role": "assistant", "content": final_response})
        with st.chat_message("assistant"):
            st.markdown(final_response)
