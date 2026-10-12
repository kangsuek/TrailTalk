"""검증용 최소 MCP 서버: save_note 하나. 호출 내용을 인자로 받은 파일에 한 줄씩 기록한다."""

import json
import sys

from mcp.server.mcpserver import MCPServer

LOG_PATH = sys.argv[1]
mcp = MCPServer("trailtalk")


@mcp.tool()
def save_note(kind: str, content: str) -> str:
    """사용자가 저장을 요청한 내용을 노트로 저장한다. kind는 idea, todo, memo 중 하나."""
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": kind, "content": content}, ensure_ascii=False) + "\n")
    return "저장 완료"


if __name__ == "__main__":
    mcp.run()
