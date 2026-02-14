# api.py - 修复超时问题
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel
from typing import List, Optional
import json
import asyncio

app = FastAPI(title="QwQ-32B API服务")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 关键：增加超时时间
client = OpenAI(
    base_url="https://api.suanli.cn/v1",
    api_key="sk-cavgiqrWgH2QVbjCDAfc2NOYaIkmmKaJCLrIIM6ZnDlDIz6h",
    timeout=120.0,  # 增加到120秒
    max_retries=3,   # 自动重试3次
)

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    stream: Optional[bool] = True

@app.get("/")
async def root():
    return {"status": "ok", "message": "QwQ-32B API服务运行中"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        # 调用API，增加超时
        response = client.chat.completions.create(
            model="Qwen/QwQ-32B",
            messages=[{"role": m.role, "content": m.content} for m in request.messages],
            stream=request.stream,
            timeout=100.0,  # 请求超时100秒
        )
        
        if request.stream:
            async def generate():
                try:
                    for chunk in response:
                        if chunk.choices[0].delta.content:
                            data = json.dumps({
                                "content": chunk.choices[0].delta.content
                            }, ensure_ascii=False)
                            yield f"data: {data}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    print(f"[ERROR] 流式生成错误: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
            return StreamingResponse(generate(), media_type="text/event-stream")
        else:
            content = response.choices[0].message.content
            return JSONResponse({"content": content, "status": "ok"})
            
    except Exception as e:
        import traceback
        print(f"[ERROR] {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("启动 QwQ-32B API服务")
    print("超时设置: 120秒")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=1)