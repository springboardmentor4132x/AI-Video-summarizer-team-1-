AI-Video-summarizer-team-1-/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── security.py
│   │   ├── models/          # Member 2 fills this
│   │   ├── schemas/         # Pydantic request/response models
│   │   ├── routers/         # Member 3 fills this (auth.py, videos.py)
│   │   ├── services/        # Member 5 fills this (ffmpeg_service.py)
│   │   └── db/
│   │       └── session.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── app/                 # Member 4 fills this
│   ├── components/
│   ├── lib/
│   ├── package.json
│   └── .env.example
├── docs/
│   ├── architecture.md
│   ├── setup.md
│   ├── api-reference.md
│   └── wireframes/
├── .gitignore
├── docker-compose.yml
└── README.md
