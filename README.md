Sanri Backend



Requirements

\- Windows

\- Python 3.10+ recommended



Setup

1\) Run: .\\setup.ps1

2\) Edit .env and set OPENAI\_API\_KEY and OPENAI\_MODEL

3\) Run: .\\run.ps1

4\) Open: http://127.0.0.1:8000/panel



Routes

\- POST /bilinc\_alani/chat

\- POST /sanri\_voice/speak

\- GET /memory/{session\_id}

\- DELETE /memory/{session\_id}



Static

\- /panel

\- /static/voices/{filename}

