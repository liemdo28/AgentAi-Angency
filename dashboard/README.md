# Agency Command Center Dashboard

Dashboard web để monitor tất cả projects và stores trong hệ thống.

## Quick Start

### Option 1: Open directly (for development)

Mở file `index.html` trong browser:
```
dashboard/index.html
```

Hoặc serve bằng Python:
```bash
cd agentai-agency/dashboard
python -m http.server 8080
# Mở http://localhost:8080
```

### Option 2: Production deployment

Copy toàn bộ folder `dashboard/` lên web server (Apache/Nginx).

## Features

### Overview Panel
- **Stats Cards**: Active projects, stores online, total revenue, pending tasks
- **Project Status Grid**: Real-time status của tất cả 5 projects
- **Store Performance**: Performance metrics cho 6 stores

### Projects Monitored

| Project | Description | API |
|---------|-------------|-----|
| `agentai-agency` | AI agency brain | FastAPI `http://localhost:8000` |
| `dashboard-taskflow` | Task management | DreamHost `dashboard.bakudanramen.com` |
| `growth-dashboard` | Sales & marketing analytics | `growth-dashboard/public/` |
| `review-management-mcp` | Google/Yelp auto-reply | MCP logs |
| `integration-full` | ToastPOS ↔ QB sync | Desktop app |

### Stores Covered

| Store ID | Name | Group |
|----------|------|-------|
| B1 | Bakudan - THE RIM | Bakudan |
| B2 | Bakudan - STONE OAK | Bakudan |
| B3 | Bakudan - BANDERA | Bakudan |
| RAW | Raw Sushi - Stockton | Raw Sushi |
| COPPER | Copper | Other |
| IFT | IFT | Other |

## API Configuration

Để kết nối với `agentai-agency`, cần chạy API server:

```bash
cd agentai-agency
pip install -r requirements.txt
PYTHONPATH=.:src uvicorn src.api:app --reload
```

API sẽ chạy tại `http://localhost:8000`

## Refresh

Dashboard tự động refresh mỗi 30 giây.
Click "Refresh All" để update ngay.

## Files

```
dashboard/
├── index.html    # Main HTML
├── styles.css    # Dark theme styling
├── app.js        # Dashboard logic & API calls
└── README.md     # This file
```

## Color Legend

- 🟢 **Online** - System hoạt động bình thường
- 🟡 **Warning** - Cần chú ý, một số metrics có vấn đề
- 🔴 **Offline** - System không kết nối được hoặc có lỗi
