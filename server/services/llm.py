# server/services/llm.py
import boto3
import json
import os

# AWS Configuration
# Ensure your ~/.aws/credentials are set, or set AWS_PROFILE/AWS_REGION in .env
BEDROCK_REGION = os.environ.get("AWS_REGION", "us-east-1")
# Using Haiku for speed/cost. Make sure you have access enabled in Bedrock Console!
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0" 

bedrock = boto3.client(service_name="bedrock-runtime", region_name=BEDROCK_REGION)

SYSTEM_PROMPT = """
You are the "Brain" of a voice coding assistant. Map natural language to tools.
Output STRICT JSON only. No markdown, no conversational text.

Structure:
{
  "intent": "create_project" | "create_task" | "status_check" | "unknown",
  "project_name": <string | null>,
  "task_description": <string | null>,
  "parameters": <object>
}
"""

async def parse_intent(text: str, projects: list):
    # Format project context
    project_names = [p['name'] for p in projects]
    context_str = f"Available Projects: {', '.join(project_names)}"
    
    user_message = f"""
    Context: {context_str}
    User Command: "{text}"
    """

    try:
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": user_message}
                ]
            })
        )

        # Parse Bedrock response
        response_body = json.loads(response.get("body").read())
        content_text = response_body["content"][0]["text"]
        
        # Clean up if the model adds markdown code blocks
        if "```json" in content_text:
            content_text = content_text.split("```json")[1].split("```")[0].strip()
            
        return json.loads(content_text)

    except Exception as e:
        print(f"Bedrock Error: {e}")
        return {"intent": "error", "message": str(e)}