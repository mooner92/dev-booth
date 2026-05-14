from notion_client import Client
import os
from dotenv import load_dotenv

load_dotenv('/dev-booth/config/.env')

notion = Client(auth=os.getenv('NOTION_TOKEN'))
DATABASE_ID = os.getenv('NOTION_DATABASE_ID')

def _text_blocks(content: str) -> list:
    """긴 텍스트를 1900자씩 paragraph 블록으로 분할"""
    chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}]
            }
        }
        for chunk in chunks
    ][:100]

def log(session: str, agent: str, message: str,
        status: str = 'active', repository: str = ''):
    """짧은 상태 로그 - 제목 + 페이지 본문"""
    title = f"[{agent}] {message[:80]}"
    try:
        notion.pages.create(
            parent={"database_id": DATABASE_ID},
            properties={
                "Name":       {"title": [{"text": {"content": title}}]},
                "Status":     {"select": {"name": status}},
                "Agent":      {"select": {"name": agent}},
                "Message":    {"rich_text": [{"text": {"content": message[:200]}}]},
                "Session":    {"rich_text": [{"text": {"content": session}}]},
                "Repository": {"rich_text": [{"text": {"content": repository}}]}
            },
            children=_text_blocks(message) if len(message) > 200 else []
        )
    except Exception as e:
        print(f"Notion 로그 실패: {e}")

def log_document(session: str, agent: str, title: str, content: str,
                 status: str = 'active', repository: str = ''):
    """긴 문서 - 제목만 DB에, 전체 내용은 페이지 본문으로"""
    try:
        notion.pages.create(
            parent={"database_id": DATABASE_ID},
            properties={
                "Name":       {"title": [{"text": {"content": f"[{agent}] {title}"}}]},
                "Status":     {"select": {"name": status}},
                "Agent":      {"select": {"name": agent}},
                "Message":    {"rich_text": [{"text": {"content": f"📄 {title}"}}]},
                "Session":    {"rich_text": [{"text": {"content": session}}]},
                "Repository": {"rich_text": [{"text": {"content": repository}}]}
            },
            children=[
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": title}}]
                    }
                }
            ] + _text_blocks(content)
        )
    except Exception as e:
        print(f"Notion 문서 로그 실패: {e}")
