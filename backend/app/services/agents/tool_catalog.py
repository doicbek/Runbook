from typing import TypedDict


class ToolEntry(TypedDict):
    id: str
    name: str
    category: str
    description: str
    import_snippet: str
    usage_snippet: str
    pip_package: str | None


TOOL_CATALOG: list[ToolEntry] = [
    {
        "id": "python-docx",
        "name": "python-docx",
        "category": "Documents",
        "description": "Read and write Microsoft Word (.docx) files",
        "import_snippet": "from docx import Document",
        "usage_snippet": (
            "# Read a Word document\n"
            "doc = Document('/mnt/c/Users/YourName/Documents/file.docx')\n"
            "text = '\\n'.join(p.text for p in doc.paragraphs)\n\n"
            "# Write a Word document\n"
            "doc = Document()\n"
            "doc.add_heading('Title', 0)\n"
            "doc.add_paragraph('Body text here.')\n"
            "doc.save('/mnt/c/Users/YourName/Documents/output.docx')"
        ),
        "pip_package": "python-docx",
    },
    {
        "id": "openpyxl",
        "name": "openpyxl",
        "category": "Documents",
        "description": "Read and write Microsoft Excel (.xlsx) files",
        "import_snippet": "import openpyxl",
        "usage_snippet": (
            "# Read an Excel file\n"
            "wb = openpyxl.load_workbook('/mnt/c/Users/YourName/Documents/data.xlsx')\n"
            "ws = wb.active\n"
            "for row in ws.iter_rows(values_only=True):\n"
            "    print(row)\n\n"
            "# Write an Excel file\n"
            "wb = openpyxl.Workbook()\n"
            "ws = wb.active\n"
            "ws['A1'] = 'Hello'\n"
            "ws['B1'] = 'World'\n"
            "wb.save('/mnt/c/Users/YourName/Documents/output.xlsx')"
        ),
        "pip_package": "openpyxl",
    },
    {
        "id": "python-pptx",
        "name": "python-pptx",
        "category": "Documents",
        "description": "Read and write Microsoft PowerPoint (.pptx) files",
        "import_snippet": "from pptx import Presentation",
        "usage_snippet": (
            "# Read a PowerPoint file\n"
            "prs = Presentation('/mnt/c/Users/YourName/Documents/slides.pptx')\n"
            "for slide in prs.slides:\n"
            "    for shape in slide.shapes:\n"
            "        if hasattr(shape, 'text'):\n"
            "            print(shape.text)\n\n"
            "# Create a new presentation\n"
            "prs = Presentation()\n"
            "slide = prs.slides.add_slide(prs.slide_layouts[0])\n"
            "slide.shapes.title.text = 'My Presentation'\n"
            "prs.save('/mnt/c/Users/YourName/Documents/output.pptx')"
        ),
        "pip_package": "python-pptx",
    },
    {
        "id": "win32com",
        "name": "win32com (Windows COM)",
        "category": "Documents",
        "description": "Windows COM automation (NOT available in WSL2 — use python-docx/openpyxl instead). Only works when running natively on Windows.",
        "import_snippet": "import win32com.client  # WARNING: not available in WSL2",
        "usage_snippet": (
            "# WARNING: win32com does NOT work in WSL2.\n"
            "# Use python-docx for Word, openpyxl for Excel, python-pptx for PowerPoint.\n"
            "# This snippet is for reference only if running natively on Windows:\n"
            "# import win32com.client\n"
            "# word = win32com.client.Dispatch('Word.Application')"
        ),
        "pip_package": "pywin32",
    },
    {
        "id": "httpx",
        "name": "httpx",
        "category": "Web & HTTP",
        "description": "Async HTTP client for making web requests and calling APIs",
        "import_snippet": "import httpx",
        "usage_snippet": (
            "# Async GET request\n"
            "async with httpx.AsyncClient() as client:\n"
            "    response = await client.get('https://api.example.com/data')\n"
            "    data = response.json()\n\n"
            "# POST with JSON body\n"
            "async with httpx.AsyncClient() as client:\n"
            "    response = await client.post(\n"
            "        'https://api.example.com/submit',\n"
            "        json={'key': 'value'},\n"
            "        headers={'Authorization': 'Bearer TOKEN'},\n"
            "    )\n"
            "    result = response.json()"
        ),
        "pip_package": "httpx",
    },
    {
        "id": "playwright",
        "name": "playwright",
        "category": "Web & HTTP",
        "description": "Browser automation for scraping JavaScript-rendered pages",
        "import_snippet": "from playwright.async_api import async_playwright",
        "usage_snippet": (
            "async with async_playwright() as p:\n"
            "    browser = await p.chromium.launch(headless=True)\n"
            "    page = await browser.new_page()\n"
            "    await page.goto('https://example.com')\n"
            "    content = await page.content()\n"
            "    text = await page.inner_text('body')\n"
            "    await browser.close()"
        ),
        "pip_package": "playwright",
    },
    {
        "id": "pathlib",
        "name": "pathlib",
        "category": "Filesystem",
        "description": "Standard library filesystem operations (read, write, list directories)",
        "import_snippet": "from pathlib import Path",
        "usage_snippet": (
            "# Read a text file\n"
            "text = Path('/mnt/c/Users/YourName/Documents/file.txt').read_text()\n\n"
            "# Write a text file\n"
            "Path('/mnt/c/Users/YourName/Documents/output.txt').write_text('content')\n\n"
            "# List files in a directory\n"
            "files = list(Path('/mnt/c/Users/YourName/Documents').glob('*.txt'))\n\n"
            "# Windows paths in WSL2 are mounted at /mnt/c/ (C:\\\\)\n"
            "# e.g. C:\\\\Users\\\\Name\\\\file.txt → /mnt/c/Users/Name/file.txt"
        ),
        "pip_package": None,
    },
    {
        "id": "mcp",
        "name": "MCP (Model Context Protocol)",
        "category": "MCP",
        "description": "Connect to MCP servers to use external tools and resources",
        "import_snippet": "# MCP config is set via the mcp_config field (JSON)",
        "usage_snippet": (
            "# MCP servers are configured via the mcp_config JSON field.\n"
            "# Example config:\n"
            "# {\n"
            "#   'servers': [\n"
            "#     {'name': 'filesystem', 'command': 'mcp-server-filesystem', 'args': ['/path']}\n"
            "#   ]\n"
            "# }\n"
            "# The agent can then use MCP tool calls within its execute() method."
        ),
        "pip_package": None,
    },
]

TOOL_CATALOG_BY_ID: dict[str, ToolEntry] = {t["id"]: t for t in TOOL_CATALOG}
