# Ai Accurate package (LLM Structuring)

## To Install Dependencies 
pip install -r requirements.txt

## TO RUN
 uvicorn app:app --reload --port 8000

## Activate NGROK
ngrok http 8000

## AI WEB PAGE
http://localhost:8000/docs
## stress test 
curl http://localhost:11434/api/chat -d "{\"model\":\"mistral\",\"messages\":[{\"role\":\"user\",\"content\":\"warm up\"}],\"stream\":false}"

