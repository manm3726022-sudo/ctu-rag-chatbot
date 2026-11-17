import os

# Test không bao giờ gọi Groq thật và luôn dùng retriever giả.
os.environ['RETRIEVER'] = 'mock'
os.environ['GROQ_API_KEY'] = ''
